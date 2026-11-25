"""Analysis queue: transcript.ready → LLM pipeline → summary, decisions, tasks in « À valider ».

Token control: one pipeline run per distinct input (cache by hash), a hard budget per meeting, and
no automatic re-processing of a meeting that was already analyzed.
"""

from __future__ import annotations

import hashlib
import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime

from ..events import EventBus
from ..llm import (
    LLMModelMissingError,
    LLMProvider,
    LLMUnavailableError,
    OllamaProvider,
)
from ..models import (
    Analysis,
    AnalysisStatus,
    AnalysisStatusInfo,
    DownloadStatus,
    Event,
    EventType,
    EvidenceRef,
    TaskProposal,
    TranscriptSegment,
)
from ..profile import ProfileStore, profile_hash
from ..store import AnalysisRepository, MeetingRepository, SettingsRepository, TaskRepository
from .chunking import transcript_text
from .mine import is_mine, normalize
from .pipeline import BudgetExceeded, InvalidOutput, parse_due, parse_timestamp, run_pipeline
from .prompts import PROMPT_VERSION

log = logging.getLogger(__name__)

AVAILABILITY_TTL_S = 5.0


def input_hash(
    provider: LLMProvider, chunk_tokens: int, profile_h: str, segments: list[TranscriptSegment]
) -> str:
    raw = "|".join(
        [
            PROMPT_VERSION,
            provider.name,
            provider.model,
            str(chunk_tokens),
            profile_h,
            transcript_text(segments),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def locate(segments: list[TranscriptSegment], ms: int | None) -> TranscriptSegment | None:
    """The segment a timestamp points to (the last one starting at or before it)."""
    if ms is None or not segments:
        return None
    best = segments[0]
    for s in segments:
        if s.start_ms <= ms:
            best = s
        else:
            break
    return best


class AnalysisService:
    def __init__(
        self,
        meetings: MeetingRepository,
        analyses: AnalysisRepository,
        tasks: TaskRepository,
        settings: SettingsRepository,
        bus: EventBus,
        profile: ProfileStore,
        provider_factory: Callable[[], LLMProvider],
    ) -> None:
        self._meetings, self._analyses, self._tasks = meetings, analyses, tasks
        self._settings, self._bus, self._profile = settings, bus, profile
        self._factory = provider_factory
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        self._waiting: deque[str] = deque()
        self._current: str | None = None
        self._force: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._avail: tuple[float, bool, str | None] = (0.0, False, None)
        self._pull = DownloadStatus(state="idle")
        bus.subscribe(self._on_event, {EventType.TRANSCRIPT_READY})

    # ---- lifecycle -------------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="analyzer")
        self._thread.start()
        for meeting_id in self._meetings.pending_analysis():
            self._enqueue(meeting_id)

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    # ---- inputs ------------------------------------------------------------------------
    def _on_event(self, event: Event) -> None:
        meeting_id = str(event.data.get("meeting_id", ""))
        if not meeting_id or not self._settings.get_llm().auto_analyze:
            return
        if self._analyses.get(meeting_id) is None:  # never re-process an analyzed meeting
            self.submit(meeting_id)

    def submit(self, meeting_id: str, force: bool = False) -> None:
        self._meetings.set_analysis(meeting_id, AnalysisStatus.PENDING)
        if force:
            self._force.add(meeting_id)
        self._enqueue(meeting_id)

    def retry_pending(self) -> None:
        """e.g. after Ollama was started or the model changed."""
        for meeting_id in self._meetings.pending_analysis():
            self._enqueue(meeting_id)

    def _enqueue(self, meeting_id: str) -> None:
        with self._lock:
            if meeting_id == self._current or meeting_id in self._waiting:
                return
            self._waiting.append(meeting_id)
        self._queue.put(meeting_id)

    # ---- status ------------------------------------------------------------------------
    def availability(self) -> tuple[bool, str | None]:
        now = time.monotonic()
        stamp, ok, why = self._avail
        if now - stamp < AVAILABILITY_TTL_S:
            return ok, why
        ok, why = self._factory().available()
        self._avail = (now, ok, why)
        return ok, why

    def status(self) -> AnalysisStatusInfo:
        provider = self._factory()
        ok, why = self.availability()
        with self._lock:
            return AnalysisStatusInfo(
                queue=list(self._waiting),
                current_meeting_id=self._current,
                provider=provider.name,
                model=provider.model,
                available=ok,
                availability_error=why,
                pull=self._pull,
            )

    def start_pull(self, model: str) -> DownloadStatus:
        """Ask the *local* Ollama server to download a model (Ollama does the network part)."""
        with self._lock:
            if self._pull.state == "downloading":
                return self._pull
            self._pull = DownloadStatus(state="downloading", model=model)
        threading.Thread(target=self._do_pull, args=(model,), daemon=True, name="llm-pull").start()
        return self._pull

    def _do_pull(self, model: str) -> None:
        try:
            OllamaProvider(self._settings.get_llm().ollama_url, model).pull(model)
            self._pull = DownloadStatus(state="done", model=model)
            self._avail = (0.0, False, None)
            self.retry_pending()
        except Exception as exc:
            self._pull = DownloadStatus(state="error", model=model, error=str(exc)[:300])

    # ---- worker ------------------------------------------------------------------------
    def _worker(self) -> None:
        while not self._stop.is_set():
            item = self._queue.get()
            if item is None:
                break
            with self._lock:
                if item in self._waiting:
                    self._waiting.remove(item)
                self._current = item
            try:
                self.process(item, force=item in self._force)
            except Exception:
                log.exception("analysis crashed for %s", item)
                self._meetings.set_analysis(item, AnalysisStatus.FAILED, "internal_error")
            finally:
                self._force.discard(item)
                with self._lock:
                    self._current = None

    def process(self, meeting_id: str, force: bool = False) -> None:
        segments = self._meetings.segments(meeting_id)
        if not segments:
            self._meetings.set_analysis(meeting_id, AnalysisStatus.FAILED, "no_transcript")
            return
        cfg = self._settings.get_llm()
        profile = self._profile.load()
        provider = self._factory()
        ok, why = provider.available()
        if not ok:
            self._meetings.set_analysis(
                meeting_id, AnalysisStatus.PENDING, f"llm_unavailable: {why}"
            )
            return
        digest = input_hash(provider, cfg.chunk_tokens, profile_hash(profile), segments)
        stored = self._analyses.get(meeting_id)
        if stored is not None and stored.input_hash == digest and not force:
            self._meetings.set_analysis(meeting_id, AnalysisStatus.DONE)  # cache hit: zero LLM call
            return
        meeting = self._meetings.get(meeting_id)
        self._meetings.set_analysis(meeting_id, AnalysisStatus.RUNNING)
        try:
            result = run_pipeline(
                provider, segments, f"{meeting.started_at.astimezone():%Y-%m-%d}", profile, cfg
            )
        except BudgetExceeded as exc:
            self._meetings.set_analysis(
                meeting_id, AnalysisStatus.FAILED, f"budget_exceeded: {exc}"
            )
            return
        except (LLMUnavailableError, LLMModelMissingError) as exc:
            self._meetings.set_analysis(
                meeting_id, AnalysisStatus.PENDING, f"llm_unavailable: {exc}"
            )
            return
        except InvalidOutput as exc:
            self._meetings.set_analysis(meeting_id, AnalysisStatus.FAILED, f"invalid_output: {exc}")
            return

        out = result.output
        created = self._create_tasks(meeting_id, out, segments, profile)
        self._analyses.save(
            Analysis(
                meeting_id=meeting_id,
                title=out.title,
                summary=out.summary,
                decisions=out.decisions,
                open_questions=out.open_questions,
                tasks_proposed=created,
                provider=provider.name,
                model=provider.model,
                chunks=result.chunks,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                created_at=datetime.now().astimezone(),
            ),
            digest,
            PROMPT_VERSION,
        )
        if out.title and not meeting.title.strip():
            self._meetings.set_title(meeting_id, out.title)  # automatic title
        self._meetings.set_analysis(meeting_id, AnalysisStatus.DONE)
        self._bus.publish(
            EventType.ANALYSIS_READY,
            {
                "meeting_id": meeting_id,
                "tasks": created,
                "tokens": result.tokens_in + result.tokens_out,
            },
        )

    def _create_tasks(self, meeting_id, out, segments, profile) -> int:  # type: ignore[no-untyped-def]
        source = f"meeting:{meeting_id}"
        existing = {normalize(t.title) for t in self._tasks.list(source=source)}
        created = 0
        for item in out.tasks:
            key = normalize(item.title)
            if key in existing:
                continue  # a re-analysis must not duplicate what is already on the board
            ms = parse_timestamp(item.evidence_timestamp)
            seg = locate(segments, ms)
            mine = is_mine(item.assignee, seg.start_ms if seg else ms, segments, profile)
            evidence = (
                EvidenceRef(meeting_id=meeting_id, start_ms=seg.start_ms, end_ms=seg.end_ms)
                if seg
                else None
            )
            description = ""
            if seg:
                who = "Moi" if seg.speaker.value == "me" else "Autres"
                description = f"« {seg.text} » ({who})"
            task = self._tasks.propose(
                TaskProposal(
                    title=item.title,
                    description=description[:2000],
                    assignee=item.assignee,
                    due=parse_due(item.due),
                    evidence=evidence,
                    confidence=item.confidence,
                ),
                source=source,
                is_mine=mine,
            )
            existing.add(key)
            created += 1
            self._bus.publish(EventType.TASK_PROPOSED, {"task": task.model_dump(mode="json")})
        return created
