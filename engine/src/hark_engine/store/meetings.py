"""Meeting persistence (audio paths stay internal: the API only exposes `audio_available`)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..models import Meeting, MeetingStatus, TrackKind
from .db import Database


class MeetingNotFound(LookupError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_meeting(row: sqlite3.Row) -> Meeting:
    paths = {TrackKind.SYSTEM: row["system_path"], TrackKind.MIC: row["mic_path"]}
    tracks = [k for k, p in paths.items() if p]
    return Meeting(
        id=row["id"],
        title=row["title"],
        status=MeetingStatus(row["status"]),
        app=row["app"],
        started_at=datetime.fromisoformat(row["started_at"]),
        ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
        duration_ms=row["duration_ms"],
        tracks=tracks,
        audio_available=any(Path(p).exists() for p in paths.values() if p),
    )


class MeetingRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self, meeting_id: str, title: str, app: str, paths: dict[TrackKind, Path]
    ) -> Meeting:
        with self.db.tx() as conn:
            conn.execute(
                "INSERT INTO meetings (id, title, status, app, started_at, system_path, mic_path) "
                "VALUES (?, ?, 'recording', ?, ?, ?, ?)",
                (
                    meeting_id,
                    title,
                    app,
                    _now(),
                    str(paths[TrackKind.SYSTEM]) if TrackKind.SYSTEM in paths else None,
                    str(paths[TrackKind.MIC]) if TrackKind.MIC in paths else None,
                ),
            )
        return self.get(meeting_id)

    def finish(self, meeting_id: str, status: MeetingStatus, duration_ms: int) -> Meeting:
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE meetings SET status = ?, ended_at = ?, duration_ms = ? WHERE id = ?",
                (status.value, _now(), duration_ms, meeting_id),
            )
        return self.get(meeting_id)

    def set_title(self, meeting_id: str, title: str) -> Meeting:
        with self.db.tx() as conn:
            cur = conn.execute("UPDATE meetings SET title = ? WHERE id = ?", (title, meeting_id))
            if cur.rowcount == 0:
                raise MeetingNotFound(meeting_id)
        return self.get(meeting_id)

    def get(self, meeting_id: str) -> Meeting:
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise MeetingNotFound(meeting_id)
        return _row_to_meeting(row)

    def list_recent(self, limit: int = 50, offset: int = 0) -> list[Meeting]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM meetings ORDER BY started_at DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        return [_row_to_meeting(r) for r in rows]

    def track_paths(self, meeting_id: str) -> dict[TrackKind, Path]:
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT system_path, mic_path FROM meetings WHERE id = ?", (meeting_id,)
            ).fetchone()
        if row is None:
            raise MeetingNotFound(meeting_id)
        out: dict[TrackKind, Path] = {}
        if row["system_path"]:
            out[TrackKind.SYSTEM] = Path(row["system_path"])
        if row["mic_path"]:
            out[TrackKind.MIC] = Path(row["mic_path"])
        return out

    def interrupted(self) -> list[Meeting]:
        with self.db.read() as conn:
            rows = conn.execute("SELECT * FROM meetings WHERE status = 'recording'").fetchall()
        return [_row_to_meeting(r) for r in rows]
