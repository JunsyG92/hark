"""Background transcription queue + audio retention.

meeting.recorded → (auto_transcribe) queue → one meeting at a time → segments in SQLite + FTS index
→ transcript.ready → audio deleted according to the retention setting (default: right away).
A failed transcription keeps the audio so it can be retried.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections import deque

from ..events import EventBus
from ..models import (
    Event,
    EventType,
    MeetingStatus,
    ModelProfileId,
    Speaker,
    TrackKind,
    TranscriptionStatus,
    TranscriptionStatusInfo,
)
from ..store import MeetingRepository, NewSegment, SettingsRepository
from .models import ModelManager
from .transcriber import ModelNotInstalledError, Transcriber

log = logging.getLogger(__name__)

PURGE_INTERVAL_S = 3600.0
SPEAKER_BY_TRACK = {TrackKind.MIC: Speaker.ME, TrackKind.SYSTEM: Speaker.OTHERS}


class TranscriptionService:
    def __init__(
        self,
        meetings: MeetingRepository,
        settings: SettingsRepository,
        bus: EventBus,
        models: ModelManager,
        transcriber: Transcriber | None,
    ) -> None:
        self._meetings = meetings
        self._settings = settings
        self._bus = bus
        self._models = models
        self._transcriber = transcriber
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        self._waiting: deque[str] = deque()
        self._current: str | None = None
        self._progress = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        bus.subscribe(self._on_event, {EventType.MEETING_RECORDED})

    # ---- lifecycle -----------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="transcriber")
        self._thread.start()
        self._meetings.requeue_interrupted()  # a transcription cut by a quit/crash restarts
        for meeting_id in self._meetings.pending_transcription():
            self._enqueue(meeting_id)  # e.g. waiting for a model, or interrupted by a restart

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    # ---- inputs --------------------------------------------------------------------
    def _on_event(self, event: Event) -> None:
        meeting = event.data.get("meeting")
        if not isinstance(meeting, dict) or meeting.get("status") != MeetingStatus.RECORDED.value:
            return
        if self._settings.get_transcription().auto_transcribe:
            self.submit(str(meeting["id"]))

    def submit(self, meeting_id: str) -> None:
        """Queue a meeting (idempotent while it is already queued/running)."""
        self._meetings.set_transcription(meeting_id, TranscriptionStatus.PENDING)
        self._enqueue(meeting_id)

    def on_model_installed(self, _profile: ModelProfileId) -> None:
        for meeting_id in self._meetings.pending_transcription():
            self._enqueue(meeting_id)

    def _enqueue(self, meeting_id: str) -> None:
        with self._lock:
            if meeting_id == self._current or meeting_id in self._waiting:
                return
            self._waiting.append(meeting_id)
        self._queue.put(meeting_id)

    # ---- status ----------------------------------------------------------------------
    def status(self) -> TranscriptionStatusInfo:
        profile = self._settings.get_transcription().profile
        with self._lock:
            return TranscriptionStatusInfo(
                queue=list(self._waiting),
                current_meeting_id=self._current,
                progress=round(self._progress, 3),
                model_installed=bool(self._transcriber and self._transcriber.ready(profile)),
                download=self._models.status(),
            )

    # ---- worker ----------------------------------------------------------------------
    def _worker(self) -> None:
        self.purge_expired_audio()
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=PURGE_INTERVAL_S)
            except queue.Empty:
                self.purge_expired_audio()
                continue
            if item is None:
                break
            with self._lock:
                if item in self._waiting:
                    self._waiting.remove(item)
                self._current, self._progress = item, 0.0
            try:
                self.process(item)
            except Exception:
                log.exception("transcription crashed for %s", item)
            finally:
                with self._lock:
                    self._current = None
                if self._transcriber and self._queue.empty():
                    self._transcriber.unload()

    def process(self, meeting_id: str) -> None:
        """Transcribe one meeting synchronously (the worker calls this; tests may too)."""
        cfg = self._settings.get_transcription()
        if self._transcriber is None or not self._transcriber.ready(cfg.profile):
            self._meetings.set_transcription(
                meeting_id, TranscriptionStatus.PENDING, "model_not_installed"
            )
            return
        paths = {k: p for k, p in self._meetings.track_paths(meeting_id).items() if p.exists()}
        if not paths:
            self._meetings.set_transcription(
                meeting_id, TranscriptionStatus.FAILED, "audio_missing"
            )
            return
        self._meetings.set_transcription(meeting_id, TranscriptionStatus.RUNNING)
        try:
            segments: list[NewSegment] = []
            languages: dict[str, int] = {}
            for index, (kind, path) in enumerate(paths.items()):

                def progress(p: float, i: int = index) -> None:
                    self._progress = (i + p) / len(paths)

                raw, language = self._transcriber.transcribe(
                    path, cfg.profile, cfg.language, progress
                )
                languages[language] = languages.get(language, 0) + sum(len(s.text) for s in raw)
                segments += [
                    NewSegment(
                        kind, SPEAKER_BY_TRACK[kind], int(s.start * 1000), int(s.end * 1000), s.text
                    )
                    for s in raw
                ]
            segments.sort(key=lambda s: (s.start_ms, s.track.value))
            count = self._meetings.replace_segments(meeting_id, segments)
            dominant = max(languages, key=lambda k: languages[k]) if languages else None
            self._meetings.set_transcription(meeting_id, TranscriptionStatus.DONE, None, dominant)
        except ModelNotInstalledError:
            self._meetings.set_transcription(
                meeting_id, TranscriptionStatus.PENDING, "model_not_installed"
            )
            return
        except Exception as exc:
            log.exception("transcription failed for %s", meeting_id)
            self._meetings.set_transcription(
                meeting_id, TranscriptionStatus.FAILED, f"{type(exc).__name__}: {exc}"[:300]
            )
            return
        self._apply_retention(meeting_id, cfg.retention_days)
        self._bus.publish(EventType.TRANSCRIPT_READY, {"meeting_id": meeting_id, "segments": count})

    # ---- retention ---------------------------------------------------------------------
    def _apply_retention(self, meeting_id: str, days: int) -> None:
        if days == 0:
            self._meetings.delete_audio(meeting_id)  # default: audio deleted after success
        else:
            self._meetings.set_audio_expiry(meeting_id, days)

    def purge_expired_audio(self) -> int:
        expired = self._meetings.expired_audio()
        for meeting_id in expired:
            self._meetings.delete_audio(meeting_id)
        return len(expired)
