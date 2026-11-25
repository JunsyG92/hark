from __future__ import annotations

from fastapi.testclient import TestClient

from hark_engine.events import EventBus
from hark_engine.models import EventType


def test_health_is_public(anon: TestClient):
    assert anon.get("/health").json()["status"] == "ok"


def test_token_required(anon: TestClient):
    assert anon.get("/v1/tasks").status_code == 401
    r = anon.get("/v1/tasks", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_foreign_host_and_browser_origin_rejected(client: TestClient):
    assert client.get("/v1/tasks", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/v1/tasks", headers={"Origin": "https://evil.example"}).status_code == 403


def test_no_public_docs(anon: TestClient):
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert anon.get(path).status_code in (401, 404)


def test_crud_flow(client: TestClient, bus: EventBus):
    seen: list[str] = []
    bus.subscribe(lambda e: seen.append(e.type.value))

    r = client.post("/v1/tasks", json={"title": "Préparer la démo", "priority": "high"})
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["column"] == "todo" and task["source"] == "manual"

    r = client.patch(f"/v1/tasks/{task['id']}", json={"assignee": "Moi", "due": "2026-12-01"})
    assert r.json()["assignee"] == "Moi" and r.json()["due"] == "2026-12-01"

    r = client.post(f"/v1/tasks/{task['id']}/move", json={"column": "in_progress", "index": 0})
    assert r.json()["column"] == "in_progress"

    assert client.delete(f"/v1/tasks/{task['id']}").status_code == 204
    assert client.get(f"/v1/tasks/{task['id']}").status_code == 404
    assert seen == [EventType.TASK_UPDATED.value] * 4


def test_strict_validation(client: TestClient):
    assert client.post("/v1/tasks", json={"title": ""}).status_code == 422
    assert client.post("/v1/tasks", json={"title": "x", "evil": 1}).status_code == 422
    assert client.post("/v1/tasks", json={"title": "x" * 201}).status_code == 422
    assert client.post("/v1/tasks", json={"title": "x", "column": "nope"}).status_code == 422


def test_propose_cannot_choose_column(client: TestClient, bus: EventBus):
    seen = []
    bus.subscribe(seen.append, {EventType.TASK_PROPOSED})
    r = client.post("/v1/tasks/propose", json={"title": "Relancer Paul"})
    assert r.status_code == 201
    assert r.json()["column"] == "to_validate"
    assert (
        client.post("/v1/tasks/propose", json={"title": "x", "column": "done"}).status_code == 422
    )
    assert len(seen) == 1


def test_detection_endpoints_scopes_and_validation(client: TestClient, anon: TestClient):
    assert anon.get("/v1/detection/status").status_code == 401
    assert client.get("/v1/detection/status").json()["phase"] == "idle"
    s = client.patch("/v1/settings/detection", json={"min_seconds": 5, "threshold_db": -50})
    assert s.json()["min_seconds"] == 5
    assert client.get("/v1/settings/detection").json()["threshold_db"] == -50
    assert client.patch("/v1/settings/detection", json={"min_seconds": 0}).status_code == 422
    assert client.patch("/v1/settings/detection", json={"evil": 1}).status_code == 422
    assert (
        client.post("/v1/detection/respond", json={"prompt_id": "x", "action": "nope"}).status_code
        == 422
    )


def test_test_prompt_then_respond_flow(client: TestClient, bus: EventBus):
    seen = []
    bus.subscribe(seen.append, {EventType.MEETING_DETECTED})
    assert client.post("/v1/detection/test").json() == {"prompted": True}
    assert client.post("/v1/detection/test").json() == {"prompted": False}  # one at a time
    pid = seen[0].data["prompt_id"]
    wrong = client.post("/v1/detection/respond", json={"prompt_id": "zzz", "action": "record"})
    assert wrong.json()["ok"] is False
    ok = client.post("/v1/detection/respond", json={"prompt_id": pid, "action": "decline"})
    assert ok.json() == {"ok": True, "recording_started": False, "error": None}


def test_recording_endpoints_scopes_and_errors(client: TestClient, anon: TestClient):
    assert anon.get("/v1/recording/status").status_code == 401
    assert anon.post("/v1/recording/start", json={}).status_code == 401
    assert client.get("/v1/recording/status").json()["recording"] is False
    # no audio device in the default test app: explicit, readable error (nothing recorded)
    r = client.post("/v1/recording/start", json={"title": "x"})
    assert r.status_code == 503 and "audio" in r.json()["detail"]
    assert client.post("/v1/recording/stop").status_code == 409
    assert client.post("/v1/recording/start", json={"evil": 1}).status_code == 422
    assert client.get("/v1/meetings").json() == []
    assert client.get("/v1/meetings/unknown").status_code == 404
    assert client.patch("/v1/meetings/unknown", json={"title": "t"}).status_code == 404
    assert client.patch("/v1/settings/recording", json={"silence_minutes": 0}).status_code == 422
    assert (
        client.patch("/v1/settings/recording", json={"silence_minutes": 5}).json()[
            "silence_minutes"
        ]
        == 5
    )
    assert client.get("/v1/settings/recording").json()["silence_minutes"] == 5


def test_accepting_the_prompt_starts_recording_with_fake_audio(db, bus, tmp_path):
    from hark_engine.api import create_app
    from hark_engine.record import Recorder
    from hark_engine.store import MeetingRepository, SettingsRepository
    from tests.test_recorder import FakeSource, TrackKind  # noqa: PLC0415

    rec = Recorder(
        MeetingRepository(db),
        SettingsRepository(db),
        bus,
        tmp_path,
        {TrackKind.SYSTEM: FakeSource(3)},
    )
    c = TestClient(
        create_app(db, "tok", bus, recorder=rec), headers={"Authorization": "Bearer tok"}
    )
    seen = []
    bus.subscribe(seen.append, {EventType.MEETING_DETECTED})
    c.post("/v1/detection/test")
    pid = seen[0].data["prompt_id"]
    result = c.post("/v1/detection/respond", json={"prompt_id": pid, "action": "record"}).json()
    assert result == {"ok": True, "recording_started": True, "error": None}
    assert c.get("/v1/detection/status").json()["phase"] == "recording"
    assert c.get("/v1/recording/status").json()["recording"] is True
    stopped = c.post("/v1/recording/stop").json()
    assert stopped["status"] == "recorded"
    assert c.get("/v1/detection/status").json()["phase"] == "cooldown"  # no immediate re-prompt
    assert (
        c.patch(f"/v1/meetings/{stopped['id']}", json={"title": "Revue"}).json()["title"] == "Revue"
    )


def test_history_endpoints(db, bus, tmp_path):
    from hark_engine.api import create_app
    from tests.test_transcription import Env, make_meeting  # noqa: PLC0415

    e = Env(db, tmp_path)
    app = create_app(db, "tok", e.bus, transcription=e.service, models=e.models)
    e.service.start()
    c = TestClient(app, headers={"Authorization": "Bearer tok"})
    anon = TestClient(app)
    try:
        mid = make_meeting(e.repo, e.audio, title="Point budget")
        e.service.submit(mid)
        for _ in range(100):
            if e.repo.get(mid).transcription.value == "done":
                break
            __import__("time").sleep(0.03)
        assert anon.get("/v1/search?q=budget").status_code == 401
        assert c.get("/v1/search", params={"q": "budget"}).json()[0]["meeting_id"] == mid
        assert c.get("/v1/search", params={"q": ""}).json() == []
        seg = c.get(f"/v1/meetings/{mid}/transcript").json()
        assert [s["speaker"] for s in seg] == ["others", "me"]
        assert c.get("/v1/meetings/unknown/transcript").status_code == 404
        md = c.get(f"/v1/meetings/{mid}/export.md")
        assert (
            md.headers["content-type"].startswith("text/markdown") and "# Point budget" in md.text
        )
        task = c.post("/v1/tasks/propose", json={"title": "Envoyer le budget"}).json()
        assert task["column"] == "to_validate"
        assert c.get("/v1/meetings").json()[0]["transcription"] == "done"
        assert c.post(f"/v1/meetings/{mid}/transcribe").status_code == 409  # audio already deleted
        assert anon.delete(f"/v1/meetings/{mid}").status_code == 401
        assert c.delete(f"/v1/meetings/{mid}").status_code == 204
        assert c.get(f"/v1/meetings/{mid}").status_code == 404
    finally:
        e.service.stop()


def test_models_and_transcription_settings_endpoints(client: TestClient, anon: TestClient):
    assert anon.get("/v1/models").status_code == 401
    models = client.get("/v1/models").json()
    assert [m["id"] for m in models] == ["light", "balanced", "accurate", "best"]
    assert sum(m["recommended"] for m in models) == 1 and not any(m["installed"] for m in models)
    assert client.get("/v1/settings/transcription").json()["retention_days"] == 0
    ok = client.patch("/v1/settings/transcription", json={"retention_days": 30, "language": "fr"})
    assert ok.json()["retention_days"] == 30 and ok.json()["language"] == "fr"
    assert client.patch("/v1/settings/transcription", json={"retention_days": 5}).status_code == 422
    assert client.patch("/v1/settings/transcription", json={"language": "de"}).status_code == 422
    assert client.patch("/v1/settings/transcription", json={"profile": "huge"}).status_code == 422
    assert client.post("/v1/models/download", json={"profile": "nope"}).status_code == 422
    assert anon.post("/v1/models/download", json={"profile": "light"}).status_code == 401
    st = client.get("/v1/transcription/status").json()
    assert st["queue"] == [] and st["model_installed"] is False


def test_analysis_profile_llm_and_cloud_endpoints(db, bus, tmp_path):
    from hark_engine.api import create_app

    app = create_app(db, "tok", bus, data_dir=tmp_path)
    c = TestClient(app, headers={"Authorization": "Bearer tok"})
    anon = TestClient(app)
    for path in (
        "/v1/profile",
        "/v1/settings/llm",
        "/v1/settings/cloud",
        "/v1/llm/models",
        "/v1/analysis/status",
    ):
        assert anon.get(path).status_code == 401
    # profile.yaml
    assert "nicknames" in c.get("/v1/profile").json()["yaml"]
    ok = c.put("/v1/profile", json={"yaml": 'name: "Mathieu Nesseir"\nnicknames: [Mat]\n'})
    assert (
        ok.json()["profile"]["name"] == "Mathieu Nesseir" and (tmp_path / "profile.yaml").exists()
    )
    bad = c.put("/v1/profile", json={"yaml": "unknown: 1"})
    assert bad.status_code == 422 and "unknown" in bad.json()["detail"]
    assert c.put("/v1/profile", json={"yaml": "name: [1"}).status_code == 422
    assert anon.put("/v1/profile", json={"yaml": ""}).status_code == 401
    assert c.get("/v1/profile").json()["profile"]["name"] == "Mathieu Nesseir"
    # LLM settings
    assert c.get("/v1/settings/llm").json()["provider"] == "ollama"
    assert (
        c.patch("/v1/settings/llm", json={"model": "llama3.1:8b", "chunk_tokens": 2000}).json()[
            "model"
        ]
        == "llama3.1:8b"
    )
    assert (
        c.patch("/v1/settings/llm", json={"ollama_url": "http://example.com:11434"}).status_code
        == 422
    )
    assert c.patch("/v1/settings/llm", json={"chunk_tokens": 10}).status_code == 422
    assert c.patch("/v1/settings/llm", json={"provider": "other"}).status_code == 422
    # cloud: off by default, cannot be enabled without acknowledgement, key never returned
    view = c.get("/v1/settings/cloud").json()
    assert view == {
        "enabled": False,
        "acknowledged": False,
        "base_url": "",
        "model": "",
        "has_key": False,
    }
    assert c.patch("/v1/settings/cloud", json={"enabled": True}).status_code == 422
    assert c.put("/v1/settings/cloud/key", json={"key": "short"}).status_code == 422
    assert c.put("/v1/settings/cloud/key", json={"key": "sk-secret-123456"}).status_code == 204
    after = c.patch(
        "/v1/settings/cloud",
        json={
            "acknowledged": True,
            "enabled": True,
            "base_url": "https://x.example/v1",
            "model": "m",
        },
    )
    assert after.json()["has_key"] is True and "sk-secret" not in after.text
    assert anon.put("/v1/settings/cloud/key", json={"key": "sk-secret-123456"}).status_code == 401
    # models, pull validation, status, analysis routes
    models = c.get("/v1/llm/models").json()
    assert [m["id"] for m in models] == ["light", "balanced", "accurate"]
    assert sum(m["recommended"] for m in models) == 1
    assert c.post("/v1/llm/pull", json={"model": "bad name; rm -rf"}).status_code == 422
    assert anon.post("/v1/llm/pull", json={"model": "qwen2.5:3b"}).status_code == 401
    st = c.get("/v1/analysis/status").json()
    assert st["queue"] == [] and st["pull"]["state"] == "idle" and "model" in st
    assert c.get("/v1/meetings/unknown/analysis").status_code == 404
    assert c.post("/v1/meetings/unknown/analyze").status_code == 404


def test_analyze_needs_a_transcript_and_analysis_404_until_done(db, bus, tmp_path):
    from hark_engine.api import create_app
    from hark_engine.models import MeetingStatus
    from hark_engine.store import MeetingRepository

    repo = MeetingRepository(db)
    repo.create("m1", "t", "", {})
    repo.finish("m1", MeetingStatus.RECORDED, 1000)
    c = TestClient(
        create_app(db, "tok", bus, data_dir=tmp_path), headers={"Authorization": "Bearer tok"}
    )
    assert c.get("/v1/meetings/m1/analysis").status_code == 404
    assert c.post("/v1/meetings/m1/analyze").status_code == 409
    assert c.get("/v1/meetings").json()[0]["analysis"] == "none"
