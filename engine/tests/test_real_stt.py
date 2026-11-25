"""Opt-in integration test with the real faster-whisper (downloads the smallest model once).

Run on a machine with internet access:  HARK_TEST_REAL_STT=1 uv run pytest tests/test_real_stt.py -s
Uses a synthetic tone only (no real meeting data); the model download is the only network use.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from hark_engine.models import ModelProfileId
from hark_engine.stt import FasterWhisperTranscriber, ModelManager

pytestmark = pytest.mark.skipif(
    os.environ.get("HARK_TEST_REAL_STT") != "1", reason="set HARK_TEST_REAL_STT=1 to run"
)


def test_real_model_download_then_offline_transcription(tmp_path: Path):
    manager = ModelManager(tmp_path / "models")
    manager.start_download(ModelProfileId.LIGHT)
    for _ in range(600):
        if manager.status().state != "downloading":
            break
        time.sleep(1)
    assert manager.status().state == "done", manager.status().error
    assert manager.installed(ModelProfileId.LIGHT)

    wav = tmp_path / "tone.wav"
    t = np.arange(16000 * 3) / 16000
    sf.write(
        str(wav), (0.05 * np.sin(2 * np.pi * 440 * t)).astype("float32"), 16000, subtype="PCM_16"
    )
    progress: list[float] = []
    segments, language = FasterWhisperTranscriber(manager).transcribe(
        wav, ModelProfileId.LIGHT, "auto", progress.append
    )
    assert language in ("fr", "en") or isinstance(language, str)
    assert isinstance(segments, list) and progress[-1] == 1.0
