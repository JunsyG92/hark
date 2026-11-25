"""Engine entrypoint.

Started by the desktop app as a sidecar. Protocol on stdout (one JSON line):

    {"event": "ready", "port": 47821, "token": "<master token>", "version": "..."}

stdout is reserved for that handshake; logs go to stderr. The token travels
over the parent's pipe only — never over the network or a file readable by
other users. Local clients (MCP, plugins) discover the port via runtime.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn

from . import __version__
from .api import create_app
from .audio.capture import FrameSource, SoundcardFrameSource, SyntheticFrameSource
from .audio.source import SoundcardLoopbackSource
from .auth import load_or_create_master_token
from .config import DEFAULT_PORT, LOOPBACK_HOST, Settings, default_data_dir
from .detect import DetectorService
from .detect.probes import default_probe
from .events import EventBus
from .models import TrackKind
from .record import Recorder
from .store import Database, MeetingRepository, SettingsRepository

log = logging.getLogger("hark")


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((LOOPBACK_HOST, port))
        except OSError:
            return False
    return True


def _pick_port(preferred: int) -> int:
    if preferred and _port_free(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((LOOPBACK_HOST, 0))
        return int(s.getsockname()[1])


def _watch_parent_stdin(on_eof: Callable[[], None]) -> None:
    """Shut down gracefully when the parent (desktop app) closes our stdin, i.e. it quit or died."""

    def run() -> None:
        try:
            while sys.stdin.read(1):
                pass
        finally:
            on_eof()

    threading.Thread(target=run, daemon=True, name="parent-watch").start()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="hark-engine")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--port", type=int, default=int(os.environ.get("HARK_PORT", DEFAULT_PORT)))
    parser.add_argument("--sidecar", action="store_true", help="exit when stdin closes")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s %(message)s"
    )

    port = _pick_port(args.port)
    settings = Settings(data_dir=args.data_dir, port=port)
    settings.ensure_dirs()
    token = load_or_create_master_token(settings.data_dir)
    db = Database(settings.db_path)
    bus = EventBus()
    detector = DetectorService(
        SettingsRepository(db),
        bus,
        source=SoundcardLoopbackSource() if os.environ.get("HARK_DETECT") != "0" else None,
        probe=default_probe(),
    )
    frame_cls = (
        SyntheticFrameSource if os.environ.get("HARK_FAKE_AUDIO") == "1" else SoundcardFrameSource
    )
    sources: dict[TrackKind, FrameSource] = {
        k: frame_cls(k) for k in (TrackKind.SYSTEM, TrackKind.MIC)
    }
    recorder = Recorder(
        MeetingRepository(db), SettingsRepository(db), bus, settings.audio_dir, sources
    )
    recovered = recorder.recover_interrupted()
    if recovered:
        log.warning("closed %d meeting(s) left open by a previous crash", recovered)
    app = create_app(db, token, bus, detector, recorder)
    detector.start()

    settings.runtime_file.write_text(
        json.dumps({"host": LOOPBACK_HOST, "port": port, "pid": os.getpid()}), encoding="utf-8"
    )

    config = uvicorn.Config(
        app, host=LOOPBACK_HOST, port=port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)

    original_startup = server.startup

    async def startup_with_handshake(sockets=None):  # type: ignore[no-untyped-def]
        await original_startup(sockets)
        print(
            json.dumps({"event": "ready", "port": port, "token": token, "version": __version__}),
            flush=True,
        )
        log.info("engine ready on http://%s:%d (data: %s)", LOOPBACK_HOST, port, settings.data_dir)

    server.startup = startup_with_handshake  # type: ignore[method-assign]
    if args.sidecar:
        _watch_parent_stdin(lambda: setattr(server, "should_exit", True))
    try:
        server.run()
    finally:
        recorder.stop()  # no-op if the API lifespan already finalized it
        detector.stop()
        db.close()
        settings.runtime_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
