"""Shared data model. Source of truth for the JSON Schemas in /contracts.

Changing a model here requires re-running ``uv run hark-contracts`` (a test
fails if /contracts is out of sync).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SOURCE_PATTERN = r"^(manual|meeting:[A-Za-z0-9_-]{1,64}|plugin:[a-z0-9][a-z0-9-]{0,63})$"

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(max_length=10_000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Source = Annotated[str, StringConstraints(pattern=SOURCE_PATTERN)]


class Strict(BaseModel):
    # Fields with defaults are always present in responses: mark them required
    # in serialization schemas so generated client types are precise.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class Column(StrEnum):
    TO_VALIDATE = "to_validate"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class EvidenceRef(Strict):
    """Pointer to the timestamped transcript excerpt a task comes from."""

    meeting_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    start_ms: int = Field(ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class Task(Strict):
    id: str
    title: Title
    description: LongText = ""
    assignee: ShortText = ""
    due: date | None = None
    priority: Priority = Priority.NORMAL
    column: Column
    position: float = Field(description="Sort key inside the column (ascending).")
    source: Source = Field(description="manual | meeting:<id> | plugin:<name>")
    evidence: EvidenceRef | None = None
    is_mine: bool = Field(default=False, description="Task concerns the user (profile match).")
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime
    updated_at: datetime


class TaskCreate(Strict):
    """Manual creation from the desktop app (ui scope)."""

    title: Title
    description: LongText = ""
    assignee: ShortText = ""
    due: date | None = None
    priority: Priority = Priority.NORMAL
    column: Column = Column.TODO


class TaskUpdate(Strict):
    title: Title | None = None
    description: LongText | None = None
    assignee: ShortText | None = None
    due: date | None = None
    priority: Priority | None = None
    is_mine: bool | None = None


class TaskMove(Strict):
    column: Column
    index: int = Field(ge=0, description="Target index inside the destination column.")


class TaskProposal(Strict):
    """What integrations may send. Always lands in the `to_validate` column."""

    title: Title
    description: LongText = ""
    assignee: ShortText = ""
    due: date | None = None
    priority: Priority = Priority.NORMAL
    evidence: EvidenceRef | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class EventType(StrEnum):
    MEETING_DETECTED = "meeting.detected"
    MEETING_RECORDING_STARTED = "meeting.recording_started"
    MEETING_RECORDED = "meeting.recorded"
    TRANSCRIPT_READY = "transcript.ready"
    ANALYSIS_READY = "analysis.ready"
    TASK_PROPOSED = "task.proposed"
    TASK_UPDATED = "task.updated"


class Event(Strict):
    id: str
    type: EventType
    occurred_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)


# name -> (model, schema mode). Inputs use "validation", outputs "serialization".
CONTRACT_MODELS: dict[str, tuple[type[BaseModel], Literal["validation", "serialization"]]] = {
    "Task": (Task, "serialization"),
    "TaskProposal": (TaskProposal, "validation"),
    "EvidenceRef": (EvidenceRef, "serialization"),
    "Event": (Event, "serialization"),
}
