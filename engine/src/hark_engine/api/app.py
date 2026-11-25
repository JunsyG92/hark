"""Local HTTP API (loopback only)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .. import __version__
from ..detect import DetectorService
from ..events import EventBus
from ..models import (
    Column,
    DetectionSettings,
    DetectionSettingsPatch,
    DetectionStatus,
    EventType,
    PromptResponse,
    PromptResult,
    Task,
    TaskCreate,
    TaskMove,
    TaskProposal,
    TaskUpdate,
)
from ..store import Database, SettingsRepository, TaskNotFound, TaskRepository
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
) -> FastAPI:
    app = FastAPI(
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
    events = bus or EventBus()
    app.state.bus = events
    detection = detector or DetectorService(SettingsRepository(db), events)
    app.state.detector = detection
    broker = EventBroker(events)

    @app.exception_handler(TaskNotFound)
    async def _not_found(_: Request, exc: TaskNotFound) -> JSONResponse:
        return JSONResponse({"detail": f"task {exc} not found"}, status_code=404)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/v1/tasks", response_model=list[Task])
    def list_tasks(
        _: ReadScope, column: Column | None = None, source: str | None = None
    ) -> list[Task]:
        return tasks.list(column=column, source=source)

    @app.get("/v1/tasks/{task_id}", response_model=Task)
    def get_task(task_id: str, _: ReadScope) -> Task:
        return tasks.get(task_id)

    @app.post("/v1/tasks/propose", response_model=Task, status_code=status.HTTP_201_CREATED)
    def propose_task(body: TaskProposal, who: ProposeScope) -> Task:
        task = tasks.propose(body, source=who.source)
        events.publish(EventType.TASK_PROPOSED, {"task": task.model_dump(mode="json")})
        return task

    # ---- desktop app only (ui scope) -------------------------------------------
    @app.post("/v1/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
    def create_task(body: TaskCreate, _: UiScope) -> Task:
        task = tasks.create(body)
        events.publish(EventType.TASK_UPDATED, {"task": task.model_dump(mode="json")})
        return task

    @app.patch("/v1/tasks/{task_id}", response_model=Task)
    def update_task(task_id: str, body: TaskUpdate, _: UiScope) -> Task:
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

    @app.get("/v1/openapi.json", include_in_schema=False)
    def openapi_doc(_: ReadScope) -> JSONResponse:
        return JSONResponse(app.openapi())

    return app
