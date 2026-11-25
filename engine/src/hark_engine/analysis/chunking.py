"""Transcript → lines → token-bounded chunks (pure)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..export import format_ts
from ..models import Speaker, TranscriptSegment


def est_tokens(text: str) -> int:
    """Cheap token estimate (≈ 3.2 chars/token, French/English); real counts come from the LLM."""
    return max(1, math.ceil(len(text) / 3.2))


@dataclass(frozen=True)
class Line:
    start_ms: int
    text: str  # "[mm:ss] Moi: ..."


@dataclass(frozen=True)
class Chunk:
    start_ms: int
    end_ms: int
    text: str
    tokens: int


def speaker_label(speaker: Speaker, user_name: str) -> str:
    if speaker is Speaker.ME:
        return f"Moi ({user_name})" if user_name else "Moi"
    return "Autres"


def to_lines(segments: list[TranscriptSegment], user_name: str = "") -> list[Line]:
    return [
        Line(
            s.start_ms, f"[{format_ts(s.start_ms)}] {speaker_label(s.speaker, user_name)}: {s.text}"
        )
        for s in segments
        if s.text.strip()
    ]


def transcript_text(segments: list[TranscriptSegment]) -> str:
    """Canonical text of a transcript (used for the cache hash)."""
    return "\n".join(f"{s.start_ms}|{s.speaker.value}|{s.text}" for s in segments)


def chunk_lines(lines: list[Line], max_tokens: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    buf: list[Line] = []
    used = 0
    for line in lines:
        t = est_tokens(line.text) + 1
        if buf and used + t > max_tokens:
            chunks.append(_make(buf, used))
            buf, used = [], 0
        buf.append(line)
        used += t
    if buf:
        chunks.append(_make(buf, used))
    return chunks


def _make(buf: list[Line], tokens: int) -> Chunk:
    return Chunk(buf[0].start_ms, buf[-1].start_ms, "\n".join(x.text for x in buf), tokens)
