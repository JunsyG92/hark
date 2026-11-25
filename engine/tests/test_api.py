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
    assert ok.json() == {"ok": True, "recording_started": False}
