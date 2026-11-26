"""Meeting persistence (audio paths stay internal: the API only exposes `audio_available`)."""

from __future__ import annotations

import contextlib
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..models import (
    AnalysisStatus,
    Meeting,
    MeetingStatus,
    Speaker,
    TrackKind,
    TranscriptionStatus,
    TranscriptSegment,
)
from . import search
from .db import Database

_SELECT = """SELECT meetings.*,
    (SELECT COUNT(*) FROM tasks WHERE tasks.source = 'meeting:' || meetings.id) AS task_count
    FROM meetings"""


class MeetingNotFound(LookupError):
    pass


@dataclass(frozen=True)
class NewSegment:
    track: TrackKind
    speaker: Speaker
    start_ms: int
    end_ms: int
    text: str


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
        transcription=TranscriptionStatus(row["transcription"]),
        transcription_error=row["transcription_error"],
        language=row["language"],
        task_count=row["task_count"],
        analysis=AnalysisStatus(row["analysis"]),
        analysis_error=row["analysis_error"],
    )


class MeetingRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- lifecycle ---------------------------------------------------------------
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
            search.index_title(conn, meeting_id, title)
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
            search.index_title(conn, meeting_id, title)
        return self.get(meeting_id)

    def delete(self, meeting_id: str) -> None:
        """Remove the meeting, its transcript, its search entries and any audio left on disk."""
        paths = self.track_paths(meeting_id)
        with self.db.tx() as conn:
            search.clear_meeting(conn, meeting_id)
            conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))  # cascades segments
        self.delete_audio_files(paths)

    # ---- reads ---------------------------------------------------------------------
    def get(self, meeting_id: str) -> Meeting:
        with self.db.read() as conn:
            row = conn.execute(f"{_SELECT} WHERE id = ?", (meeting_id,)).fetchone()  # noqa: S608
        if row is None:
            raise MeetingNotFound(meeting_id)
        return _row_to_meeting(row)

    def list_recent(self, limit: int = 50, offset: int = 0) -> list[Meeting]:
        with self.db.read() as conn:
            rows = conn.execute(
                f"{_SELECT} ORDER BY started_at DESC LIMIT ? OFFSET ?",  # noqa: S608
                (limit, offset),
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
            rows = conn.execute(f"{_SELECT} WHERE status = 'recording'").fetchall()  # noqa: S608
        return [_row_to_meeting(r) for r in rows]

    def pending_transcription(self) -> list[str]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT id FROM meetings WHERE transcription = 'pending' ORDER BY started_at"
            ).fetchall()
        return [r["id"] for r in rows]

    # ---- transcription state -------------------------------------------------------
    def set_transcription(
        self,
        meeting_id: str,
        status: TranscriptionStatus,
        error: str | None = None,
        language: str | None = None,
    ) -> Meeting:
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE meetings SET transcription = ?, transcription_error = ?, "
                "language = COALESCE(?, language) WHERE id = ?",
                (status.value, error, language, meeting_id),
            )
        return self.get(meeting_id)

    def set_analysis(
        self, meeting_id: str, status: AnalysisStatus, error: str | None = None
    ) -> Meeting:
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE meetings SET analysis = ?, analysis_error = ? WHERE id = ?",
                (status.value, error, meeting_id),
            )
        return self.get(meeting_id)

    def requeue_interrupted(self) -> tuple[int, int]:
        """Work left `running` by a quit/crash goes back to `pending` (else stuck forever)."""
        with self.db.tx() as conn:
            t = conn.execute(
                "UPDATE meetings SET transcription = 'pending', transcription_error = NULL "
                "WHERE transcription = 'running'"
            ).rowcount
            a = conn.execute(
                "UPDATE meetings SET analysis = 'pending', analysis_error = NULL "
                "WHERE analysis = 'running'"
            ).rowcount
        return t, a

    def pending_analysis(self) -> list[str]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT id FROM meetings WHERE analysis = 'pending' ORDER BY started_at"
            ).fetchall()
        return [r["id"] for r in rows]

    def replace_segments(self, meeting_id: str, segments: list[NewSegment]) -> int:
        with self.db.tx() as conn:
            conn.execute("DELETE FROM transcript_segments WHERE meeting_id = ?", (meeting_id,))
            search.clear_meeting(conn, meeting_id, "transcript")
            for seg in segments:
                cur = conn.execute(
                    "INSERT INTO transcript_segments "
                    "(meeting_id, track, speaker, start_ms, end_ms, text) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        meeting_id,
                        seg.track.value,
                        seg.speaker.value,
                        seg.start_ms,
                        seg.end_ms,
                        seg.text,
                    ),
                )
                assert cur.lastrowid is not None  # noqa: S101
                search.index_segment(conn, meeting_id, cur.lastrowid, seg.text)
        return len(segments)

    def segments(self, meeting_id: str) -> list[TranscriptSegment]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM transcript_segments WHERE meeting_id = ? ORDER BY start_ms, id",
                (meeting_id,),
            ).fetchall()
        return [
            TranscriptSegment(
                id=r["id"],
                meeting_id=r["meeting_id"],
                track=TrackKind(r["track"]),
                speaker=Speaker(r["speaker"]),
                start_ms=r["start_ms"],
                end_ms=r["end_ms"],
                text=r["text"],
            )
            for r in rows
        ]

    def search(self, text: str, limit: int = 30) -> list[sqlite3.Row]:
        with self.db.read() as conn:
            return search.query(conn, text, limit)

    # ---- audio retention -----------------------------------------------------------
    def set_audio_expiry(self, meeting_id: str, days: int | None) -> None:
        expires = (datetime.now(UTC) + timedelta(days=days)).isoformat() if days else None
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE meetings SET audio_expires_at = ? WHERE id = ?", (expires, meeting_id)
            )

    def expired_audio(self) -> list[str]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT id FROM meetings "
                "WHERE audio_expires_at IS NOT NULL AND audio_expires_at <= ?",
                (_now(),),
            ).fetchall()
        return [r["id"] for r in rows]

    def delete_audio(self, meeting_id: str) -> None:
        """Delete the audio files (keeps the meeting, transcript and tasks)."""
        self.delete_audio_files(self.track_paths(meeting_id))
        self.set_audio_expiry(meeting_id, None)

    @staticmethod
    def delete_audio_files(paths: dict[TrackKind, Path]) -> None:
        folders: set[Path] = set()
        for path in paths.values():
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)
            folders.add(path.parent)
        for folder in folders:
            with contextlib.suppress(OSError):
                if folder.is_dir() and not any(folder.iterdir()):
                    shutil.rmtree(folder)
