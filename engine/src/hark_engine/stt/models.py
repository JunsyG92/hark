"""Whisper model files: where they live, whether they are installed, explicit download.

Transcription only ever loads local files. Downloading is a separate, explicit user action; it is
the only place the engine is allowed to use the network (see net.guard.allow_network).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..models import DownloadStatus, ModelProfileId
from ..net import allow_network
from .profiles import PROFILES

log = logging.getLogger(__name__)

# (whisper model name, models dir, local_files_only) -> local path; raises if absent
Resolver = Callable[[str, Path, bool], str]


def _faster_whisper_resolver(name: str, models_dir: Path, local_only: bool) -> str:
    from faster_whisper.utils import download_model

    return str(download_model(name, local_files_only=local_only, cache_dir=str(models_dir)))


class ModelManager:
    def __init__(
        self,
        models_dir: Path,
        resolver: Resolver = _faster_whisper_resolver,
        on_installed: Callable[[ModelProfileId], None] | None = None,
    ) -> None:
        self.models_dir = models_dir
        self._resolver = resolver
        self.on_installed = on_installed
        self._lock = threading.Lock()
        self._status = DownloadStatus(state="idle")

    def path(self, profile: ModelProfileId) -> str | None:
        """Local directory of the model, or None if not downloaded. Never touches the network."""
        try:
            return self._resolver(PROFILES[profile].whisper_model, self.models_dir, True)
        except Exception:
            return None

    def installed(self, profile: ModelProfileId) -> bool:
        return self.path(profile) is not None

    def status(self) -> DownloadStatus:
        with self._lock:
            return self._status

    def start_download(self, profile: ModelProfileId) -> DownloadStatus:
        """Download in the background. Returns immediately; poll `status()`."""
        with self._lock:
            if self._status.state == "downloading":
                return self._status
            self._status = DownloadStatus(state="downloading", profile=profile)
        threading.Thread(
            target=self._download, args=(profile,), daemon=True, name="model-download"
        ).start()
        return self.status()

    def _download(self, profile: ModelProfileId) -> None:
        name = PROFILES[profile].whisper_model
        try:
            self.models_dir.mkdir(parents=True, exist_ok=True)
            with allow_network(), _hf_online():
                self._resolver(name, self.models_dir, False)
            with self._lock:
                self._status = DownloadStatus(state="done", profile=profile)
            log.info("model %s downloaded", name)
            if self.on_installed:
                self.on_installed(profile)
        except Exception as exc:
            log.warning("model download failed: %s", exc)
            with self._lock:
                self._status = DownloadStatus(
                    state="error", profile=profile, error=f"{type(exc).__name__}: {exc}"[:300]
                )


class _hf_online:  # noqa: N801 - context manager, lowercase on purpose
    """huggingface_hub reads HF_HUB_OFFLINE once at import: flip its constant for a download."""

    def __init__(self) -> None:
        self._constants: Any = None
        self._previous = True

    def __enter__(self) -> None:
        try:
            from huggingface_hub import constants
        except ImportError:  # pragma: no cover
            return
        self._constants = constants
        self._previous = constants.HF_HUB_OFFLINE
        constants.HF_HUB_OFFLINE = False

    def __exit__(self, *exc: object) -> None:
        if self._constants is not None:
            self._constants.HF_HUB_OFFLINE = self._previous
