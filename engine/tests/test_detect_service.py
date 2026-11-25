from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from hark_engine.detect import DetectorService
from hark_engine.detect.probes import MicStatus
from hark_engine.events import EventBus
from hark_engine.models import (
    DetectionPhase,
    DetectionSettingsPatch,
    EventType,
    PromptAction,
)
from hark_engine.store import Database, SettingsRepository


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class FakeSource:
    name = "fake"

    def __init__(self, levels: list[float]) -> None:
        self._levels = levels

    def levels(self, stop: threading.Event) -> Iterator[float]:
        yield from self._levels
        stop.wait(5)  # like a real device: keep the stream open


class BrokenSource:
    name = "broken"

    def levels(self, stop: threading.Event) -> Iterator[float]:
        raise RuntimeError("no audio device")
        yield 0.0  # pragma: no cover


@pytest.fixture
def parts(db: Database):
    clock = Clock()
    bus = EventBus()
    events: list = []
    bus.subscribe(events.append)
    svc = DetectorService(SettingsRepository(db), bus, clock=clock)
    return svc, clock, events


def drive(svc: DetectorService, clock: Clock, seconds: float, level: float) -> None:
    end = clock.t + seconds
    while clock.t < end:
        svc.feed_level(level)
        clock.t += 0.25


def test_call_emits_meeting_detected_with_consent_reminder(parts):
    svc, clock, events = parts
    svc._mic = MicStatus(True, ("Teams",))
    drive(svc, clock, 12, -28)
    detected = [e for e in events if e.type == EventType.MEETING_DETECTED]
    assert len(detected) == 1
    data = detected[0].data
    assert data["app"] == "Teams" and "informer" in data["reminder"]
    assert svc.status().phase == DetectionPhase.PROMPTED


def test_status_tells_why_there_is_no_notification(parts):
    svc, clock, events = parts
    svc._mic = MicStatus(False, ())
    drive(svc, clock, 3, -28)
    st = svc.status()
    assert "mic_not_in_use" in st.blockers and "waiting_duration" in st.blockers
    assert st.mic_in_use is False and st.mic_probe == "unsupported"


def test_unknown_mic_state_still_prompts_and_is_explained(parts):
    svc, clock, events = parts
    svc._mic = None  # probe unavailable (e.g. pactl missing)
    drive(svc, clock, 12, -28)
    assert len(events) == 1 and svc.status().mic_probe_error


def test_youtube_only_emits_nothing(parts):
    svc, clock, events = parts
    svc._mic = MicStatus(False, ())
    drive(svc, clock, 120, -28)
    assert events == [] and svc.status().phase == DetectionPhase.IDLE


def test_accept_without_recorder_does_not_claim_recording(parts):
    svc, clock, events = parts
    svc._mic = MicStatus(True, ("Zoom",))
    drive(svc, clock, 12, -28)
    pid = events[0].data["prompt_id"]
    result = svc.respond(pid, PromptAction.RECORD)
    assert result.ok and not result.recording_started
    assert svc.status().phase == DetectionPhase.COOLDOWN  # nothing was recorded


def test_accept_with_recorder_hook(parts):
    svc, clock, events = parts
    started = []
    svc.on_accept = lambda p: started.append(p.id) or True
    svc._mic = MicStatus(True, ("Zoom",))
    drive(svc, clock, 12, -28)
    result = svc.respond(events[0].data["prompt_id"], PromptAction.RECORD)
    assert result.recording_started and started
    assert svc.status().phase == DetectionPhase.RECORDING


def test_settings_patch_persists_and_applies(parts, db):
    svc, clock, events = parts
    svc.patch_settings(DetectionSettingsPatch(min_seconds=3, threshold_db=-60))
    assert SettingsRepository(db).get_detection().min_seconds == 3
    svc._mic = MicStatus(True, ("Teams",))
    drive(svc, clock, 5, -55)
    assert len(events) == 1
    svc.patch_settings(DetectionSettingsPatch(enabled=False))
    assert svc.status().phase == DetectionPhase.DISABLED


def test_meter_loop_consumes_source_and_reports_errors(db):
    bus = EventBus()
    svc = DetectorService(SettingsRepository(db), bus, source=FakeSource([-30.0, -31.0]))
    svc._stop.clear()
    t = threading.Thread(target=svc._meter_loop, daemon=True)
    t.start()
    for _ in range(50):
        if svc.status().level_db == -31.0:
            break
        t.join(timeout=0.05)
    svc._stop.set()
    assert svc.status().level_db == -31.0
    broken = DetectorService(SettingsRepository(db), bus, source=BrokenSource())
    broken._stop.clear()
    th = threading.Thread(target=broken._meter_loop, daemon=True)
    th.start()
    for _ in range(50):
        if broken.status().error:
            break
        th.join(timeout=0.05)
    broken._stop.set()
    assert "no audio device" in (broken.status().error or "")
