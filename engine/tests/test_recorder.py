"""Recorder tests with synthetic audio only (no devices, no real meeting data)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from hark_engine.audio.capture import BLOCK_FRAMES
from hark_engine.audio.source import AudioUnavailableError
from hark_engine.events import EventBus
from hark_engine.models import EventType, MeetingStatus, TrackKind
from hark_engine.record import Recorder, RecorderBusy
from hark_engine.record.silence import SilenceEvent, SilenceTracker
from hark_engine.store import Database, MeetingRepository, SettingsRepository


def tone(amp: float = 0.1) -> Any:
    t = np.arange(BLOCK_FRAMES) / 16000
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


class FakeSource:
    """Yields a fixed number of blocks, then behaves like an open device until stopped."""

    def __init__(self, blocks: int, amp: float = 0.1, fail_after: int | None = None) -> None:
        self.blocks, self.amp, self.fail_after = blocks, amp, fail_after

    def probe(self) -> None:
        return None

    def frames(self, stop: threading.Event) -> Iterator[Any]:
        for i in range(self.blocks):
            if self.fail_after is not None and i >= self.fail_after:
                raise OSError("device unplugged")
            yield tone(self.amp)
        stop.wait(10)


class MissingSource:
    def probe(self) -> None:
        raise AudioUnavailableError("no microphone found")

    def frames(self, stop: threading.Event) -> Iterator[Any]:  # pragma: no cover
        yield from ()


@pytest.fixture
def parts(db: Database, tmp_path: Path):
    bus = EventBus()
    events: list = []
    bus.subscribe(events.append)
    repo = MeetingRepository(db)
    return db, bus, events, repo, tmp_path / "audio"


def make(parts, sources):
    db, bus, _, repo, audio = parts
    states: list[bool] = []
    rec = Recorder(repo, SettingsRepository(db), bus, audio, sources, on_state=states.append)
    return rec, states


def wait_frames(rec: Recorder, kind: TrackKind, n: int) -> None:
    for _ in range(200):
        s = rec._session
        if s and s.tracks[kind].frames >= n:
            return
        time.sleep(0.01)
    raise AssertionError("frames not written in time")


def test_records_two_wav_tracks_and_publishes_events(parts):
    _, _, events, repo, _ = parts
    rec, states = make(parts, {TrackKind.SYSTEM: FakeSource(8), TrackKind.MIC: FakeSource(8, 0.05)})
    meeting = rec.start(title="Point budget", app="Teams")
    assert meeting.status == MeetingStatus.RECORDING and meeting.title == "Point budget"
    wait_frames(rec, TrackKind.SYSTEM, 8 * BLOCK_FRAMES)
    wait_frames(rec, TrackKind.MIC, 8 * BLOCK_FRAMES)
    done = rec.stop()
    assert done is not None and done.status == MeetingStatus.RECORDED
    assert done.duration_ms == 2000  # 8 blocks x 0.25 s
    assert set(done.tracks) == {TrackKind.SYSTEM, TrackKind.MIC} and done.audio_available
    for path in repo.track_paths(done.id).values():
        info = sf.info(str(path))
        assert info.format == "WAV" and info.samplerate == 16000 and info.channels == 1
        assert abs(info.duration - 2.0) < 0.01
    kinds = [e.type for e in events]
    assert kinds == [EventType.MEETING_RECORDING_STARTED, EventType.MEETING_RECORDED]
    assert states == [True, False] and not rec.active


def test_only_one_recording_at_a_time_and_stop_is_idempotent(parts):
    rec, _ = make(parts, {TrackKind.SYSTEM: FakeSource(2)})
    rec.start()
    with pytest.raises(RecorderBusy):
        rec.start()
    assert rec.stop() is not None
    assert rec.stop() is None


def test_missing_microphone_still_records_system_with_warning(parts):
    rec, _ = make(parts, {TrackKind.SYSTEM: FakeSource(4), TrackKind.MIC: MissingSource()})
    meeting = rec.start()
    assert meeting.tracks == [TrackKind.SYSTEM]
    assert any("microphone" in w for w in rec.status().warnings)
    rec.stop()


def test_no_usable_device_refuses_to_start(parts):
    rec, states = make(parts, {TrackKind.SYSTEM: MissingSource()})
    with pytest.raises(AudioUnavailableError):
        rec.start()
    assert states == [] and not rec.active
    with pytest.raises(AudioUnavailableError):
        make(parts, {})[0].start()


def test_track_failure_keeps_partial_audio_and_other_track(parts):
    rec, _ = make(
        parts, {TrackKind.SYSTEM: FakeSource(6), TrackKind.MIC: FakeSource(10, fail_after=2)}
    )
    rec.start()
    wait_frames(rec, TrackKind.SYSTEM, 6 * BLOCK_FRAMES)
    for _ in range(100):
        if rec._session and rec._session.tracks[TrackKind.MIC].finished:
            break
        time.sleep(0.01)
    status = rec.status()
    assert any("device unplugged" in w for w in status.warnings)
    done = rec.stop()
    assert done and done.status == MeetingStatus.RECORDED and done.duration_ms == 1500


def test_levels_in_status_and_title_edit(parts):
    rec, _ = make(parts, {TrackKind.SYSTEM: FakeSource(4, 0.1)})
    meeting = rec.start()
    wait_frames(rec, TrackKind.SYSTEM, 4 * BLOCK_FRAMES)
    st = rec.status()
    assert st.recording and st.meeting_id == meeting.id and st.system_level_db is not None
    assert -25 < st.system_level_db < -20  # 0.1 amplitude sine ~ -23 dBFS
    parts[3].set_title(meeting.id, "Renommée")
    assert rec.status().title == "Renommée"
    rec.stop()


def test_silence_prompts_but_never_stops_and_voice_returns(parts):
    _, _, events, _, _ = parts
    rec, _ = make(parts, {TrackKind.SYSTEM: FakeSource(1, 0.0)})
    rec.start()
    session = rec._session
    assert session is not None
    session.tracker.silence_s = 180
    t0 = session.started
    for track in session.tracks.values():
        track.peak_db = -90  # silence
    rec._tick(session, t0 + 100)
    assert not [e for e in events if e.type == EventType.MEETING_SILENCE]
    rec._tick(session, t0 + 181)
    silence = [e for e in events if e.type == EventType.MEETING_SILENCE]
    assert len(silence) == 1 and silence[0].data["silent"] is True
    assert rec.active  # never stops by itself
    for track in session.tracks.values():
        track.peak_db = -20  # a voice is heard again
    rec._tick(session, t0 + 200)
    silence = [e for e in events if e.type == EventType.MEETING_SILENCE]
    assert silence[-1].data["silent"] is False
    rec.stop()


def test_silence_tracker_repeats_question_until_voice():
    t = SilenceTracker(180, now=0)
    assert t.feed(100, False) is None
    assert t.feed(181, False) == SilenceEvent.SILENT
    assert t.feed(200, False) is None  # already asked
    assert t.feed(362, False) == SilenceEvent.SILENT  # dismissed question comes back later
    assert t.feed(370, True) == SilenceEvent.VOICE_RETURNED
    assert t.feed(371, True) is None
    assert not t.prompted


def test_recover_interrupted_meeting(parts):
    db, bus, _, repo, audio = parts
    folder = audio / "crashed"
    folder.mkdir(parents=True)
    path = folder / "system.wav"
    with sf.SoundFile(str(path), "w", 16000, 1, format="WAV", subtype="PCM_16") as f:
        f.write(np.zeros(16000 * 3, dtype=np.float32))
    repo.create("crashed", "", "", {TrackKind.SYSTEM: path})
    empty = folder / "mic.wav"
    repo.create("empty", "", "", {TrackKind.MIC: empty})  # file never written
    rec, _ = make(parts, {})
    assert rec.recover_interrupted() == 2
    assert repo.get("crashed").status == MeetingStatus.RECORDED
    assert repo.get("crashed").duration_ms == 3000
    assert repo.get("empty").status == MeetingStatus.FAILED


def test_recover_after_real_crash_keeps_the_audio(parts):
    """A process killed mid-recording (no close) must not lose what was already on disk."""
    import subprocess
    import sys

    _, _, _, repo, audio = parts
    folder = audio / "live"
    folder.mkdir(parents=True)
    path = folder / "system.wav"
    code = (
        "import soundfile as sf, numpy as np, os\n"
        f"f = sf.SoundFile({str(path)!r}, 'w', 16000, 1, format='WAV', subtype='PCM_16')\n"
        "for _ in range(8):\n"
        "    f.write(np.zeros(4000, dtype='float32')); f.flush()\n"
        "os._exit(0)  # crash: close() never runs\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603
    repo.create("live", "", "", {TrackKind.SYSTEM: path})
    rec, _ = make(parts, {})
    assert rec.recover_interrupted() == 1
    meeting = repo.get("live")
    assert meeting.status == MeetingStatus.RECORDED and meeting.duration_ms == 2000


def test_graceful_shutdown_finalizes_recording(db, bus, tmp_path):
    """Leaving the app context (uvicorn lifespan shutdown) must stop and save the recording."""
    from fastapi.testclient import TestClient

    from hark_engine.api import create_app

    repo = MeetingRepository(db)
    rec = Recorder(repo, SettingsRepository(db), bus, tmp_path, {TrackKind.SYSTEM: FakeSource(4)})
    with TestClient(create_app(db, "tok", bus, recorder=rec)):
        rec.start(title="En cours")
        wait_frames(rec, TrackKind.SYSTEM, 4 * BLOCK_FRAMES)
    meeting = repo.list_recent()[0]
    assert meeting.status == MeetingStatus.RECORDED and meeting.duration_ms == 1000
    assert sf.info(str(next(tmp_path.rglob("system.wav")))).duration == 1.0
