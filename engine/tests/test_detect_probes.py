from __future__ import annotations

import numpy as np

from hark_engine.audio.levels import SILENCE_DB, rms_dbfs
from hark_engine.detect.probes import (
    app_label_from_registry_name,
    default_probe,
    parse_pactl_sources,
    parse_source_outputs,
)

SOURCES = (
    "0\talsa_output.pci.analog-stereo.monitor\tPipeWire\ts16le\tRUNNING\n"
    "1\talsa_input.pci.analog-stereo\tPipeWire\ts16le\tIDLE\n"
)


def block(idx: str, source: str, name: str) -> str:
    return (
        f"Source Output #{idx}\n\tDriver: PipeWire\n\tSource: {source}\n"
        f'\tProperties:\n\t\tapplication.name = "{name}"\n'
        f'\t\tapplication.process.binary = "{name.lower()}"\n'
    )


def test_pactl_mic_stream_detected_and_monitor_ignored():
    sources = parse_pactl_sources(SOURCES)
    out = block("10", "1", "ZOOM VoiceEngine") + block("11", "0", "Hark Loopback")
    status = parse_source_outputs(out, sources)
    assert status.in_use and status.apps == ("ZOOM VoiceEngine",)


def test_pactl_only_monitor_or_own_streams_means_no_call():
    sources = parse_pactl_sources(SOURCES)
    assert not parse_source_outputs(block("1", "0", "Chromium"), sources).in_use  # monitor
    assert not parse_source_outputs(block("2", "1", "soundcard"), sources).in_use  # ourselves
    assert not parse_source_outputs("", sources).in_use


def test_windows_registry_names():
    assert app_label_from_registry_name("C:#Users#me#AppData#Local#Zoom#bin#Zoom.exe") == "Zoom"
    assert app_label_from_registry_name("MSTeams_8wekyb3d8bbwe") == "MSTeams"


def test_pactl_missing_is_reported_not_silent(monkeypatch):
    from hark_engine.detect.probes import PactlProbe

    def boom(*a, **k):
        raise FileNotFoundError("pactl")

    monkeypatch.setattr("hark_engine.detect.probes.subprocess.run", boom)
    probe = PactlProbe()
    assert probe.read() is None and "pulseaudio-utils" in (probe.last_error or "")


def test_default_probe_per_platform():
    assert default_probe("linux").name == "pactl"
    assert default_probe("win32").name == "windows-consent-store"
    assert default_probe("darwin").name == "unsupported"


def test_rms_dbfs_synthetic_signals():
    t = np.linspace(0, 1, 16000, endpoint=False)
    sine = 0.5 * np.sin(2 * np.pi * 440 * t)  # RMS 0.354 -> about -9 dBFS
    assert -9.5 < rms_dbfs(sine) < -8.5
    quiet = sine * 0.001
    assert rms_dbfs(quiet) < -60
    assert rms_dbfs(np.zeros(100)) == SILENCE_DB
    assert rms_dbfs([]) == SILENCE_DB


def test_missing_audio_server_gives_actionable_error(monkeypatch):
    import threading

    import pytest

    from hark_engine.audio import source

    def missing():
        raise source.AudioUnavailableError("audio server not reachable (Linux: install libpulse)")

    monkeypatch.setattr(source, "_load_soundcard", missing)
    with pytest.raises(source.AudioUnavailableError, match="libpulse"):
        next(source.SoundcardLoopbackSource().levels(threading.Event()))
