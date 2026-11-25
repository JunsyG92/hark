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
    # Extra (not in the original list): recording went silent / a voice came back.
    MEETING_SILENCE = "meeting.silence"


class Event(Strict):
    id: str
    type: EventType
    occurred_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)


class PromptAction(StrEnum):
    RECORD = "record"
    DECLINE = "decline"
    IGNORE = "ignore"


class DetectionPhase(StrEnum):
    DISABLED = "disabled"
    IDLE = "idle"
    PROMPTED = "prompted"
    COOLDOWN = "cooldown"
    RECORDING = "recording"


class DetectionSettings(Strict):
    """Meeting detection tuning. Detection only observes audio levels; nothing is recorded."""

    enabled: bool = True
    threshold_db: float = Field(default=-45.0, ge=-80.0, le=-10.0, description="RMS dBFS.")
    min_seconds: float = Field(default=8.0, ge=1.0, le=120.0)
    require_mic_in_use: bool = Field(
        default=True, description="Another app must be using the microphone (call signal)."
    )
    prompt_seconds: float = Field(default=20.0, ge=5.0, le=120.0)
    cooldown_ignore_minutes: float = Field(default=10.0, ge=0.0, le=240.0)
    cooldown_decline_minutes: float = Field(default=30.0, ge=0.0, le=240.0)


class DetectionSettingsPatch(Strict):
    enabled: bool | None = None
    threshold_db: float | None = Field(default=None, ge=-80.0, le=-10.0)
    min_seconds: float | None = Field(default=None, ge=1.0, le=120.0)
    require_mic_in_use: bool | None = None
    prompt_seconds: float | None = Field(default=None, ge=5.0, le=120.0)
    cooldown_ignore_minutes: float | None = Field(default=None, ge=0.0, le=240.0)
    cooldown_decline_minutes: float | None = Field(default=None, ge=0.0, le=240.0)


class DetectionStatus(Strict):
    phase: DetectionPhase
    level_db: float | None = Field(description="Current output level, null if no audio source.")
    above_threshold_seconds: float
    mic_in_use: bool | None = Field(description="null when the OS does not expose it.")
    mic_apps: list[str]
    audio_source: str | None
    error: str | None


class PromptResponse(Strict):
    prompt_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    action: PromptAction


class PromptResult(Strict):
    ok: bool
    recording_started: bool
    error: str | None = None


class MeetingDetectedData(Strict):
    """`data` of the `meeting.detected` event."""

    prompt_id: str
    app: str
    level_db: float
    prompt_seconds: float
    reminder: str = "Pense à informer les participants."


class MeetingStatus(StrEnum):
    RECORDING = "recording"
    RECORDED = "recorded"
    FAILED = "failed"


class TrackKind(StrEnum):
    SYSTEM = "system"  # what the other participants say (system output loopback)
    MIC = "mic"  # me


class Meeting(Strict):
    id: str
    title: ShortText = ""
    status: MeetingStatus
    app: ShortText = ""
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    tracks: list[TrackKind]
    audio_available: bool = Field(description="Audio files still on disk (see retention).")


class RecordingStart(Strict):
    title: ShortText = ""


class MeetingTitleUpdate(Strict):
    title: ShortText


class RecordingSettings(Strict):
    silence_minutes: float = Field(default=3.0, ge=1.0, le=30.0)
    silence_threshold_db: float = Field(default=-45.0, ge=-80.0, le=-10.0)


class RecordingSettingsPatch(Strict):
    silence_minutes: float | None = Field(default=None, ge=1.0, le=30.0)
    silence_threshold_db: float | None = Field(default=None, ge=-80.0, le=-10.0)


class RecordingStatus(Strict):
    recording: bool
    meeting_id: str | None
    title: str
    started_at: datetime | None
    elapsed_s: float
    tracks: list[TrackKind]
    system_level_db: float | None
    mic_level_db: float | None
    silent_seconds: float
    silence_prompted: bool
    warnings: list[str]


# name -> (model, schema mode). Inputs use "validation", outputs "serialization".
CONTRACT_MODELS: dict[str, tuple[type[BaseModel], Literal["validation", "serialization"]]] = {
    "Task": (Task, "serialization"),
    "TaskProposal": (TaskProposal, "validation"),
    "EvidenceRef": (EvidenceRef, "serialization"),
    "Event": (Event, "serialization"),
    "DetectionSettings": (DetectionSettings, "serialization"),
    "DetectionStatus": (DetectionStatus, "serialization"),
    "MeetingDetectedData": (MeetingDetectedData, "serialization"),
    "Meeting": (Meeting, "serialization"),
    "RecordingSettings": (RecordingSettings, "serialization"),
    "RecordingStatus": (RecordingStatus, "serialization"),
}
