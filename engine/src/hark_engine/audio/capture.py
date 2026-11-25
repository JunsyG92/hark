"""Frame sources used for recording (16 kHz mono float32 blocks)."""

from __future__ import annotations

import math
import threading
from collections.abc import Iterator
from typing import Any, Protocol

import numpy as np

from ..models import TrackKind
from .source import BLOCK_SECONDS, SAMPLE_RATE, AudioUnavailableError, _load_soundcard

BLOCK_FRAMES = int(SAMPLE_RATE * BLOCK_SECONDS)


class FrameSource(Protocol):
    def probe(self) -> None:
        """Raise AudioUnavailableError if this device cannot be opened right now."""
        ...

    def frames(self, stop: threading.Event) -> Iterator[Any]:
        """Yield float32 mono blocks until `stop` is set."""
        ...


class SoundcardFrameSource:
    """System output (loopback) or microphone, via `soundcard`."""

    def __init__(self, kind: TrackKind) -> None:
        self.kind = kind

    def _device(self) -> Any:
        sc = _load_soundcard()
        try:
            if self.kind is TrackKind.SYSTEM:
                return sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
            mic = sc.default_microphone()
        except Exception as exc:
            raise AudioUnavailableError(f"{self.kind.value}: {type(exc).__name__}: {exc}") from exc
        if mic is None:
            raise AudioUnavailableError("no microphone found")
        return mic

    def probe(self) -> None:
        self._device()

    def frames(self, stop: threading.Event) -> Iterator[Any]:
        with self._device().recorder(
            samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK_FRAMES
        ) as rec:
            while not stop.is_set():
                data = rec.record(numframes=BLOCK_FRAMES)
                yield np.asarray(data, dtype=np.float32).reshape(-1)


class SyntheticFrameSource:
    """Dev/e2e only (HARK_FAKE_AUDIO=1): real-time paced tone or near-silence. No device needed."""

    def __init__(self, kind: TrackKind) -> None:
        self.kind = kind

    def probe(self) -> None:
        return None

    def frames(self, stop: threading.Event) -> Iterator[Any]:
        n = 0
        amp = 0.1 if self.kind is TrackKind.SYSTEM else 0.0003
        while not stop.is_set():
            t = (np.arange(BLOCK_FRAMES) + n * BLOCK_FRAMES) / SAMPLE_RATE
            yield (amp * np.sin(2 * math.pi * 440 * t)).astype(np.float32)
            n += 1
            stop.wait(BLOCK_SECONDS)
