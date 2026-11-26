"""Local HTTP API (loopback only)."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .. import __version__
from ..analysis import AnalysisService
from ..analysis.mine import person_is_me
from ..audio.source import AudioUnavailableError
from ..detect import DetectorService
from ..events import EventBus
from ..export import export_markdown
from ..llm.factory import make_provider_factory
from ..models import (
    Column,
    DetectionSettings,
    DetectionSettingsPatch,
    DetectionStatus,
    EventType,
    Meeting,
    MeetingTitleUpdate,
    ModelDownloadRequest,
    ModelProfile,
    Person,
    PersonCreate,
    PersonUpdate,
    PromptResponse,
    PromptResult,
    RecordingSettings,
    RecordingSettingsPatch,
    RecordingStart,
    RecordingStatus,
    SearchHit,
    Task,
    TaskCreate,
    TaskMove,
    TaskProposal,
    TaskUpdate,
    TranscriptionSettings,
    TranscriptionSettingsPatch,
    TranscriptionStatusInfo,
    TranscriptSegment,
)
from ..profile import ProfileStore
from ..record import Recorder, RecorderBusy
from ..store import (
    AnalysisRepository,
    Database,
    DuplicateEmail,
    MeetingNotFound,
    MeetingRepository,
    PeopleRepository,
    PersonNotFound,
    SettingsRepository,
    TaskNotFound,
    TaskRepository,
    full_name,
)
from ..stt import PROFILES, ModelManager, TranscriptionService, has_cuda, recommend, total_ram_gb
from .analysis_routes import add_analysis_routes
from .deps import ProposeScope, ReadScope, UiScope
from .stream import EventBroker, format_sse

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


class LoopbackGuard(BaseHTTPMiddleware):
    """Reject non-loopback peers and foreign Host headers (DNS rebinding)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client = request.client.host if request.client else None
        if client not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail": "loopback only"}, status_code=403)
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ALLOWED_HOSTS | {"testserver"}:
            return JSONResponse({"detail": "invalid host header"}, status_code=403)
        if request.headers.get("origin"):
            # Browsers send Origin on cross-site requests. Hark has no web client.
            return JSONResponse({"detail": "browser origins are not allowed"}, status_code=403)
        return await call_next(request)


