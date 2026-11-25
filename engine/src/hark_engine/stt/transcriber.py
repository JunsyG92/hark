"""Speech-to-text engines. Real: faster-whisper (local). Fake: deterministic, for tests/dev."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..models import ModelProfileId
from .models import ModelManager
from .profiles import PROFILES, has_cuda

log = logging.getLogger(__name__)

ALLOWED_AUTO_LANGUAGES = ("fr", "en")


class ModelNotInstalledError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawSegment:
    start: float  # seconds
    end: float
    text: str


class Transcriber(Protocol):
    def ready(self, profile: ModelProfileId) -> bool:
        """True if the model for this profile is available locally."""
        ...

    def transcribe(
        self,
        path: Path,
        profile: ModelProfileId,
        language: str,
        on_progress: Callable[[float], None],
    ) -> tuple[list[RawSegment], str]:
        """Return (segments, language). `language` is "auto", "fr" or "en"."""
        ...

    def unload(self) -> None: ...


def pick_language(all_probs: list[tuple[str, float]], allowed: tuple[str, ...]) -> str | None:
    """Most probable language among the allowed ones (fr/en), None if none was scored."""
    best: tuple[str, float] | None = None
    for lang, prob in all_probs:
        if lang in allowed and (best is None or prob > best[1]):
            best = (lang, prob)
    return best[0] if best else None


SAMPLE_RATE = 16_000


def load_audio(path: Path) -> Any:
    """Our recordings are already 16 kHz WAV: read them directly (no PyAV/ffmpeg decoder).

    faster-whisper's own decoder breaks with some PyAV releases (e.g. `metadata_errors` removed in
    PyAV 19), and handing it a float32 array avoids that code path entirely.
    """
    import numpy as np
    import soundfile as sf

    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
    if rate != SAMPLE_RATE and len(mono):  # not produced by Hark; keep it robust anyway
        target = int(len(mono) * SAMPLE_RATE / rate)
        mono = np.interp(np.linspace(0, len(mono) - 1, target), np.arange(len(mono)), mono)
    return np.ascontiguousarray(mono, dtype=np.float32)


class FasterWhisperTranscriber:
    """Local transcription with faster-whisper. Loads model files only (local_files_only)."""

    def __init__(self, models: ModelManager) -> None:
        self._models = models
        self._lock = threading.Lock()
        self._loaded: tuple[ModelProfileId, Any] | None = None

    def ready(self, profile: ModelProfileId) -> bool:
        return self._models.installed(profile)

    def _model(self, profile: ModelProfileId) -> Any:
        if self._loaded and self._loaded[0] == profile:
            return self._loaded[1]
        path = self._models.path(profile)
        if path is None:
            raise ModelNotInstalledError(PROFILES[profile].whisper_model)
        from faster_whisper import WhisperModel

        gpu = has_cuda()
        log.info("loading %s on %s", PROFILES[profile].whisper_model, "cuda" if gpu else "cpu")
        model = WhisperModel(
            path,
            device="cuda" if gpu else "cpu",
            compute_type="float16" if gpu else "int8",
            local_files_only=True,
        )
        self._loaded = (profile, model)
        return model

    def transcribe(
        self,
        path: Path,
        profile: ModelProfileId,
        language: str,
        on_progress: Callable[[float], None],
    ) -> tuple[list[RawSegment], str]:
        with self._lock:
            model = self._model(profile)
            audio = load_audio(path)
            lang: str | None = None if language == "auto" else language
            if lang is None:
                try:
                    _, _, probs = model.detect_language(audio)
                    lang = pick_language(list(probs), ALLOWED_AUTO_LANGUAGES)
                except Exception:
                    log.warning("language detection failed; letting whisper decide")
            segments, info = model.transcribe(
                audio,
                language=lang,
                vad_filter=True,  # skips silence (the mic track is mostly silent)
                vad_parameters={"min_silence_duration_ms": 500},
                beam_size=5,
                condition_on_previous_text=False,
            )
            out: list[RawSegment] = []
            total = max(float(info.duration), 0.001)
            for seg in segments:  # lazy: this is where the work happens
                text = seg.text.strip()
                if text:
                    out.append(RawSegment(float(seg.start), float(seg.end), text))
                on_progress(min(1.0, float(seg.end) / total))
            on_progress(1.0)
            return out, str(info.language)

    def unload(self) -> None:
        with self._lock:
            self._loaded = None  # frees RAM between meetings


class FakeTranscriber:
    """Deterministic synthetic transcript (HARK_FAKE_STT=1 and tests). No model needed."""

    def __init__(self, texts: dict[str, list[str]] | None = None) -> None:
        self.texts = texts or {}
        self.calls: list[tuple[str, str]] = []

    def ready(self, profile: ModelProfileId) -> bool:
        return True

    def transcribe(
        self,
        path: Path,
        profile: ModelProfileId,
        language: str,
        on_progress: Callable[[float], None],
    ) -> tuple[list[RawSegment], str]:
        self.calls.append((path.stem, language))
        lines = self.texts.get(path.stem) or (
            ["Bonjour à tous, on commence le point budget."]
            if path.stem == "system"
            else ["Je m'occupe du budget Q1."]
        )
        offset = 4.0 if path.stem == "mic" else 0.0  # the other side speaks first
        segs = [
            RawSegment(offset + i * 8.0, offset + i * 8.0 + 3.0, t) for i, t in enumerate(lines)
        ]
        on_progress(1.0)
        return segs, "fr" if language == "auto" else language

    def unload(self) -> None:
        return None
