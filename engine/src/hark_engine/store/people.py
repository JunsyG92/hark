"""Team directory (people tasks can be assigned to)."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
import uuid
from datetime import UTC, datetime

from ..models import Person, PersonCreate, PersonUpdate
from .db import Database


class PersonNotFound(LookupError):
    pass


class DuplicateEmail(ValueError):
    pass


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def full_name(p: Person) -> str:
    return " ".join(x for x in (p.first_name, p.last_name) if x) or p.email


def _row(row: sqlite3.Row) -> Person:
    return Person(
        id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        email=row["email"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class PeopleRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self) -> list[Person]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM people ORDER BY first_name COLLATE NOCASE, last_name COLLATE NOCASE"
            ).fetchall()
        return [_row(r) for r in rows]

    def get(self, person_id: str) -> Person:
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
        if row is None:
            raise PersonNotFound(person_id)
        return _row(row)

    def find_by_email(self, email: str) -> Person | None:
        if not email:
            return None
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM people WHERE email = ?", (email.lower(),)).fetchone()
        return _row(row) if row else None

    def create(self, data: PersonCreate) -> Person:
        pid = uuid.uuid4().hex
        try:
            with self.db.tx() as conn:
                conn.execute(
                    "INSERT INTO people (id, first_name, last_name, email, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        pid,
                        data.first_name,
                        data.last_name,
                        data.email,
                        datetime.now(UTC).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateEmail(data.email) from exc
        return self.get(pid)

    def update(self, person_id: str, data: PersonUpdate) -> Person:
        current = self.get(person_id)
        fields = data.model_dump(exclude_unset=True, exclude_none=True)
        merged = current.model_copy(update=fields)
        if not (merged.first_name or merged.last_name):
            raise ValueError("prénom ou nom obligatoire")
        try:
            with self.db.tx() as conn:
                conn.execute(
                    "UPDATE people SET first_name = ?, last_name = ?, email = ? WHERE id = ?",
                    (merged.first_name, merged.last_name, merged.email, person_id),
                )
                # keep the free-text assignee of their tasks readable (exports, plugins)
                conn.execute(
                    "UPDATE tasks SET assignee = ? WHERE assignee_id = ?",
                    (full_name(merged), person_id),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateEmail(merged.email) from exc
        return self.get(person_id)

    def delete(self, person_id: str) -> None:
        """Tasks keep the person's name as free text; the link is cleared (ON DELETE SET NULL)."""
        with self.db.tx() as conn:
            cur = conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
            if cur.rowcount == 0:
                raise PersonNotFound(person_id)

    def match(self, spoken: str) -> Person | None:
        """Resolve a name heard in a meeting ("Paul", "paul durand", an e-mail) to ONE person.

        Returns None when nothing or several people match: the user then assigns by hand.
        """
        key = _norm(spoken)
        if not key:
            return None
        people = self.list()
        for p in people:
            if p.email and key == p.email:
                return p
        exact = [p for p in people if _norm(full_name(p)) == key]
        if len(exact) == 1:
            return exact[0]
        first = [p for p in people if p.first_name and _norm(p.first_name) == key]
        if len(first) == 1:
            return first[0]
        last = [p for p in people if p.last_name and _norm(p.last_name) == key]
        return last[0] if len(last) == 1 else None
