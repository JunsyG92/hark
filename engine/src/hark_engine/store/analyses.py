"""Analysis persistence + search indexing of summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from ..models import Analysis
from .db import Database


@dataclass(frozen=True)
class StoredAnalysis:
    analysis: Analysis
    input_hash: str
    prompt_version: str


class AnalysisRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, meeting_id: str) -> StoredAnalysis | None:
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT * FROM analyses WHERE meeting_id = ?", (meeting_id,)
            ).fetchone()
        if row is None:
            return None
        return StoredAnalysis(
            Analysis(
                meeting_id=row["meeting_id"],
                title=row["title"],
                summary=row["summary"],
                decisions=json.loads(row["decisions"]),
                open_questions=json.loads(row["open_questions"]),
                tasks_proposed=row["tasks_proposed"],
                provider=row["provider"],
                model=row["model"],
                chunks=row["chunks"],
                tokens_in=row["tokens_in"],
                tokens_out=row["tokens_out"],
                created_at=datetime.fromisoformat(row["created_at"]),
            ),
            row["input_hash"],
            row["prompt_version"],
        )

    def save(self, a: Analysis, input_hash: str, prompt_version: str) -> None:
        with self.db.tx() as conn:
            conn.execute(
                """INSERT INTO analyses (meeting_id, input_hash, prompt_version, provider, model, title,
                       summary, decisions, open_questions, tasks_proposed, chunks, tokens_in, tokens_out,
                       created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(meeting_id) DO UPDATE SET
                       input_hash = excluded.input_hash, prompt_version = excluded.prompt_version,
                       provider = excluded.provider, model = excluded.model, title = excluded.title,
                       summary = excluded.summary, decisions = excluded.decisions,
                       open_questions = excluded.open_questions, tasks_proposed = excluded.tasks_proposed,
                       chunks = excluded.chunks, tokens_in = excluded.tokens_in,
                       tokens_out = excluded.tokens_out, created_at = excluded.created_at""",
                (
                    a.meeting_id, input_hash, prompt_version, a.provider, a.model, a.title, a.summary,
                    json.dumps(a.decisions, ensure_ascii=False),
                    json.dumps(a.open_questions, ensure_ascii=False),
                    a.tasks_proposed, a.chunks, a.tokens_in, a.tokens_out,
                    datetime.now(UTC).isoformat(),
                ),
            )  # fmt: skip
            conn.execute(
                "DELETE FROM search WHERE meeting_id = ? AND kind = 'summary'", (a.meeting_id,)
            )
            text = "\n".join([a.summary, *a.decisions, *a.open_questions]).strip()
            if text:
                conn.execute(
                    "INSERT INTO search (text, meeting_id, kind, segment_id) "
                    "VALUES (?, ?, 'summary', NULL)",
                    (text, a.meeting_id),
                )
