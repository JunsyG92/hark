"""Key/value settings stored as JSON."""

from __future__ import annotations

import json

from ..models import (
    DetectionSettings,
    DetectionSettingsPatch,
    RecordingSettings,
    RecordingSettingsPatch,
)
from .db import Database

DETECTION_KEY = "detection"
RECORDING_KEY = "recording"


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_detection(self) -> DetectionSettings:
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (DETECTION_KEY,)
            ).fetchone()
        if row is None:
            return DetectionSettings()
        try:
            return DetectionSettings.model_validate(json.loads(row["value"]))
        except ValueError:
            return DetectionSettings()

    def patch_detection(self, patch: DetectionSettingsPatch) -> DetectionSettings:
        merged = self.get_detection().model_copy(update=patch.model_dump(exclude_none=True))
        validated = DetectionSettings.model_validate(merged.model_dump())
        with self.db.tx() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (DETECTION_KEY, validated.model_dump_json()),
            )
        return validated

    def get_recording(self) -> RecordingSettings:
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (RECORDING_KEY,)
            ).fetchone()
        if row is None:
            return RecordingSettings()
        try:
            return RecordingSettings.model_validate(json.loads(row["value"]))
        except ValueError:
            return RecordingSettings()

    def patch_recording(self, patch: RecordingSettingsPatch) -> RecordingSettings:
        merged = self.get_recording().model_copy(update=patch.model_dump(exclude_none=True))
        validated = RecordingSettings.model_validate(merged.model_dump())
        with self.db.tx() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (RECORDING_KEY, validated.model_dump_json()),
            )
        return validated
