"""Task persistence."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, date, datetime
from typing import Any

from ..models import (
    Column,
    EvidenceRef,
    Priority,
    Task,
    TaskCreate,
    TaskMove,
    TaskProposal,
    TaskUpdate,
)
from .db import Database


class TaskNotFound(LookupError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_task(row: sqlite3.Row) -> Task:
    evidence = None
    if row["evidence_meeting_id"]:
        evidence = EvidenceRef(
            meeting_id=row["evidence_meeting_id"],
            start_ms=row["evidence_start_ms"] or 0,
            end_ms=row["evidence_end_ms"],
        )
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        assignee=row["assignee"],
        due=date.fromisoformat(row["due"]) if row["due"] else None,
        priority=Priority(row["priority"]),
        column=Column(row["column"]),
        position=row["position"],
        source=row["source"],
        evidence=evidence,
        is_mine=bool(row["is_mine"]),
        assignee_id=row["assignee_id"],
        confidence=row["confidence"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class TaskRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- reads -----------------------------------------------------------------
    def list(
        self,
        column: Column | None = None,
        source: str | None = None,
        assignee_id: str | None = None,
    ) -> list[Task]:
        clauses: list[str] = []
        params: list[Any] = []
        if assignee_id is not None:
            clauses.append("assignee_id = ?")
            params.append(assignee_id)
        if column is not None:
            clauses.append('"column" = ?')
            params.append(column.value)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f'SELECT * FROM tasks {where} ORDER BY "column", position'  # noqa: S608
        with self.db.read() as conn:
            return [_row_to_task(r) for r in conn.execute(sql, params)]

    def get(self, task_id: str) -> Task:
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskNotFound(task_id)
        return _row_to_task(row)

    # ---- writes ----------------------------------------------------------------
    def _insert(
        self,
        *,
        title: str,
        description: str,
        assignee: str,
        due: date | None,
        priority: Priority,
        column: Column,
        source: str,
        evidence: EvidenceRef | None = None,
        is_mine: bool = False,
        confidence: float | None = None,
        assignee_id: str | None = None,
    ) -> Task:
        task_id = uuid.uuid4().hex
        now = _now()
        with self.db.tx() as conn:
            (max_pos,) = conn.execute(
                'SELECT COALESCE(MAX(position), -1) FROM tasks WHERE "column" = ?',
                (column.value,),
            ).fetchone()
            conn.execute(
                """INSERT INTO tasks (id, title, description, assignee, due, priority, "column",
                       position, source, evidence_meeting_id, evidence_start_ms, evidence_end_ms,
                       is_mine, confidence, created_at, updated_at, assignee_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    title,
                    description,
                    assignee,
                    due.isoformat() if due else None,
                    priority.value,
                    column.value,
                    float(max_pos) + 1.0,
                    source,
                    evidence.meeting_id if evidence else None,
                    evidence.start_ms if evidence else None,
                    evidence.end_ms if evidence else None,
                    int(is_mine),
                    confidence,
                    now,
                    now,
                    assignee_id,
                ),
            )
        return self.get(task_id)

    def create(self, data: TaskCreate, *, is_mine: bool = False) -> Task:
        return self._insert(
            title=data.title,
            description=data.description,
            assignee=data.assignee,
            due=data.due,
            priority=data.priority,
            column=data.column,
            source="manual",
            assignee_id=data.assignee_id,
            is_mine=is_mine,
        )

    def propose(
        self,
        data: TaskProposal,
        *,
        source: str,
        is_mine: bool = False,
        assignee_id: str | None = None,
    ) -> Task:
        """Integrations / AI only ever land in `to_validate`."""
        return self._insert(
            title=data.title,
            description=data.description,
            assignee=data.assignee,
            due=data.due,
            priority=data.priority,
            column=Column.TO_VALIDATE,
            source=source,
            evidence=data.evidence,
            is_mine=is_mine,
            confidence=data.confidence,
            assignee_id=assignee_id,
        )

    def update(self, task_id: str, data: TaskUpdate) -> Task:
        fields = data.model_dump(exclude_unset=True)
        if not fields:
            return self.get(task_id)
        sets: list[str] = []
        params: list[Any] = []
        for key, value in fields.items():
            if key == "due":
                value = value.isoformat() if value else None
            elif key == "priority":
                value = Priority(value).value
            elif key == "is_mine":
                value = int(value)
            sets.append(f"{key} = ?")
            params.append(value)
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(task_id)
        with self.db.tx() as conn:
            cur = conn.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?",  # noqa: S608 - keys are model fields
                params,
            )
            if cur.rowcount == 0:
                raise TaskNotFound(task_id)
        return self.get(task_id)

    def move(self, task_id: str, data: TaskMove) -> Task:
        with self.db.tx() as conn:
            row = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise TaskNotFound(task_id)
            ids = [
                r["id"]
                for r in conn.execute(
                    'SELECT id FROM tasks WHERE "column" = ? AND id != ? ORDER BY position',
                    (data.column.value, task_id),
                )
            ]
            index = min(data.index, len(ids))
            ids.insert(index, task_id)
            now = _now()
            for pos, tid in enumerate(ids):
                if tid == task_id:
                    conn.execute(
                        'UPDATE tasks SET "column" = ?, position = ?, updated_at = ? WHERE id = ?',
                        (data.column.value, float(pos), now, tid),
                    )
                else:
                    conn.execute("UPDATE tasks SET position = ? WHERE id = ?", (float(pos), tid))
        return self.get(task_id)

    def delete(self, task_id: str) -> None:
        with self.db.tx() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cur.rowcount == 0:
                raise TaskNotFound(task_id)
