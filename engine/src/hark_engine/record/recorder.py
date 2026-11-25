"""Two-track recording (system output + microphone) to WAV (16 kHz mono PCM16).

WAV rather than FLAC on purpose: libsndfile cannot read back an unfinalized FLAC after a crash,
while a WAV is recoverable from its length. Each block is flushed so a crash loses < 1 s.

Only ever started by an explicit user action (consent toast "Enregistrer", tray menu, or the
Record button). It never stops by itself: silence only produces a question for the user.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import soundfile as sf

from ..audio.capture import FrameSource
from ..audio.levels import SILENCE_DB, rms_dbfs
from ..audio.source import SAMPLE_RATE, AudioUnavailableError
from ..events import EventBus
from ..models import (
    EventType,
    Meeting,
    MeetingStatus,
    RecordingStatus,
    TrackKind,
)
from ..store import MeetingRepository, SettingsRepository
from .silence import SilenceEvent, SilenceTracker

log = logging.getLogger(__name__)

MONITOR_INTERVAL_S = 0.5
JOIN_TIMEOUT_S = 3.0


def _count_frames(path: Path) -> int:
    """Real number of readable frames (an unfinalized header cannot be trusted)."""
    total = 0
    # missing/truncated file: keep what was decoded
    with contextlib.suppress(Exception), sf.SoundFile(str(path)) as f:
        while len(block := f.read(65536, dtype="int16")):
            total += len(block)
    return total


class RecorderBusy(RuntimeError):
    pass


@dataclass
class _Track:
    kind: TrackKind
    source: FrameSource
    path: Path
    writer: Any
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None
    level_db: float | None = None
    peak_db: float = SILENCE_DB
    frames: int = 0
    error: str | None = None
    finished: bool = False


@dataclass
class _Session:
    meeting: Meeting
    tracks: dict[TrackKind, _Track]
    tracker: SilenceTracker
    started: float
    warnings: list[str]
    stop: threading.Event = field(default_factory=threading.Event)
    monitor: threading.Thread | None = None
    stopping: bool = False


class Recorder:
    def __init__(
        self,
        meetings: MeetingRepository,
        settings: SettingsRepository,
        bus: EventBus,
        audio_dir: Path,
        sources: dict[TrackKind, FrameSource] | None = None,
        clock: Callable[[], float] = time.monotonic,
        on_state: Callable[[bool], None] | None = None,
    ) -> None:
        self._meetings = meetings
        self._settings = settings
        self._bus = bus
        self._audio_dir = audio_dir
        self._sources = sources or {}
        self._clock = clock
        self.on_state = on_state
        self._lock = threading.RLock()
        self._session: _Session | None = None

    # ---- start / stop ------------------------------------------------------------
    def start(self, title: str = "", app: str = "") -> Meeting:
        with self._lock:
            if self._session is not None:
                raise RecorderBusy("a recording is already in progress")
            warnings: list[str] = []
            usable: list[TrackKind] = []
            for kind, source in self._sources.items():
                try:
                    source.probe()
                    usable.append(kind)
                except AudioUnavailableError as exc:
                    warnings.append(f"{kind.value}: {exc}")
            if not usable:
                raise AudioUnavailableError("; ".join(warnings) or "no audio source configured")

            meeting_id = uuid.uuid4().hex
            folder = self._audio_dir / meeting_id
            folder.mkdir(parents=True, exist_ok=True)
            tracks: dict[TrackKind, _Track] = {}
            try:
                for kind in usable:
                    path = folder / f"{kind.value}.wav"
                    writer = sf.SoundFile(
                        str(path), "w", samplerate=SAMPLE_RATE, channels=1, format="WAV",
                        subtype="PCM_16",
                    )  # fmt: skip
                    tracks[kind] = _Track(kind, self._sources[kind], path, writer)
            except Exception:
                for t in tracks.values():
                    t.writer.close()
                raise
            meeting = self._meetings.create(
                meeting_id, title.strip(), app, {k: t.path for k, t in tracks.items()}
            )
            cfg = self._settings.get_recording()
            now = self._clock()
            session = _Session(
                meeting, tracks, SilenceTracker(cfg.silence_minutes * 60, now), now, warnings
            )
            for track in tracks.values():
                track.thread = threading.Thread(
                    target=self._capture, args=(session, track), daemon=True,
                    name=f"rec-{track.kind.value}",
                )  # fmt: skip
                track.thread.start()
            session.monitor = threading.Thread(
                target=self._monitor, args=(session,), daemon=True, name="rec-monitor"
            )
            session.monitor.start()
            self._session = session
        self._bus.publish(
            EventType.MEETING_RECORDING_STARTED,
            {"meeting": meeting.model_dump(mode="json")},
        )
        if self.on_state:
            self.on_state(True)
        return meeting

    def stop(self) -> Meeting | None:
        with self._lock:
            session = self._session
            if session is None or session.stopping:
                return None
            session.stopping = True
        session.stop.set()
        me = threading.current_thread()
        for t in [tr.thread for tr in session.tracks.values()] + [session.monitor]:
            if t is not None and t is not me:
                t.join(timeout=JOIN_TIMEOUT_S)
        for track in session.tracks.values():
            with track.lock:
                track.writer.close()
        frames = max((t.frames for t in session.tracks.values()), default=0)
        status = MeetingStatus.RECORDED if frames > 0 else MeetingStatus.FAILED
        meeting = self._meetings.finish(
            session.meeting.id, status, int(frames * 1000 / SAMPLE_RATE)
        )
        with self._lock:
            self._session = None
        self._bus.publish(EventType.MEETING_RECORDED, {"meeting": meeting.model_dump(mode="json")})
        if self.on_state:
            self.on_state(False)
        return meeting

    # ---- threads -------------------------------------------------------------------
    def _capture(self, session: _Session, track: _Track) -> None:
        try:
            for block in track.source.frames(session.stop):
                db = rms_dbfs(block)
                with track.lock:
                    if session.stop.is_set() and track.writer.closed:
                        break
                    track.writer.write(block)
                    track.writer.flush()
                    track.frames += len(block)
                track.level_db = db
                track.peak_db = max(track.peak_db, db)
                if session.stop.is_set():
                    break
        except Exception as exc:
            track.error = f"{type(exc).__name__}: {exc}"[:200]
            session.warnings.append(f"{track.kind.value}: {track.error}")
            log.warning("recording track %s failed: %s", track.kind.value, track.error)
        finally:
            track.finished = True
            track.level_db = None

    def _monitor(self, session: _Session) -> None:
        while not session.stop.wait(MONITOR_INTERVAL_S):
            self._tick(session, self._clock())

    def _tick(self, session: _Session, now: float) -> None:
        cfg = self._settings.get_recording()
        session.tracker.silence_s = cfg.silence_minutes * 60
        peaks = []
        for track in session.tracks.values():
            peaks.append(track.peak_db)
            track.peak_db = SILENCE_DB
        voice = max(peaks, default=SILENCE_DB) >= cfg.silence_threshold_db
        event = session.tracker.feed(now, voice)
        if event is not None:
            self._bus.publish(
                EventType.MEETING_SILENCE,
                {
                    "meeting_id": session.meeting.id,
                    "silent": event is SilenceEvent.SILENT,
                    "silence_seconds": round(session.tracker.silent_seconds(now), 1),
                },
            )
        if session.tracks and all(t.finished for t in session.tracks.values()):
            # every device died: finalize what we have (not from this thread: stop() joins it)
            threading.Thread(target=self.stop, daemon=True, name="rec-autostop").start()

    # ---- queries / settings ----------------------------------------------------------
    def status(self) -> RecordingStatus:
        with self._lock:
            session = self._session
        if session is None:
            return RecordingStatus(
                recording=False, meeting_id=None, title="", started_at=None, elapsed_s=0.0,
                tracks=[], system_level_db=None, mic_level_db=None, silent_seconds=0.0,
                silence_prompted=False, warnings=[],
            )  # fmt: skip
        now = self._clock()
        sysd = session.tracks.get(TrackKind.SYSTEM)
        mic = session.tracks.get(TrackKind.MIC)
        title = self._meetings.get(session.meeting.id).title
        return RecordingStatus(
            recording=True,
            meeting_id=session.meeting.id,
            title=title,
            started_at=session.meeting.started_at,
            elapsed_s=round(now - session.started, 1),
            tracks=list(session.tracks),
            system_level_db=sysd.level_db if sysd else None,
            mic_level_db=mic.level_db if mic else None,
            silent_seconds=round(session.tracker.silent_seconds(now), 1),
            silence_prompted=session.tracker.prompted,
            warnings=list(session.warnings),
        )

    @property
    def active(self) -> bool:
        return self._session is not None

    def recover_interrupted(self) -> int:
        """After a crash/kill: close meetings left in `recording` using what is on disk."""
        fixed = 0
        for meeting in self._meetings.interrupted():
            duration_ms = 0
            for path in self._meetings.track_paths(meeting.id).values():
                duration_ms = max(duration_ms, int(_count_frames(path) * 1000 / SAMPLE_RATE))
            status = MeetingStatus.RECORDED if duration_ms > 0 else MeetingStatus.FAILED
            self._meetings.finish(meeting.id, status, duration_ms)
            fixed += 1
        return fixed
