"""Shared data model. Source of truth for the JSON Schemas in /contracts.

Changing a model here requires re-running ``uv run hark-contracts`` (a test
fails if /contracts is out of sync).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

SOURCE_PATTERN = r"^(manual|meeting:[A-Za-z0-9_-]{1,64}|plugin:[a-z0-9][a-z0-9-]{0,63})$"

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(max_length=10_000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Source = Annotated[str, StringConstraints(pattern=SOURCE_PATTERN)]


class Strict(BaseModel):
    # Fields with defaults are always present in responses: mark them required
    # in serialization schemas so generated client types are precise.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{1,63}$"
PersonId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=320)]


def _check_email(value: str) -> str:
    import re

    if value and not re.match(EMAIL_PATTERN, value):
        raise ValueError("adresse e-mail invalide")
    return value


class Person(Strict):
    """A team member tasks can be assigned to (the lead's team directory)."""

    id: str
    first_name: str
    last_name: str
    email: str
    created_at: datetime


class PersonCreate(Strict):
    first_name: Name = ""
    last_name: Name = ""
    email: Email = ""

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _check_email(v)

    @model_validator(mode="after")
    def _named(self) -> PersonCreate:
        if not (self.first_name or self.last_name):
            raise ValueError("prénom ou nom obligatoire")
        return self


class PersonUpdate(Strict):
    first_name: Name | None = None
    last_name: Name | None = None
    email: Email | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return _check_email(v) if v is not None else v


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
    assignee_id: str | None = Field(default=None, description="Person from the team directory.")
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime
    updated_at: datetime


class TaskCreate(Strict):
    """Manual creation from the desktop app (ui scope)."""

    title: Title
    description: LongText = ""
    assignee: ShortText = ""
    assignee_id: PersonId | None = None
    due: date | None = None
    priority: Priority = Priority.NORMAL
    column: Column = Column.TODO


class TaskUpdate(Strict):
    title: Title | None = None
    description: LongText | None = None
    assignee: ShortText | None = None
    assignee_id: PersonId | None = Field(default=None, description="null clears the assignment.")
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
    assignee_email: Email = Field(
        default="", description="Links the task to an existing team member (never creates one)."
    )
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
    mic_probe: str = Field(description="Which mechanism reads the mic state on this OS.")
    mic_probe_error: str | None
    cooldown_remaining_s: float
    blockers: list[str] = Field(description="Why no notification is shown right now (codes).")


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


class TranscriptionStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"  # waiting (queue, or model not installed yet)
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Speaker(StrEnum):
    ME = "me"  # microphone track
    OTHERS = "others"  # system output track


class TranscriptSegment(Strict):
    id: int
    meeting_id: str
    track: TrackKind
    speaker: Speaker
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str


class AnalysisStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"  # waiting (queue, or the LLM is not reachable yet)
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


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
    transcription: TranscriptionStatus = TranscriptionStatus.NONE
    transcription_error: str | None = None
    analysis: AnalysisStatus = AnalysisStatus.NONE
    analysis_error: str | None = None
    language: str | None = None
    task_count: int = 0


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


class ModelProfileId(StrEnum):
    LIGHT = "light"
    BALANCED = "balanced"
    ACCURATE = "accurate"
    BEST = "best"


class ModelProfile(Strict):
    id: ModelProfileId
    label: str
    description: str
    whisper_model: str
    download_mb: int
    min_ram_gb: int
    gpu_recommended: bool
    installed: bool
    recommended: bool


class TranscriptionSettings(Strict):
    profile: ModelProfileId = ModelProfileId.BALANCED
    language: Literal["auto", "fr", "en"] = "auto"
    auto_transcribe: bool = True
    retention_days: Literal[0, 7, 30] = Field(
        default=0,
        description="Days to keep the audio after a successful transcription (0 = delete).",
    )


class TranscriptionSettingsPatch(Strict):
    profile: ModelProfileId | None = None
    language: Literal["auto", "fr", "en"] | None = None
    auto_transcribe: bool | None = None
    retention_days: Literal[0, 7, 30] | None = None


class DownloadStatus(Strict):
    state: Literal["idle", "downloading", "done", "error"]
    profile: ModelProfileId | None = None
    model: str | None = None
    error: str | None = None


class TranscriptionStatusInfo(Strict):
    queue: list[str]
    current_meeting_id: str | None
    progress: float = Field(ge=0, le=1)
    model_installed: bool
    download: DownloadStatus


class ModelDownloadRequest(Strict):
    profile: ModelProfileId


class SearchHit(Strict):
    meeting_id: str
    meeting_title: str
    kind: Literal["title", "summary", "transcript"]
    snippet: str = Field(description="Excerpt; matches wrapped in <mark>…</mark>.")
    start_ms: int | None = None
    speaker: Speaker | None = None


class LenientModel(BaseModel):
    """For model-generated JSON: unknown keys are ignored, then everything is re-validated."""

    model_config = ConfigDict(extra="ignore")


class ExtractedTask(LenientModel):
    title: str = ""
    assignee: str = ""
    due: str | None = Field(default=None, description="ISO date YYYY-MM-DD, only if said.")
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence_timestamp: str | int | float | None = Field(
        default=None, description="Timestamp of the source line: 'mm:ss' or seconds."
    )


class AnalysisOutput(LenientModel):
    """Structured output requested from the LLM (validated by this schema)."""

    title: str = ""
    summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    tasks: list[ExtractedTask] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class Analysis(Strict):
    meeting_id: str
    title: str
    summary: str
    decisions: list[str]
    open_questions: list[str]
    tasks_proposed: int
    provider: str
    model: str
    chunks: int
    tokens_in: int
    tokens_out: int
    created_at: datetime


class UserProfile(Strict):
    """The user's profile (profile.yaml): used to flag the tasks that concern them."""

    name: ShortText = ""
    email: ShortText = ""
    nicknames: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]] = (
        Field(default_factory=list, max_length=20)
    )
    role: ShortText = ""
    team: ShortText = ""
    projects: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = (
        Field(default_factory=list, max_length=50)
    )
    keywords: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = (
        Field(default_factory=list, max_length=50)
    )


