"""Transcription, history, search, retention and network guard. Synthetic data only."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from hark_engine.api import create_app
from hark_engine.events import EventBus
from hark_engine.export import export_markdown, format_ts
from hark_engine.models import (
    EventType,
    ModelProfileId,
    TrackKind,
    TranscriptionSettingsPatch,
    TranscriptionStatus,
)
from hark_engine.net import (
    NetworkBlockedError,
    allow_network,
    blocked_attempts,
    install_guard,
    uninstall_guard,
)
from hark_engine.store import Database, MeetingRepository, SettingsRepository
from hark_engine.store.search import build_match
from hark_engine.stt import FakeTranscriber, ModelManager, TranscriptionService, recommend
from hark_engine.stt.transcriber import pick_language

TOKEN = "tok"


def make_meeting(repo: MeetingRepository, audio: Path, mid: str = "m1", title: str = "") -> str:
    folder = audio / mid
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for kind in (TrackKind.SYSTEM, TrackKind.MIC):
        p = folder / f"{kind.value}.wav"
        sf.write(str(p), np.zeros(16000, dtype="float32"), 16000, subtype="PCM_16")
        paths[kind] = p
    repo.create(mid, title, "Teams", paths)
    repo.finish(mid, __import__("hark_engine.models", fromlist=["x"]).MeetingStatus.RECORDED, 1000)
    return mid


class Env:
    def __init__(self, db: Database, tmp: Path, transcriber: Any = None, installed: bool = True):
        self.bus = EventBus()
        self.events: list = []
        self.bus.subscribe(self.events.append)
        self.repo = MeetingRepository(db)
        self.settings = SettingsRepository(db)
        self.audio = tmp / "audio"
        self.installed = installed
        self.models = ModelManager(
            tmp / "models",
            resolver=lambda *_: "x" if self.installed else (_ for _ in ()).throw(OSError("no")),
        )
        self.transcriber = transcriber or FakeTranscriber()
        self.service = TranscriptionService(
            self.repo, self.settings, self.bus, self.models, self.transcriber
        )

    def wait(self, mid: str, status: TranscriptionStatus, timeout: float = 5) -> None:
        end = time.time() + timeout
        while time.time() < end:
            if self.repo.get(mid).transcription == status:
                return
            time.sleep(0.02)
        raise AssertionError(f"{mid} is {self.repo.get(mid).transcription}, wanted {status}")


@pytest.fixture
def env(db: Database, tmp_path: Path):
    e = Env(db, tmp_path)
    e.service.start()
    yield e
    e.service.stop()


# ---- search ---------------------------------------------------------------------------
def test_build_match_is_safe_and_prefix_on_last_term():
    assert build_match("budget Q1") == '"budget" "Q1"*'
    assert build_match('a" OR 1=1 --') == '"a" "OR" "1" "1"*'  # no FTS operator injection
    assert build_match("   ") is None and build_match("!!") is None


def test_search_french_accents_prefix_titles_and_segments(env: Env):
    mid = make_meeting(env.repo, env.audio, title="Revue du budget")
    env.service.submit(mid)
    env.wait(mid, TranscriptionStatus.DONE)
    assert [h["kind"] for h in env.repo.search("revue")] == ["title"]
    assert env.repo.search("BUDGÉT") == env.repo.search("budget")  # accents/case-insensitive
    hits = env.repo.search("commen")  # prefix: "commence"
    assert hits and hits[0]["kind"] == "transcript" and hits[0]["start_ms"] == 0
    assert "<mark>" in hits[0]["snippet"] and hits[0]["speaker"] == "others"
    env.repo.set_title(mid, "Point trésorerie")
    assert env.repo.search("revue") == [] and env.repo.search("tresorerie")


# ---- service --------------------------------------------------------------------------
def test_recorded_meeting_is_transcribed_with_both_speakers_and_audio_deleted(env: Env):
    mid = make_meeting(env.repo, env.audio)
    paths = list(env.repo.track_paths(mid).values())
    env.bus.publish(
        EventType.MEETING_RECORDED, {"meeting": env.repo.get(mid).model_dump(mode="json")}
    )
    env.wait(mid, TranscriptionStatus.DONE)
    segs = env.repo.segments(mid)
    assert [(s.speaker.value, s.track.value) for s in segs] == [("others", "system"), ("me", "mic")]
    assert segs[0].start_ms <= segs[1].start_ms
    meeting = env.repo.get(mid)
    assert meeting.language == "fr" and not meeting.audio_available  # default retention: delete
    assert not any(p.exists() for p in paths)
    ready = [e for e in env.events if e.type == EventType.TRANSCRIPT_READY]
    assert ready and ready[0].data == {"meeting_id": mid, "segments": 2}


def test_auto_transcribe_off_does_not_queue(env: Env):
    env.settings.patch_transcription(TranscriptionSettingsPatch(auto_transcribe=False))
    mid = make_meeting(env.repo, env.audio)
    env.bus.publish(
        EventType.MEETING_RECORDED, {"meeting": env.repo.get(mid).model_dump(mode="json")}
    )
    time.sleep(0.3)
    assert env.repo.get(mid).transcription == TranscriptionStatus.NONE


def test_retention_keeps_audio_then_purges_when_expired(env: Env, db: Database):
    env.settings.patch_transcription(TranscriptionSettingsPatch(retention_days=7))
    mid = make_meeting(env.repo, env.audio)
    env.service.submit(mid)
    env.wait(mid, TranscriptionStatus.DONE)
    time.sleep(0.1)
    assert env.repo.get(mid).audio_available
    assert env.service.purge_expired_audio() == 0
    with db.tx() as conn:
        conn.execute("UPDATE meetings SET audio_expires_at = '2000-01-01T00:00:00+00:00'")
    assert env.service.purge_expired_audio() == 1
    assert not env.repo.get(mid).audio_available and env.repo.segments(mid)  # transcript stays


def test_missing_model_waits_then_runs_once_installed(db: Database, tmp_path: Path):
    e = Env(db, tmp_path, installed=False)
    e.transcriber.ready = lambda profile: e.installed  # type: ignore[method-assign]
    e.service.start()
    try:
        mid = make_meeting(e.repo, e.audio)
        e.service.submit(mid)
        time.sleep(0.3)
        meeting = e.repo.get(mid)
        assert meeting.transcription == TranscriptionStatus.PENDING
        assert meeting.transcription_error == "model_not_installed" and meeting.audio_available
        assert e.service.status().model_installed is False
        e.installed = True
        e.service.on_model_installed(ModelProfileId.BALANCED)
        e.wait(mid, TranscriptionStatus.DONE)
    finally:
        e.service.stop()


def test_failure_keeps_audio_and_can_be_retried(db: Database, tmp_path: Path):
    class Flaky(FakeTranscriber):
        fail = True

        def transcribe(self, *a: Any, **k: Any):  # type: ignore[no-untyped-def]
            if self.fail:
                raise RuntimeError("decoder crashed")
            return super().transcribe(*a, **k)

    flaky = Flaky()
    e = Env(db, tmp_path, flaky)
    e.service.start()
    try:
        mid = make_meeting(e.repo, e.audio)
        e.service.submit(mid)
        e.wait(mid, TranscriptionStatus.FAILED)
        assert "decoder crashed" in (e.repo.get(mid).transcription_error or "")
        assert e.repo.get(mid).audio_available  # never delete audio of a failed transcription
        flaky.fail = False
        e.service.submit(mid)
        e.wait(mid, TranscriptionStatus.DONE)
        assert e.repo.get(mid).transcription_error is None
    finally:
        e.service.stop()


def test_delete_meeting_removes_everything(env: Env):
    mid = make_meeting(env.repo, env.audio, title="Secret")
    env.service.submit(mid)
    env.wait(mid, TranscriptionStatus.DONE)
    env.repo.delete(mid)
    assert env.repo.list_recent() == [] and env.repo.search("secret") == []
    assert env.repo.search("budget") == []


def test_markdown_export():
    from datetime import UTC, datetime

    from hark_engine.models import Meeting, MeetingStatus, Speaker, TranscriptSegment

    m = Meeting(
        id="m", title="", status=MeetingStatus.RECORDED, app="Teams",
        started_at=datetime(2026, 11, 25, 10, 0, tzinfo=UTC), duration_ms=1_860_000,
        tracks=[], audio_available=False, language="fr",
    )  # fmt: skip
    seg = TranscriptSegment(
        id=1, meeting_id="m", track=TrackKind.MIC, speaker=Speaker.ME,
        start_ms=3_725_000, end_ms=3_730_000, text="Je m'en occupe.",
    )  # fmt: skip
    md = export_markdown(m, [seg], [])
    assert md.startswith("# Réunion du ") and "Durée : 31 min" in md and "Langue : fr" in md
    assert "**[1:02:05] Moi** : Je m'en occupe." in md
    assert format_ts(65_000) == "01:05"
    assert "Pas de transcription" in export_markdown(m, [], [])


def test_profiles_and_language_helpers():
    assert recommend(4, False) == ModelProfileId.LIGHT
    assert recommend(16, False) == ModelProfileId.BALANCED
    assert recommend(None, False) == ModelProfileId.BALANCED
    assert recommend(8, True) == ModelProfileId.ACCURATE
    assert pick_language([("de", 0.6), ("en", 0.3), ("fr", 0.1)], ("fr", "en")) == "en"
    assert pick_language([("de", 1.0)], ("fr", "en")) is None


# ---- model manager ----------------------------------------------------------------------
def test_model_download_is_explicit_and_only_then_allows_network(tmp_path: Path):
    from hark_engine.net import guard

    seen: dict[str, Any] = {}
    present = {"yes": False}

    def resolver(name: str, models_dir: Path, local_only: bool) -> str:
        if local_only:
            if not present["yes"]:
                raise OSError("not cached")
            return "/models/x"
        seen["depth"] = guard._allow_depth  # network must be allowed during the download only
        present["yes"] = True
        return "/models/x"

    done = threading.Event()
    mm = ModelManager(tmp_path, resolver, on_installed=lambda p: done.set())
    assert not mm.installed(ModelProfileId.LIGHT) and mm.status().state == "idle"
    mm.start_download(ModelProfileId.LIGHT)
    assert done.wait(3)
    assert seen["depth"] >= 1 and guard._allow_depth == 0
    assert mm.installed(ModelProfileId.LIGHT) and mm.status().state == "done"


def test_model_download_error_is_reported(tmp_path: Path):
    def resolver(name: str, models_dir: Path, local_only: bool) -> str:
        raise OSError("offline")

    mm = ModelManager(tmp_path, resolver)
    mm.start_download(ModelProfileId.BALANCED)
    for _ in range(100):
        if mm.status().state != "downloading":
            break
        time.sleep(0.02)
    assert mm.status().state == "error" and "offline" in (mm.status().error or "")


# ---- network guard ------------------------------------------------------------------------
@pytest.fixture
def guard_on():
    install_guard()
    yield
    uninstall_guard()


def test_guard_blocks_non_loopback_and_allows_loopback(guard_on):
    with socket.socket() as s, pytest.raises(NetworkBlockedError):
        s.connect(("203.0.113.9", 443))  # TEST-NET-3: never reached, blocked before connecting
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("example.com", 443)
    assert "203.0.113.9" in blocked_attempts()[0]
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    with socket.socket() as c:
        c.connect(server.getsockname())  # loopback is fine
    server.close()
    socket.getaddrinfo("localhost", 80)


def test_guard_allow_network_context_lifts_the_block(guard_on):
    with allow_network(), socket.socket() as s:
        s.settimeout(0.05)
        try:
            s.connect(("203.0.113.9", 443))
        except NetworkBlockedError:  # pragma: no cover
            pytest.fail("allow_network() must not block")
        except OSError:
            pass  # unreachable in the test sandbox: that is not the guard
    assert blocked_attempts() == []


def test_full_flow_makes_no_outbound_connection(db: Database, tmp_path: Path, guard_on):
    """Record → transcribe → search → export, with the guard on: zero blocked attempts."""
    e = Env(db, tmp_path)
    app = create_app(db, TOKEN, e.bus, transcription=e.service, models=e.models)
    e.service.start()
    try:
        with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as c:
            mid = make_meeting(e.repo, e.audio, title="Budget Q1")
            e.bus.publish(
                EventType.MEETING_RECORDED, {"meeting": e.repo.get(mid).model_dump(mode="json")}
            )
            e.wait(mid, TranscriptionStatus.DONE)
            assert c.get("/v1/search", params={"q": "budget"}).json()
            assert "Transcription" in c.get(f"/v1/meetings/{mid}/export.md").text
    finally:
        e.service.stop()
    assert blocked_attempts() == []
