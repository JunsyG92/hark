"""Real HTTP server (uvicorn) to verify the SSE stream end to end."""

from __future__ import annotations

import json
import socket
import threading
import time

import httpx
import uvicorn

from hark_engine.api import create_app
from hark_engine.events import EventBus
from hark_engine.models import EventType
from hark_engine.store import Database

TOKEN = "t" * 32


def test_sse_delivers_meeting_detected_and_requires_token():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    db, bus = Database(":memory:"), EventBus()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(db, TOKEN, bus),
            host="127.0.0.1",
            port=port,
            log_level="error",
            timeout_graceful_shutdown=1,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    base = f"http://127.0.0.1:{port}"
    try:
        assert httpx.get(f"{base}/v1/events/stream").status_code == 401
        with httpx.stream(
            "GET",
            f"{base}/v1/events/stream",
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=5,
        ) as resp:
            lines = resp.iter_lines()
            assert next(lines) == ": connected"
            bus.publish(EventType.MEETING_DETECTED, {"prompt_id": "abc", "app": "Teams"})
            got = {}
            for line in lines:
                if line.startswith("event: "):
                    got["event"] = line[7:]
                if line.startswith("data: "):
                    got["data"] = json.loads(line[6:])
                    break
        assert got["event"] == "meeting.detected" and got["data"]["data"]["prompt_id"] == "abc"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        db.close()