def create_app(
    db: Database,
    master_token: str,
    bus: EventBus | None = None,
    detector: DetectorService | None = None,
    recorder: Recorder | None = None,
    transcription: TranscriptionService | None = None,
    models: ModelManager | None = None,
    analysis: AnalysisService | None = None,
    profile_store: ProfileStore | None = None,
    data_dir: Path | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        # Graceful shutdown: finalize an in-progress recording (valid WAV files, meeting saved).
        # Must live here: uvicorn re-raises the termination signal right after this, so code
        # placed after server.run() would never execute.
        await run_in_threadpool(app.state.recorder.stop)
        await run_in_threadpool(app.state.detector.stop)
        await run_in_threadpool(app.state.transcription.stop)
        await run_in_threadpool(app.state.analysis.stop)

    app = FastAPI(
        lifespan=lifespan,
        title="Hark local API",
        version=__version__,
        description="Loopback-only API. Bearer token required. Integrations get read/propose.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(LoopbackGuard)
    app.state.master_token = master_token
    tasks = TaskRepository(db)
    people = PeopleRepository(db)
    events = bus or EventBus()
    app.state.bus = events
    detection = detector or DetectorService(SettingsRepository(db), events)
    app.state.detector = detection
    meetings = MeetingRepository(db)
    settings_repo = SettingsRepository(db)
    rec = recorder or Recorder(
        meetings, settings_repo, events, Path(tempfile.gettempdir()) / "hark-unused"
    )
    app.state.recorder = rec
    model_manager = models or ModelManager(Path(tempfile.gettempdir()) / "hark-unused-models")
    stt_service = transcription or TranscriptionService(
        meetings, settings_repo, events, model_manager, None
    )
    app.state.transcription = stt_service
    scratch = data_dir or Path(tempfile.gettempdir()) / "hark-unused"
    profiles = profile_store or ProfileStore(scratch / "profile.yaml")
    analyses = AnalysisRepository(db)
    analysis_service = analysis or AnalysisService(
        meetings, analyses, TaskRepository(db), settings_repo, events, profiles,
        make_provider_factory(settings_repo, scratch),
    )  # fmt: skip
    app.state.analysis = analysis_service
    add_analysis_routes(
        app, meetings=meetings, analyses=analyses, service=analysis_service,
        settings=settings_repo, profile=profiles, data_dir=scratch,
    )  # fmt: skip

    def _accept(prompt: object) -> bool:
        # Only the user's click on "Enregistrer" reaches this point.
        app_name = getattr(prompt, "app", "")
        rec.start(app="" if app_name == "test" else app_name)
        return True

    if detection.on_accept is None:
        detection.on_accept = _accept
    rec.on_state = detection.set_recording
    broker = EventBroker(events)

    @app.exception_handler(TaskNotFound)
    async def _not_found(_: Request, exc: TaskNotFound) -> JSONResponse:
        return JSONResponse({"detail": f"task {exc} not found"}, status_code=404)

    @app.exception_handler(MeetingNotFound)
    async def _meeting_not_found(_: Request, exc: MeetingNotFound) -> JSONResponse:
        return JSONResponse({"detail": f"meeting {exc} not found"}, status_code=404)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/v1/tasks", response_model=list[Task])
    def list_tasks(
        _: ReadScope,
        column: Column | None = None,
        source: str | None = None,
        assignee_id: str | None = None,
    ) -> list[Task]:
        return tasks.list(column=column, source=source, assignee_id=assignee_id)

    @app.get("/v1/tasks/{task_id}", response_model=Task)
    def get_task(task_id: str, _: ReadScope) -> Task:
        return tasks.get(task_id)

    @app.post("/v1/tasks/propose", response_model=Task, status_code=status.HTTP_201_CREATED)
    def propose_task(body: TaskProposal, who: ProposeScope) -> Task:
        person = people.find_by_email(body.assignee_email)  # links, never creates
        if person is not None and not body.assignee:
            body = body.model_copy(update={"assignee": full_name(person)})
        task = tasks.propose(
            body,
            source=who.source,
            assignee_id=person.id if person else None,
            is_mine=bool(person and person_is_me(person, profiles.load())),
        )
        events.publish(EventType.TASK_PROPOSED, {"task": task.model_dump(mode="json")})
        return task

    def _person_or_422(person_id: str) -> Person:
        try:
            return people.get(person_id)
        except PersonNotFound as exc:
            raise HTTPException(422, "unknown person") from exc

    # ---- team directory ----------------------------------------------------------
    @app.get("/v1/people", response_model=list[Person])
    def list_people(_: ReadScope) -> list[Person]:
        return people.list()

    @app.post("/v1/people", response_model=Person, status_code=status.HTTP_201_CREATED)
    def create_person(body: PersonCreate, _: UiScope) -> Person:
        try:
            person = people.create(body)
        except DuplicateEmail as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "cette adresse e-mail existe déjà"
            ) from exc
        # the kanban refreshes on task.* events: a new team member must show up there too
        events.publish(EventType.TASK_UPDATED, {"person_id": person.id})
        return person

    @app.patch("/v1/people/{person_id}", response_model=Person)
    def update_person(person_id: str, body: PersonUpdate, _: UiScope) -> Person:
        try:
            person = people.update(person_id, body)
        except PersonNotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "person not found") from exc
        except DuplicateEmail as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "cette adresse e-mail existe déjà"
            ) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        events.publish(EventType.TASK_UPDATED, {"person_id": person_id})
        return person

    @app.delete("/v1/people/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_person(person_id: str, _: UiScope) -> Response:
        try:
            people.delete(person_id)
        except PersonNotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "person not found") from exc
        events.publish(EventType.TASK_UPDATED, {"person_id": person_id, "deleted": True})
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ---- desktop app only (ui scope) -------------------------------------------
    @app.post("/v1/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
    def create_task(body: TaskCreate, _: UiScope) -> Task:
        mine = False
        if body.assignee_id is not None:
            person = _person_or_422(body.assignee_id)
            body = body.model_copy(update={"assignee": full_name(person)})
            mine = person_is_me(person, profiles.load())
        task = tasks.create(body, is_mine=mine)
        events.publish(EventType.TASK_UPDATED, {"task": task.model_dump(mode="json")})
        return task

    @app.patch("/v1/tasks/{task_id}", response_model=Task)
    def update_task(task_id: str, body: TaskUpdate, _: UiScope) -> Task:
        tasks.get(task_id)  # 404 first
        if "assignee_id" in body.model_fields_set:
            extra: dict[str, object] = {}
            if body.assignee_id is None:  # unassign
                if "assignee" not in body.model_fields_set:
                    extra["assignee"] = ""
            else:
                person = _person_or_422(body.assignee_id)
                extra["assignee"] = full_name(person)
                if "is_mine" not in body.model_fields_set:
                    extra["is_mine"] = person_is_me(person, profiles.load())
            body = TaskUpdate.model_validate(
                {**body.model_dump(exclude_unset=True, mode="json"), **extra}
            )
        task = tasks.update(task_id, body)
        events.publish(EventType.TASK_UPDATED, {"task": task.model_dump(mode="json")})
        return task

    @app.post("/v1/tasks/{task_id}/move", response_model=Task)
    def move_task(task_id: str, body: TaskMove, _: UiScope) -> Task:
        task = tasks.move(task_id, body)
        events.publish(EventType.TASK_UPDATED, {"task": task.model_dump(mode="json")})
        return task

    @app.delete("/v1/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_task(task_id: str, _: UiScope) -> Response:
        tasks.delete(task_id)
        events.publish(EventType.TASK_UPDATED, {"task_id": task_id, "deleted": True})
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ---- events stream (SSE) ---------------------------------------------------
    @app.get("/v1/events/stream")
    async def events_stream(request: Request, _: ReadScope) -> StreamingResponse:
        queue = broker.subscribe()

        async def gen() -> AsyncIterator[str]:
            try:
                yield ": connected\n\n"
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield format_sse(event)
            finally:
                broker.unsubscribe(queue)

        return StreamingResponse(
            gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    # ---- meeting detection -----------------------------------------------------
    @app.get("/v1/detection/status", response_model=DetectionStatus)
    def detection_status(_: ReadScope) -> DetectionStatus:
        return detection.status()

    @app.get("/v1/settings/detection", response_model=DetectionSettings)
    def get_detection_settings(_: ReadScope) -> DetectionSettings:
        return detection.get_settings()

    @app.patch("/v1/settings/detection", response_model=DetectionSettings)
    def patch_detection_settings(body: DetectionSettingsPatch, _: UiScope) -> DetectionSettings:
        return detection.patch_settings(body)

    @app.post("/v1/detection/respond", response_model=PromptResult)
    def detection_respond(body: PromptResponse, _: UiScope) -> PromptResult:
        return detection.respond(body.prompt_id, body.action)

    @app.post("/v1/detection/test", status_code=status.HTTP_202_ACCEPTED)
    def detection_test(_: UiScope) -> dict[str, bool]:
        """Show the consent notification once, to check it works. Records nothing."""
        return {"prompted": detection.test_prompt()}

    # ---- meetings & recording ----------------------------------------------------
    @app.get("/v1/meetings", response_model=list[Meeting])
    def list_meetings(_: ReadScope, limit: int = 50, offset: int = 0) -> list[Meeting]:
        return meetings.list_recent(limit=max(1, min(limit, 200)), offset=max(0, offset))

    @app.get("/v1/meetings/{meeting_id}", response_model=Meeting)
    def get_meeting(meeting_id: str, _: ReadScope) -> Meeting:
        return meetings.get(meeting_id)

    @app.patch("/v1/meetings/{meeting_id}", response_model=Meeting)
    def rename_meeting(meeting_id: str, body: MeetingTitleUpdate, _: UiScope) -> Meeting:
        return meetings.set_title(meeting_id, body.title)

    @app.get("/v1/meetings/{meeting_id}/transcript", response_model=list[TranscriptSegment])
    def meeting_transcript(meeting_id: str, _: ReadScope) -> list[TranscriptSegment]:
        meetings.get(meeting_id)  # 404 if unknown
        return meetings.segments(meeting_id)

    @app.get("/v1/meetings/{meeting_id}/export.md")
    def meeting_export(meeting_id: str, _: ReadScope) -> Response:
        meeting = meetings.get(meeting_id)
        md = export_markdown(
            meeting,
            meetings.segments(meeting_id),
            TaskRepository(db).list(source=f"meeting:{meeting_id}"),
        )
        return Response(md, media_type="text/markdown; charset=utf-8")

    @app.delete("/v1/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_meeting(meeting_id: str, _: UiScope) -> Response:
        meetings.get(meeting_id)
        if rec.status().meeting_id == meeting_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "stop the recording first")
        meetings.delete(meeting_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/v1/meetings/{meeting_id}/transcribe", status_code=status.HTTP_202_ACCEPTED)
    def transcribe_meeting(meeting_id: str, _: UiScope) -> dict[str, str]:
        meeting = meetings.get(meeting_id)
        if meeting.status.value != "recorded" or not meeting.audio_available:
            raise HTTPException(status.HTTP_409_CONFLICT, "no audio available for this meeting")
        stt_service.submit(meeting_id)
        return {"status": "queued"}

    @app.get("/v1/search", response_model=list[SearchHit])
    def search_meetings(_: ReadScope, q: str = "", limit: int = 30) -> list[SearchHit]:
        rows = meetings.search(q[:200], max(1, min(limit, 100)))
        return [
            SearchHit(
                meeting_id=r["meeting_id"],
                meeting_title=r["meeting_title"],
                kind=r["kind"],
                snippet=r["snippet"],
                start_ms=r["start_ms"],
                speaker=r["speaker"],
            )
            for r in rows
        ]

    # ---- transcription: settings, models, status -------------------------------------
    @app.get("/v1/settings/transcription", response_model=TranscriptionSettings)
    def get_transcription_settings(_: ReadScope) -> TranscriptionSettings:
        return settings_repo.get_transcription()

    @app.patch("/v1/settings/transcription", response_model=TranscriptionSettings)
    def patch_transcription_settings(
        body: TranscriptionSettingsPatch, _: UiScope
    ) -> TranscriptionSettings:
        new = settings_repo.patch_transcription(body)
        stt_service.on_model_installed(new.profile)  # meetings waiting for a model retry now
        return new

    @app.get("/v1/models", response_model=list[ModelProfile])
    def list_models(_: ReadScope) -> list[ModelProfile]:
        best = recommend(total_ram_gb(), has_cuda())
        return [
            ModelProfile(
                id=p.id,
                label=p.label,
                description=p.description,
                whisper_model=p.whisper_model,
                download_mb=p.download_mb,
                min_ram_gb=p.min_ram_gb,
                gpu_recommended=p.gpu_recommended,
                installed=model_manager.installed(p.id),
                recommended=p.id == best,
            )
            for p in PROFILES.values()
        ]

    @app.post("/v1/models/download", status_code=status.HTTP_202_ACCEPTED)
    def download_model(body: ModelDownloadRequest, _: UiScope) -> dict[str, str]:
        """The only place the engine uses the network: an explicit user action."""
        model_manager.start_download(body.profile)
        return {"status": "downloading"}

    @app.get("/v1/transcription/status", response_model=TranscriptionStatusInfo)
    def transcription_status(_: ReadScope) -> TranscriptionStatusInfo:
        return stt_service.status()

    @app.get("/v1/recording/status", response_model=RecordingStatus)
    def recording_status(_: ReadScope) -> RecordingStatus:
        return rec.status()

    @app.post("/v1/recording/start", response_model=Meeting, status_code=status.HTTP_201_CREATED)
    def recording_start(body: RecordingStart, _: UiScope) -> Meeting:
        """Explicit user action only (ui scope): integrations can never start a recording."""
        try:
            return rec.start(title=body.title)
        except RecorderBusy as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except AudioUnavailableError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    @app.post("/v1/recording/stop", response_model=Meeting)
    def recording_stop(_: UiScope) -> Meeting:
        meeting = rec.stop()
        if meeting is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "no recording in progress")
        return meeting

    @app.get("/v1/settings/recording", response_model=RecordingSettings)
    def get_recording_settings(_: ReadScope) -> RecordingSettings:
        return settings_repo.get_recording()

    @app.patch("/v1/settings/recording", response_model=RecordingSettings)
    def patch_recording_settings(body: RecordingSettingsPatch, _: UiScope) -> RecordingSettings:
        return settings_repo.patch_recording(body)

    @app.get("/v1/openapi.json", include_in_schema=False)
    def openapi_doc(_: ReadScope) -> JSONResponse:
        return JSONResponse(app.openapi())

    return app