class ProfileDocument(Strict):
    yaml: Annotated[str, StringConstraints(max_length=20_000)]
    profile: UserProfile | None = None
    error: str | None = None


class ProfileUpdate(Strict):
    yaml: Annotated[str, StringConstraints(max_length=20_000)]


class LLMSettings(Strict):
    provider: Literal["ollama", "cloud"] = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    model: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] = "qwen2.5:7b-instruct"
    chunk_tokens: int = Field(default=1500, ge=500, le=6000)
    max_tokens_per_meeting: int = Field(default=40_000, ge=2_000, le=500_000)
    auto_analyze: bool = True

    @field_validator("ollama_url")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in (
            "127.0.0.1",
            "localhost",
            "::1",
        ):
            raise ValueError("the local LLM server must be on this machine (127.0.0.1)")
        return value.rstrip("/")


class LLMSettingsPatch(Strict):
    provider: Literal["ollama", "cloud"] | None = None
    ollama_url: str | None = None
    model: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    chunk_tokens: int | None = Field(default=None, ge=500, le=6000)
    max_tokens_per_meeting: int | None = Field(default=None, ge=2_000, le=500_000)
    auto_analyze: bool | None = None


class CloudSettings(Strict):
    """Optional cloud LLM. Disabled by default; sends transcript text off this machine when used."""

    enabled: bool = False
    acknowledged: bool = Field(
        default=False, description="The user confirmed that transcript text leaves the machine."
    )
    base_url: Annotated[str, StringConstraints(max_length=300)] = ""
    model: Annotated[str, StringConstraints(max_length=100)] = ""


class CloudSettingsPatch(Strict):
    enabled: bool | None = None
    acknowledged: bool | None = None
    base_url: Annotated[str, StringConstraints(max_length=300)] | None = None
    model: Annotated[str, StringConstraints(max_length=100)] | None = None


