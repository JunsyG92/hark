"""Pure meeting-detection state machine (no I/O, injectable clock).

idle ──(audio ≥ threshold for N s AND mic used by another app)──► prompted
prompted ──record──► recording      ──decline/ignore/timeout──► cooldown ──► idle

Nothing here records anything: a prompt is only a question for the user.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from ..models import DetectionPhase, DetectionSettings, PromptAction

GAP_TOLERANCE_S = 2.0  # speech has pauses: short dips do not reset the timer


@dataclass(frozen=True)
class Prompt:
    id: str
    app: str
    level_db: float
    expires_at: float


class DetectionMachine:
    def __init__(self, settings: DetectionSettings) -> None:
        self.settings = settings
        self.prompt: Prompt | None = None
        self._phase = DetectionPhase.IDLE
        self._above_since: float | None = None
        self._last_above = 0.0
        self._cooldown_until = 0.0

    # ---- state -----------------------------------------------------------------
    @property
    def phase(self) -> DetectionPhase:
        return DetectionPhase.DISABLED if not self.settings.enabled else self._phase

    def above_seconds(self, now: float) -> float:
        return 0.0 if self._above_since is None else max(0.0, now - self._above_since)

    def cooldown_remaining(self, now: float) -> float:
        if self._phase is not DetectionPhase.COOLDOWN:
            return 0.0
        return max(0.0, self._cooldown_until - now)

    def blockers(self, now: float, level_db: float | None, mic_in_use: bool | None) -> list[str]:
        """Human-diagnosable reasons why no prompt is shown right now (codes, see the UI)."""
        s = self.settings
        if not s.enabled:
            return ["disabled"]
        if self._phase is DetectionPhase.PROMPTED:
            return ["prompt_showing"]
        if self._phase is DetectionPhase.RECORDING:
            return ["recording"]
        if self._phase is DetectionPhase.COOLDOWN:
            return ["cooldown"]
        out: list[str] = []
        if level_db is None:
            out.append("no_audio")
        elif self._above_since is None:
            out.append("below_threshold")
        elif self.above_seconds(now) < s.min_seconds:
            out.append("waiting_duration")
        if s.require_mic_in_use and mic_in_use is False:
            out.append("mic_not_in_use")
        return out

    def update_settings(self, settings: DetectionSettings) -> None:
        self.settings = settings
        if not settings.enabled:
            self.prompt = None
            if self._phase is DetectionPhase.PROMPTED:
                self._phase = DetectionPhase.IDLE
            self._reset_candidate()

    # ---- inputs ----------------------------------------------------------------
    def poll(self, now: float) -> None:
        """Handle time-based transitions (prompt timeout, cooldown end)."""
        if self._phase is DetectionPhase.PROMPTED and self.prompt and now >= self.prompt.expires_at:
            self._start_cooldown(now, self.settings.cooldown_ignore_minutes)
        elif self._phase is DetectionPhase.COOLDOWN and now >= self._cooldown_until:
            self._phase = DetectionPhase.IDLE
            self._reset_candidate()

    def feed(
        self, now: float, level_db: float, mic_in_use: bool | None, app: str = ""
    ) -> Prompt | None:
        """Feed one audio level. Returns a Prompt when the user should be asked."""
        self.poll(now)
        if not self.settings.enabled or self._phase is not DetectionPhase.IDLE:
            return None

        if level_db >= self.settings.threshold_db:
            if self._above_since is None:
                self._above_since = now
            self._last_above = now
        elif self._above_since is not None and now - self._last_above > GAP_TOLERANCE_S:
            self._reset_candidate()

        if self._above_since is None or now - self._above_since < self.settings.min_seconds:
            return None
        if self.settings.require_mic_in_use and mic_in_use is False:
            return None  # e.g. a YouTube video alone: loud, but no app is using the mic
        # mic_in_use is None = the OS does not tell us: do not block (the user can still say "Non")
        return self._open_prompt(now, level_db, app or "application inconnue")

    def force_prompt(self, now: float, app: str = "test") -> Prompt | None:
        """Manual test of the notification (settings button)."""
        self.poll(now)
        if self._phase is not DetectionPhase.IDLE:
            return None
        return self._open_prompt(now, self.settings.threshold_db, app)

    def respond(self, now: float, prompt_id: str, action: PromptAction) -> bool:
        """User answer. Returns True if it matched the open prompt."""
        self.poll(now)
        if self._phase is not DetectionPhase.PROMPTED or not self.prompt:
            return False
        if self.prompt.id != prompt_id:
            return False
        if action is PromptAction.RECORD:
            self._phase = DetectionPhase.RECORDING
            self.prompt = None
        elif action is PromptAction.DECLINE:
            self._start_cooldown(now, self.settings.cooldown_decline_minutes)
        else:
            self._start_cooldown(now, self.settings.cooldown_ignore_minutes)
        return True

    def set_recording(self, recording: bool, now: float = 0.0) -> None:
        """Called by the recorder: no new prompt while recording."""
        if recording:
            self._phase = DetectionPhase.RECORDING
            self.prompt = None
            self._reset_candidate()
        elif self._phase is DetectionPhase.RECORDING:
            self._start_cooldown(now, self.settings.cooldown_ignore_minutes)

    # ---- internals -------------------------------------------------------------
    def _open_prompt(self, now: float, level_db: float, app: str) -> Prompt:
        self.prompt = Prompt(uuid.uuid4().hex, app, level_db, now + self.settings.prompt_seconds)
        self._phase = DetectionPhase.PROMPTED
        self._reset_candidate()
        return self.prompt

    def _start_cooldown(self, now: float, minutes: float) -> None:
        self.prompt = None
        self._phase = DetectionPhase.COOLDOWN
        self._cooldown_until = now + minutes * 60.0
        self._reset_candidate()

    def _reset_candidate(self) -> None:
        self._above_since = None
