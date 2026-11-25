"""Runs the detection loop: audio level source + mic probe + state machine → events."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from ..audio.source import LevelSource
from ..events import EventBus
from ..models import (
    DetectionSettings,
    DetectionSettingsPatch,
    DetectionStatus,
    EventType,
    MeetingDetectedData,
    PromptAction,
    PromptResult,
)
from ..store import SettingsRepository
from .machine import DetectionMachine, Prompt
from .probes import MicProbe, MicStatus, NullProbe

log = logging.getLogger(__name__)

PROBE_INTERVAL_S = 2.0
RETRY_SOURCE_S = 5.0


class DetectorService:
    def __init__(
        self,
        settings_repo: SettingsRepository,
        bus: EventBus,
        source: LevelSource | None = None,
        probe: MicProbe | None = None,
        clock: Callable[[], float] = time.monotonic,
        on_accept: Callable[[Prompt], bool] | None = None,
    ) -> None:
        self._repo = settings_repo
        self._bus = bus
        self._source = source
        self._probe = probe or NullProbe()
        self._clock = clock
        # Step 3 plugs the recorder here. Returns True if recording really started.
        self.on_accept = on_accept
        self._lock = threading.RLock()
        self._machine = DetectionMachine(self._repo.get_detection())
        self._level: float | None = None
        self._mic: MicStatus | None = None
        self._error: str | None = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        loops: list[tuple[str, Callable[[], None]]] = [("probe", self._probe_loop)]
        if self._source is not None:
            loops.append(("meter", self._meter_loop))
        for name, target in loops:
            t = threading.Thread(target=target, daemon=True, name=f"detect-{name}")
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)
        self._threads.clear()

    # ---- loops -----------------------------------------------------------------
    def _meter_loop(self) -> None:
        assert self._source is not None  # noqa: S101
        while not self._stop.is_set():
            try:
                for level in self._source.levels(self._stop):
                    self.feed_level(level)
                    if self._stop.is_set():
                        break
                self._error = None
                self._stop.wait(0.5)  # source ended (e.g. default output changed): reopen
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"[:300]
                with self._lock:
                    self._level = None
                if message != self._error:  # log once per distinct failure, not every retry
                    log.warning("audio level source failed (%s); retrying", message)
                self._error = message
                self._stop.wait(RETRY_SOURCE_S)

    def _probe_loop(self) -> None:
        while not self._stop.is_set():
            try:
                status = self._probe.read()
            except Exception:
                log.exception("mic probe failed")
                status = None
            with self._lock:
                self._mic = status
                self._machine.poll(self._clock())
            self._stop.wait(PROBE_INTERVAL_S)

    # ---- core (also called directly by tests) -----------------------------------
    def feed_level(self, level_db: float) -> None:
        now = self._clock()
        with self._lock:
            self._level = level_db
            mic = self._mic
            app = mic.apps[0] if mic and mic.apps else ""
            prompt = self._machine.feed(now, level_db, mic.in_use if mic else None, app)
        if prompt:
            self._announce(prompt)

    def _announce(self, prompt: Prompt) -> None:
        with self._lock:
            seconds = self._machine.settings.prompt_seconds
        data = MeetingDetectedData(
            prompt_id=prompt.id, app=prompt.app, level_db=prompt.level_db, prompt_seconds=seconds
        )
        self._bus.publish(EventType.MEETING_DETECTED, data.model_dump(mode="json"))

    def respond(self, prompt_id: str, action: PromptAction) -> PromptResult:
        with self._lock:
            prompt = self._machine.prompt
            matched = self._machine.respond(self._clock(), prompt_id, action)
        started = False
        if matched and action is PromptAction.RECORD and prompt and self.on_accept:
            started = bool(self.on_accept(prompt))
            if not started:
                with self._lock:
                    self._machine.set_recording(False, self._clock())
        elif matched and action is PromptAction.RECORD:
            with self._lock:  # no recorder yet (step 3): behave like "ignore"
                self._machine.set_recording(False, self._clock())
        return PromptResult(ok=matched, recording_started=started)

    def test_prompt(self) -> bool:
        with self._lock:
            prompt = self._machine.force_prompt(self._clock(), app="test")
        if prompt:
            self._announce(prompt)
        return prompt is not None

    # ---- settings / status -------------------------------------------------------
    def get_settings(self) -> DetectionSettings:
        with self._lock:
            return self._machine.settings

    def patch_settings(self, patch: DetectionSettingsPatch) -> DetectionSettings:
        new = self._repo.patch_detection(patch)
        with self._lock:
            self._machine.update_settings(new)
        return new

    def status(self) -> DetectionStatus:
        now = self._clock()
        with self._lock:
            mic = self._mic
            return DetectionStatus(
                phase=self._machine.phase,
                level_db=self._level,
                above_threshold_seconds=round(self._machine.above_seconds(now), 1),
                mic_in_use=mic.in_use if mic else None,
                mic_apps=list(mic.apps) if mic else [],
                audio_source=self._source.name if self._source else None,
                error=self._error,
            )