class CloudSettingsView(CloudSettings):
    has_key: bool


class CloudKeyUpdate(Strict):
    key: Annotated[str, StringConstraints(min_length=8, max_length=500)]


class LLMProfileId(StrEnum):
    LIGHT = "light"
    BALANCED = "balanced"
    ACCURATE = "accurate"


class LLMModelProfile(Strict):
    id: LLMProfileId
    label: str
    description: str
    ollama_model: str
    download_gb: float
    min_ram_gb: int
    installed: bool
    recommended: bool


class LLMPullRequest(Strict):
    model: Annotated[
        str, StringConstraints(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:/-]+$")
    ]


class AnalysisStatusInfo(Strict):
    queue: list[str]
    current_meeting_id: str | None
    provider: str
    model: str
    available: bool
    availability_error: str | None
    pull: DownloadStatus


class ProgressSettings(Strict):
    enabled: bool = True
    daily_goal: int = Field(default=3, ge=1, le=20, description="Tasks to complete per day.")


class ProgressSettingsPatch(Strict):
    enabled: bool | None = None
    daily_goal: int | None = Field(default=None, ge=1, le=20)


class DayStat(Strict):
    date: str
    completed: int
    points: int


class CompletedToday(Strict):
    task_id: str
    title: str
    points: int


class TodayProgress(Strict):
    date: str
    completed: int
    goal: int
    goal_reached: bool
    points: int
    tasks: list[CompletedToday]


class Streak(Strict):
    current: int
    best: int


class Level(Strict):
    level: int
    xp: int
    level_start: int
    next_at: int


class PeriodProgress(Strict):
    key: str = Field(description="YYYY-MM for a month, YYYY for a year.")
    completed: int
    points: int
    previous_completed: int
    days: list[DayStat] = Field(description="Only days with activity.")
    goal_days: int = Field(description="Days in the period where the daily goal was reached.")


class Badge(Strict):
    id: str
    label: str
    description: str
    earned: bool
    progress: int
    target: int


class TeamMemberProgress(Strict):
    person_id: str
    name: str
    completed: int


class ProgressSummary(Strict):
    enabled: bool
    today: TodayProgress
    streak: Streak
    level: Level
    month: PeriodProgress
    year: PeriodProgress
    badges: list[Badge]
    team: list[TeamMemberProgress] = Field(
        description="Team completions in the month (no points, no ranking)."
    )


# name -> (model, schema mode). Inputs use "validation", outputs "serialization".
CONTRACT_MODELS: dict[str, tuple[type[BaseModel], Literal["validation", "serialization"]]] = {
    "Task": (Task, "serialization"),
    "TaskProposal": (TaskProposal, "validation"),
    "Person": (Person, "serialization"),
    "ProgressSummary": (ProgressSummary, "serialization"),
    "ProgressSettings": (ProgressSettings, "serialization"),
    "EvidenceRef": (EvidenceRef, "serialization"),
    "Event": (Event, "serialization"),
    "DetectionSettings": (DetectionSettings, "serialization"),
    "DetectionStatus": (DetectionStatus, "serialization"),
    "MeetingDetectedData": (MeetingDetectedData, "serialization"),
    "Meeting": (Meeting, "serialization"),
    "RecordingSettings": (RecordingSettings, "serialization"),
    "RecordingStatus": (RecordingStatus, "serialization"),
    "TranscriptSegment": (TranscriptSegment, "serialization"),
    "TranscriptionSettings": (TranscriptionSettings, "serialization"),
    "ModelProfile": (ModelProfile, "serialization"),
    "SearchHit": (SearchHit, "serialization"),
    "Analysis": (Analysis, "serialization"),
    "AnalysisOutput": (AnalysisOutput, "validation"),
    "UserProfile": (UserProfile, "serialization"),
    "LLMSettings": (LLMSettings, "serialization"),
    "LLMModelProfile": (LLMModelProfile, "serialization"),
}
