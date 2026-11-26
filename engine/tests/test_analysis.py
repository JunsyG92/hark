"""Analysis pipeline, cache, budget, profile, LLM providers. Synthetic transcripts only."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from hark_engine.analysis import AnalysisService
from hark_engine.analysis.chunking import chunk_lines, est_tokens, to_lines
from hark_engine.analysis.mine import is_mine
from hark_engine.analysis.pipeline import (
    BudgetExceeded,
    InvalidOutput,
    normalize_output,
    parse_due,
    parse_output,
    parse_timestamp,
    run_pipeline,
)
from hark_engine.events import EventBus
from hark_engine.llm import (
    CloudProvider,
    LLMModelMissingError,
    LLMResult,
    LLMUnavailableError,
    OllamaProvider,
    ScriptedProvider,
)
from hark_engine.models import (
    AnalysisOutput,
    AnalysisStatus,
    CloudSettings,
    CloudSettingsPatch,
    Column,
    EventType,
    LLMSettings,
    LLMSettingsPatch,
    MeetingStatus,
    Speaker,
    TrackKind,
    TranscriptSegment,
    UserProfile,
)
from hark_engine.net import blocked_attempts, install_guard, uninstall_guard
from hark_engine.profile import ProfileError, ProfileStore, parse_profile
from hark_engine.store import (
    AnalysisRepository,
    Database,
    MeetingRepository,
    NewSegment,
    SettingsRepository,
    TaskRepository,
)

PROFILE = UserProfile(name="Mathieu Nesseir", nicknames=["Mat"])


def seg(i: int, speaker: Speaker, start_s: int, text: str) -> TranscriptSegment:
    return TranscriptSegment(
        id=i, meeting_id="m", track=TrackKind.MIC if speaker is Speaker.ME else TrackKind.SYSTEM,
        speaker=speaker, start_ms=start_s * 1000, end_ms=start_s * 1000 + 3000, text=text,
    )  # fmt: skip


SEGS = [
    seg(1, Speaker.OTHERS, 0, "Bonjour, on fait le point sur le budget Q1."),
    seg(2, Speaker.ME, 4, "Je m'occupe du budget Q1."),
    seg(3, Speaker.OTHERS, 9, "Paul, tu relis le contrat fournisseur ?"),
]


# ---- pure helpers -------------------------------------------------------------------------
def test_chunking_respects_the_token_bound_and_keeps_order():
    segs = [seg(i, Speaker.OTHERS, i * 3, "mot " * 60) for i in range(20)]
    chunks = chunk_lines(to_lines(segs, "Mathieu"), 500)
    assert len(chunks) > 3 and all(c.tokens <= 500 + est_tokens("mot " * 60) for c in chunks)
    assert [c.start_ms for c in chunks] == sorted(c.start_ms for c in chunks)
    assert chunk_lines([], 500) == []
    assert "Moi (Mathieu)" in to_lines(SEGS, "Mathieu")[1].text


def test_parse_output_tolerates_fences_extra_keys_and_rejects_garbage():
    body = '{"title": "T", "summary": "S", "tasks": [{"title": "A", "foo": 1}], "extra": 5}'
    raw = f"```json\n{body}\n```"
    out = parse_output(raw)
    assert out.title == "T" and out.tasks[0].title == "A"
    with pytest.raises(InvalidOutput):
        parse_output("Désolé, je ne peux pas.")
    with pytest.raises(InvalidOutput):
        parse_output('{"tasks": [{"title": "x", "confidence": 7}]}')  # confidence out of 0..1


def test_timestamps_and_dates():
    assert parse_timestamp("00:04") == 4000 and parse_timestamp("[1:02:05]") == 3_725_000
    assert parse_timestamp(12) == 12_000 and parse_timestamp("12s") == 12_000
    assert parse_timestamp("tout à l'heure") is None and parse_timestamp(None) is None
    assert str(parse_due("2026-12-05")) == "2026-12-05" and parse_due("vendredi") is None


def test_normalize_output_enforces_limits_and_dedupes():
    out = AnalysisOutput.model_validate(
        {
            "summary": "\n".join(f"ligne {i}" for i in range(25)),
            "decisions": ["  d  ", "", "e"],
            "tasks": [{"title": "Faire X"}, {"title": " faire x "}, {"title": ""}]
            + [{"title": f"t{i}"} for i in range(60)],
        }
    )
    n = normalize_output(out)
    assert len(n.summary.splitlines()) == 10 and n.decisions == ["d", "e"]
    assert n.tasks[0].title == "Faire X" and len(n.tasks) == 30
    assert len({t.title.lower() for t in n.tasks}) == len(n.tasks)


def test_is_mine_rules():
    me = PROFILE
    assert is_mine("Mathieu", None, SEGS, me) and is_mine("mat", None, SEGS, me)
    assert is_mine("MATHIEU NESSEIR", None, SEGS, me) and is_mine("moi", None, SEGS, me)
    assert not is_mine("Paul", None, SEGS, me)
    assert is_mine("", 4000, SEGS, me)  # "je m'occupe du budget" said on the mic track
    assert is_mine("", 0, SEGS, me)  # asked at 00:00, I answered "je m'occupe" 4 s later
    assert not is_mine("", 9000, SEGS, me)  # my commitment came BEFORE that request
    assert not is_mine("", 60_000, SEGS, me)  # far from anything I said
    other = [seg(1, Speaker.OTHERS, 0, "Je m'en occupe, ne t'inquiète pas.")]
    assert not is_mine("", 0, other, me)  # the commitment must come from the user's own track
    assert not is_mine("Paul", 4000, SEGS, me)  # explicitly assigned to someone else
    assert is_mine("Éloïse", None, SEGS, UserProfile(name="Eloise Martin"))  # accents


# ---- pipeline ----------------------------------------------------------------------------
def test_short_transcript_is_one_llm_call():
    p = ScriptedProvider()
    res = run_pipeline(p, SEGS, "2026-11-25", PROFILE, LLMSettings())
    assert len(p.calls) == 1 and res.chunks == 1
    assert p.calls[0][2] is not None  # JSON schema requested
    assert res.output.tasks[0].title.startswith("Envoyer le budget")
    assert "Mathieu Nesseir" in p.calls[0][1] and "2026-11-25" in p.calls[0][1]


def test_long_transcript_is_summarized_per_chunk_then_one_final_pass():
    segs = [seg(i, Speaker.OTHERS, i * 3, "contenu de réunion " * 30) for i in range(30)]
    p = ScriptedProvider()
    cfg = LLMSettings(chunk_tokens=1000, max_tokens_per_meeting=100_000)
    res = run_pipeline(p, segs, "2026-11-25", PROFILE, cfg)
    maps = [c for c in p.calls if c[2] is None]
    finals = [c for c in p.calls if c[2] is not None]
    assert res.chunks == len(maps) > 1 and len(finals) == 1
    assert "[00:00]" in finals[0][1]  # the final pass reads the notes, not the raw transcript
    assert len(finals[0][1]) < sum(len(s.text) for s in segs)


def test_budget_is_checked_before_any_call():
    segs = [seg(i, Speaker.OTHERS, i, "mot " * 200) for i in range(100)]
    p = ScriptedProvider()
    with pytest.raises(BudgetExceeded, match="budget"):
        run_pipeline(p, segs, "d", PROFILE, LLMSettings(max_tokens_per_meeting=2000))
    assert p.calls == []  # nothing was sent


def test_budget_is_enforced_with_real_token_counts():
    class Greedy(ScriptedProvider):
        def chat(self, system: str, user: str, **kw: Any) -> LLMResult:
            return LLMResult("{}", tokens_in=50_000, tokens_out=10)

    with pytest.raises(BudgetExceeded):
        run_pipeline(Greedy(), SEGS, "d", PROFILE, LLMSettings(max_tokens_per_meeting=10_000))


def test_invalid_json_gets_exactly_one_repair_attempt():
    answers = iter(["pas du json", ScriptedProvider().responder("", "", {})])
    p = ScriptedProvider(responder=lambda s, u, schema: next(answers))
    res = run_pipeline(p, SEGS, "d", PROFILE, LLMSettings())
    assert len(p.calls) == 2 and res.output.tasks
    bad = ScriptedProvider(responder=lambda s, u, schema: "toujours pas du json")
    with pytest.raises(InvalidOutput):
        run_pipeline(bad, SEGS, "d", PROFILE, LLMSettings())
    assert len(bad.calls) == 2


# ---- service -------------------------------------------------------------------------------
class Env:
    def __init__(self, db: Database, tmp: Path, provider: ScriptedProvider | None = None) -> None:
        self.bus = EventBus()
        self.events: list = []
        self.bus.subscribe(self.events.append)
        self.meetings = MeetingRepository(db)
        self.tasks = TaskRepository(db)
        self.analyses = AnalysisRepository(db)
        self.settings = SettingsRepository(db)
        self.profile = ProfileStore(tmp / "profile.yaml")
        self.profile.save('name: "Mathieu Nesseir"\nnicknames: ["Mat"]\n')
        self.provider = provider or ScriptedProvider()
        self.service = AnalysisService(
            self.meetings, self.analyses, self.tasks, self.settings, self.bus, self.profile,
            lambda: self.provider,
        )  # fmt: skip

    def meeting(self, mid: str = "m1", title: str = "") -> str:
        self.meetings.create(mid, title, "Teams", {})
        self.meetings.finish(mid, MeetingStatus.RECORDED, 12000)
        self.meetings.replace_segments(
            mid,
            [NewSegment(s.track, s.speaker, s.start_ms, s.end_ms, s.text) for s in SEGS],
        )
        return mid

    def wait(self, mid: str, status: AnalysisStatus, timeout: float = 5) -> None:
        end = time.time() + timeout
        while time.time() < end:
            if self.meetings.get(mid).analysis == status:
                return
            time.sleep(0.02)
        raise AssertionError(f"{mid}: {self.meetings.get(mid).analysis}, wanted {status}")


@pytest.fixture
def env(db: Database, tmp_path: Path):
    e = Env(db, tmp_path)
    e.service.start()
    yield e
    e.service.stop()


def test_transcript_ready_triggers_analysis_with_tasks_in_to_validate(env: Env):
    mid = env.meeting()
    env.bus.publish(EventType.TRANSCRIPT_READY, {"meeting_id": mid, "segments": 3})
    env.wait(mid, AnalysisStatus.DONE)
    tasks = env.tasks.list(source=f"meeting:{mid}")
    assert len(tasks) == 2 and all(t.column == Column.TO_VALIDATE for t in tasks)
    by_title = {t.title: t for t in tasks}
    budget = by_title["Envoyer le budget Q1 à la direction"]
    assert budget.is_mine and budget.evidence and budget.evidence.start_ms == 4000
    assert budget.evidence.meeting_id == mid and "Je m'occupe du budget Q1" in budget.description
    paul = by_title["Relire le contrat fournisseur"]
    assert not paul.is_mine and paul.assignee == "Paul" and str(paul.due) == "2026-12-05"
    assert env.meetings.get(mid).title == "Revue budget Q1"  # automatic title
    stored = env.analyses.get(mid)
    assert stored and stored.analysis.tasks_proposed == 2 and stored.analysis.tokens_in > 0
    assert env.meetings.search("réserve")[0]["kind"] == "summary"  # summaries are searchable
    types = [e.type for e in env.events]
    assert types.count(EventType.TASK_PROPOSED) == 2 and EventType.ANALYSIS_READY in types


def test_same_input_is_never_reprocessed(env: Env):
    mid = env.meeting()
    env.service.submit(mid)
    env.wait(mid, AnalysisStatus.DONE)
    calls = len(env.provider.calls)
    env.service.submit(mid)  # explicit click, same transcript/model/profile: cache hit
    time.sleep(0.4)
    env.wait(mid, AnalysisStatus.DONE)
    assert len(env.provider.calls) == calls
    # the automatic trigger never re-processes an analyzed meeting
    env.bus.publish(EventType.TRANSCRIPT_READY, {"meeting_id": mid})
    time.sleep(0.3)
    assert len(env.provider.calls) == calls


def test_force_reruns_without_duplicating_tasks_and_profile_change_invalidates_cache(env: Env):
    mid = env.meeting()
    env.service.submit(mid)
    env.wait(mid, AnalysisStatus.DONE)
    calls = len(env.provider.calls)
    env.service.submit(mid, force=True)
    for _ in range(100):
        if len(env.provider.calls) > calls:
            break
        time.sleep(0.02)
    env.wait(mid, AnalysisStatus.DONE)
    assert len(env.provider.calls) > calls and len(env.tasks.list(source=f"meeting:{mid}")) == 2
    calls = len(env.provider.calls)
    env.profile.save(
        'name: "Mathieu Nesseir"\nrole: "CTO"\n'
    )  # different profile = different input
    env.service.submit(mid)
    for _ in range(100):
        if len(env.provider.calls) > calls:
            break
        time.sleep(0.02)
    assert len(env.provider.calls) > calls


def test_auto_analyze_off_does_nothing(env: Env):
    from hark_engine.models import LLMSettingsPatch

    env.settings.patch_llm(LLMSettingsPatch(auto_analyze=False))
    mid = env.meeting()
    env.bus.publish(EventType.TRANSCRIPT_READY, {"meeting_id": mid})
    time.sleep(0.3)
    assert env.meetings.get(mid).analysis == AnalysisStatus.NONE and env.provider.calls == []


def test_llm_down_waits_then_runs_when_it_is_back(env: Env):
    env.provider.ok = False
    mid = env.meeting()
    env.service.submit(mid)
    for _ in range(200):  # PENDING is also the queued state: wait for the recorded reason
        if env.meetings.get(mid).analysis_error:
            break
        time.sleep(0.02)
    assert env.meetings.get(mid).analysis == AnalysisStatus.PENDING
    assert "llm_unavailable" in (env.meetings.get(mid).analysis_error or "")
    assert env.tasks.list() == [] and env.provider.calls == []
    env.provider.ok = True
    env.service.retry_pending()
    env.wait(mid, AnalysisStatus.DONE)


def test_budget_failure_is_reported_and_creates_nothing(env: Env):
    env.settings.patch_llm(LLMSettingsPatch(max_tokens_per_meeting=2000))
    big = env.meeting("big")
    env.meetings.replace_segments(
        big,
        [
            NewSegment(TrackKind.SYSTEM, Speaker.OTHERS, i * 1000, i * 1000 + 900, "mot " * 300)
            for i in range(80)
        ],
    )
    env.service.submit(big)
    env.wait(big, AnalysisStatus.FAILED)
    assert "budget_exceeded" in (env.meetings.get(big).analysis_error or "")
    assert env.provider.calls == [] and env.tasks.list() == []


def test_no_transcript_fails_cleanly(env: Env):
    env.meetings.create("empty", "", "", {})
    env.service.submit("empty")
    env.wait("empty", AnalysisStatus.FAILED)
    assert env.meetings.get("empty").analysis_error == "no_transcript"


# ---- profile.yaml ----------------------------------------------------------------------------
def test_profile_validation_and_safe_yaml(tmp_path: Path):
    p = parse_profile('name: "A B"\nnicknames: [x]\nprojects: [Q1]\n')
    assert p.name == "A B" and p.nicknames == ["x"]
    assert parse_profile("").name == ""
    for bad in ("name: [1", "- a\n- b", "unknown: 1", "nicknames: 5", "name: " + "x" * 300):
        with pytest.raises(ProfileError):
            parse_profile(bad)
    with pytest.raises(ProfileError):
        parse_profile("name: !!python/object/apply:os.system ['echo hacked']")  # safe_load only
    store = ProfileStore(tmp_path / "p.yaml")
    assert "name" in store.text() and store.load().name == ""
    with pytest.raises(ProfileError):
        store.save("unknown: 1")
    assert not (tmp_path / "p.yaml").exists()  # nothing written when invalid
    store.save("name: Zoé\n")
    assert store.load().name == "Zoé"
    (tmp_path / "p.yaml").write_text("name: [broken", encoding="utf-8")
    assert (
        store.load().name == "" and store.document().error
    )  # a broken file never crashes analysis


# ---- providers ----------------------------------------------------------------------------------
class FakeLLMServer:
    """A tiny local HTTP server standing in for Ollama / a cloud endpoint."""

    def __init__(self, models: list[str] | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.models = models if models is not None else ["qwen2.5:7b-instruct"]
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def _send(self, code: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/api/tags":
                    self._send(200, {"models": [{"name": m} for m in outer.models]})
                else:
                    self._send(404, {})

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(
                    {"path": self.path, "body": body, "auth": self.headers.get("Authorization")}
                )
                if self.path == "/api/chat":
                    if body["model"] not in outer.models:
                        return self._send(404, {"error": "model not found"})
                    self._send(
                        200,
                        {
                            "message": {"content": '{"summary": "ok"}'},
                            "prompt_eval_count": 11,
                            "eval_count": 5,
                        },
                    )
                elif self.path == "/chat/completions":
                    self._send(
                        200,
                        {
                            "choices": [{"message": {"content": "{}"}}],
                            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                        },
                    )
                else:
                    self._send(404, {})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()  # refuse new connections instead of leaving them hanging


@pytest.fixture
def server():
    s = FakeLLMServer()
    yield s
    s.close()


def test_ollama_sends_schema_temperature_zero_and_context_window(server: FakeLLMServer):
    p = OllamaProvider(server.url, "qwen2.5:7b-instruct")
    assert p.available() == (True, None)
    res = p.chat("sys", "user", json_schema={"type": "object"}, max_tokens=300, num_ctx=8192)
    body = server.requests[-1]["body"]
    assert (res.tokens_in, res.tokens_out) == (11, 5)
    assert body["format"] == {"type": "object"} and body["stream"] is False
    assert body["options"] == {"temperature": 0, "num_predict": 300, "num_ctx": 8192}
    assert body["messages"][0] == {"role": "system", "content": "sys"}


def test_ollama_errors_are_explicit(server: FakeLLMServer):
    assert OllamaProvider(server.url, "absent:1b").available()[0] is False
    assert "ollama pull absent:1b" in (OllamaProvider(server.url, "absent:1b").available()[1] or "")
    with pytest.raises(LLMModelMissingError):
        OllamaProvider(server.url, "absent:1b").chat("s", "u")
    server.close()
    down = OllamaProvider(server.url, "qwen2.5:7b-instruct")
    ok, why = down.available()
    assert not ok and "injoignable" in (why or "")
    with pytest.raises(LLMUnavailableError):
        down.chat("s", "u")


def test_cloud_is_disabled_by_default_and_needs_explicit_opt_in(
    server: FakeLLMServer, db: Database
):
    default = CloudProvider(CloudSettings(), lambda: "key-123456")
    assert default.available() == (False, "fournisseur cloud désactivé")
    with pytest.raises(LLMUnavailableError):
        default.chat("s", "u")
    settings = SettingsRepository(db)
    with pytest.raises(ValueError, match="acknowledge"):
        settings.patch_cloud(
            CloudSettingsPatch(enabled=True)
        )  # cannot enable without acknowledging
    no_key = CloudProvider(
        CloudSettings(enabled=True, acknowledged=True, base_url=server.url, model="m"), lambda: None
    )
    assert no_key.available()[0] is False
    on = CloudProvider(
        CloudSettings(enabled=True, acknowledged=True, base_url=server.url, model="m"),
        lambda: "key-123456",
    )
    res = on.chat("s", "u", json_schema={})
    assert (res.tokens_in, res.tokens_out) == (7, 3) and server.requests[-1][
        "auth"
    ] == "Bearer key-123456"
    http = CloudProvider(
        CloudSettings(enabled=True, acknowledged=True, base_url="http://example.com", model="m"),
        lambda: "key-123456",
    )
    assert http.available()[0] is False  # plain http to a remote host is refused


def test_llm_settings_url_must_be_local():
    assert LLMSettings(ollama_url="http://localhost:11434/").ollama_url == "http://localhost:11434"
    for bad in (
        "http://example.com:11434",
        "http://192.168.1.5:11434",
        "ftp://127.0.0.1",
        "javascript:1",
    ):
        with pytest.raises(ValueError):
            LLMSettings(ollama_url=bad)


def test_analysis_flow_with_local_server_makes_no_outbound_connection(
    db: Database, tmp_path: Path, server: FakeLLMServer
):
    """Real OllamaProvider ↔ local server, guard on: loopback is fine, nothing else is attempted."""
    install_guard()
    try:
        e = Env(db, tmp_path)
        e.provider = OllamaProvider(server.url, "qwen2.5:7b-instruct")  # type: ignore[assignment]
        e.service.start()
        mid = e.meeting()
        e.service.submit(mid)
        e.wait(mid, AnalysisStatus.DONE)  # '{"summary": "ok"}' is valid (no tasks)
        e.service.stop()
        assert blocked_attempts() == [] and e.analyses.get(mid)
    finally:
        uninstall_guard()


def test_schema_sent_to_the_llm_is_flat_and_matches_the_validator():
    from hark_engine.analysis.pipeline import LLM_SCHEMA

    text = json.dumps(LLM_SCHEMA)
    assert "$ref" not in text and "$defs" not in text and "anyOf" not in text
    props = set(LLM_SCHEMA["properties"])  # type: ignore[call-overload]
    assert props == set(AnalysisOutput.model_fields)
    assert (
        parse_output(
            '{"title": "t", "summary": "s", "decisions": [], "open_questions": [], '
            '"tasks": [{"title": "x", "assignee": "", "due": "", "confidence": 0.5, '
            '"evidence_timestamp": ""}]}'
        )
        .tasks[0]
        .due
        == ""
    )
    assert parse_due("") is None and parse_timestamp("") is None


def test_work_interrupted_by_a_quit_is_resumed_at_start(db: Database, tmp_path: Path):
    """Regression: a meeting left `running` (closed mid-analysis) stayed stuck, no button."""
    e = Env(db, tmp_path)
    mid = e.meeting()
    e.meetings.set_analysis(mid, AnalysisStatus.RUNNING)  # what a crash leaves behind
    e.service.start()
    try:
        e.wait(mid, AnalysisStatus.DONE)
    finally:
        e.service.stop()


def test_status_reports_the_steps_of_the_running_analysis(db: Database, tmp_path: Path):
    seen: list[tuple[int, int]] = []
    segs = [seg(i, Speaker.OTHERS, i * 3, "contenu de réunion " * 30) for i in range(30)]
    cfg = LLMSettings(chunk_tokens=1000, max_tokens_per_meeting=100_000)
    run_pipeline(
        ScriptedProvider(), segs, "d", PROFILE, cfg, on_step=lambda d, t: seen.append((d, t))
    )
    total = seen[0][1]
    assert seen[0] == (0, total) and seen[-1] == (total - 1, total) and total > 2
    one = []
    run_pipeline(
        ScriptedProvider(),
        SEGS,
        "d",
        PROFILE,
        LLMSettings(),
        on_step=lambda d, t: one.append((d, t)),
    )
    assert one == [(0, 1)]
