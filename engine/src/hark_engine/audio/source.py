"""System-output level sources (WASAPI loopback on Windows, Pulse/PipeWire monitor on Linux)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any, Protocol

from .levels import rms_dbfs

SAMPLE_RATE = 16_000
BLOCK_SECONDS = 0.25
DEVICE_CHECK_EVERY = 60  # blocks (~15 s)


class LevelSource(Protocol):
    name: str

    def levels(self, stop: threading.Event) -> Iterator[float]:
        """Yield one dBFS level per ~0.25 s block until `stop` is set. May raise on device loss."""
        ...


class AudioUnavailableError(RuntimeError):
    """The system audio cannot be observed (shown as-is in the settings screen)."""


def _load_soundcard() -> Any:
    try:
        import soundcard as sc  # lazy: needs libpulse / WASAPI at import time
    except Exception as exc:  # soundcard raises AssertionError/OSError when libpulse is missing
        raise AudioUnavailableError(
            "audio server not reachable (Linux: install libpulse and make sure PulseAudio or "
            f"PipeWire-Pulse is running; {type(exc).__name__})"
        ) from exc
    return sc


class SoundcardLoopbackSource:
    """Loopback of the default output device via `soundcard`. Audio is measured, never stored."""

    name = "system-output-loopback"

    def levels(self, stop: threading.Event) -> Iterator[float]:
        sc = _load_soundcard()
        try:
            speaker = sc.default_speaker()
            current = str(speaker.name)
            mic = sc.get_microphone(id=current, include_loopback=True)
        except Exception as exc:
            raise AudioUnavailableError(
                f"no output device to listen to ({type(exc).__name__}: {exc})"
            ) from exc
        frames = int(SAMPLE_RATE * BLOCK_SECONDS)
        count = 0
        with mic.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=frames) as rec:
            while not stop.is_set():
                data = rec.record(numframes=frames)
                yield rms_dbfs(data)
                count += 1
                if count % DEVICE_CHECK_EVERY == 0 and str(sc.default_speaker().name) != current:
                    return  # default output changed: caller reopens on the new device
