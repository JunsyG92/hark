"""End-of-meeting detection: pure, clock-injected.

After `silence_s` without any voice (system or mic) it reports SILENT. It reports SILENT again each
further `silence_s` while the silence lasts (so a dismissed question comes back), and
VOICE_RETURNED once when someone speaks again after a SILENT. It never stops anything by itself.
"""

from __future__ import annotations

from enum import StrEnum


class SilenceEvent(StrEnum):
    SILENT = "silent"
    VOICE_RETURNED = "voice_returned"


class SilenceTracker:
    def __init__(self, silence_s: float, now: float) -> None:
        self.silence_s = silence_s
        self._last_voice = now
        self._prompted_at: float | None = None

    @property
    def prompted(self) -> bool:
        return self._prompted_at is not None

    def silent_seconds(self, now: float) -> float:
        return max(0.0, now - self._last_voice)

    def feed(self, now: float, voice: bool) -> SilenceEvent | None:
        if voice:
            self._last_voice = now
            if self._prompted_at is not None:
                self._prompted_at = None
                return SilenceEvent.VOICE_RETURNED
            return None
        if now - self._last_voice >= self.silence_s and (
            self._prompted_at is None or now - self._prompted_at >= self.silence_s
        ):
            self._prompted_at = now
            return SilenceEvent.SILENT
        return None
