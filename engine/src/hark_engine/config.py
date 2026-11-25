"""Runtime configuration and data directory resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Hark"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 47821


def default_data_dir() -> Path:
    override = os.environ.get("HARK_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(user_data_dir(APP_NAME, appauthor=False))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=default_data_dir)
    port: int = DEFAULT_PORT
    # The API only ever binds to loopback. This is not configurable on purpose.
    host: str = LOOPBACK_HOST

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hark.sqlite3"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def runtime_file(self) -> Path:
        """Discovery file for local clients (port only, never the token)."""
        return self.data_dir / "runtime.json"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
