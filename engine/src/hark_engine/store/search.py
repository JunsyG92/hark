"""FTS5 index helpers (SQLite full-text search). Functions take an open connection/transaction."""

from __future__ import annotations

import re
import sqlite3

_WORD = re.compile(r"[\w]+", re.UNICODE)


def build_match(query: str) -> str | None:
    """Turn free user text into a safe FTS5 query: quoted terms (AND), prefix on the last one."""
    words = _WORD.findall(query)
    if not words:
        return None
    terms = [f'"{w}"' for w in words]
    terms[-1] += "*"
    return " ".join(terms)


def index_title(conn: sqlite3.Connection, meeting_id: str, title: str) -> None:
    conn.execute("DELETE FROM search WHERE meeting_id = ? AND kind = 'title'", (meeting_id,))
    if title.strip():
        conn.execute(
            "INSERT INTO search (text, meeting_id, kind, segment_id) VALUES (?, ?, 'title', NULL)",
            (title, meeting_id),
        )


def index_segment(conn: sqlite3.Connection, meeting_id: str, segment_id: int, text: str) -> None:
    conn.execute(
        "INSERT INTO search (text, meeting_id, kind, segment_id) VALUES (?, ?, 'transcript', ?)",
        (text, meeting_id, segment_id),
    )


def clear_meeting(conn: sqlite3.Connection, meeting_id: str, kind: str | None = None) -> None:
    if kind is None:
        conn.execute("DELETE FROM search WHERE meeting_id = ?", (meeting_id,))
    else:
        conn.execute("DELETE FROM search WHERE meeting_id = ? AND kind = ?", (meeting_id, kind))


def query(conn: sqlite3.Connection, text: str, limit: int = 30) -> list[sqlite3.Row]:
    match = build_match(text)
    if match is None:
        return []
    return conn.execute(
        """SELECT s.meeting_id, s.kind, s.segment_id,
                  snippet(search, 0, '<mark>', '</mark>', '…', 14) AS snippet,
                  m.title AS meeting_title,
                  t.start_ms AS start_ms, t.speaker AS speaker
           FROM search s
           JOIN meetings m ON m.id = s.meeting_id
           LEFT JOIN transcript_segments t ON t.id = s.segment_id
           WHERE search MATCH ?
           ORDER BY rank
           LIMIT ?""",
        (match, limit),
    ).fetchall()
