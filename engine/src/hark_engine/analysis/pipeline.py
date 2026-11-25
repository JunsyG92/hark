"""Chunk → per-chunk summary → one final extraction pass, under a token budget."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from pydantic import ValidationError

from ..llm import LLMProvider
from ..models import AnalysisOutput, LLMSettings, TranscriptSegment, UserProfile
from .chunking import chunk_lines, est_tokens, to_lines
from .prompts import (
    CHUNK_SYSTEM,
    FINAL_SYSTEM,
    REPAIR,
    final_user_prompt,
)

MAX_TASKS = 30
MAP_OUT_TOKENS = 300
FINAL_OUT_TOKENS = 1200
OVERHEAD_TOKENS = 250


# Flat, reference-free schema sent to the LLM server (structured outputs). Pydantic's own schema
# uses $defs/anyOf, which not every server handles; AnalysisOutput still re-validates the answer.
LLM_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "assignee": {"type": "string"},
                    "due": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence_timestamp": {"type": "string"},
                },
                "required": ["title", "assignee", "due", "confidence", "evidence_timestamp"],
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "decisions", "tasks", "open_questions"],
}


class BudgetExceeded(RuntimeError):
    pass


class InvalidOutput(RuntimeError):
    pass


@dataclass
class Budget:
    limit: int
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def used(self) -> int:
        return self.tokens_in + self.tokens_out

    def add(self, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        if self.used > self.limit:
            raise BudgetExceeded(f"budget de {self.limit} tokens dépassé ({self.used} utilisés)")


@dataclass
class PipelineResult:
    output: AnalysisOutput
    chunks: int
    tokens_in: int
    tokens_out: int
    notes: list[str] = field(default_factory=list)


def estimate_cost(chunk_tokens: list[int]) -> int:
    """Pessimistic token estimate (input + output) before calling the LLM."""
    if len(chunk_tokens) <= 1:
        return sum(chunk_tokens) + OVERHEAD_TOKENS + FINAL_OUT_TOKENS
    map_cost = sum(t + OVERHEAD_TOKENS + MAP_OUT_TOKENS for t in chunk_tokens)
    final_in = len(chunk_tokens) * MAP_OUT_TOKENS + OVERHEAD_TOKENS
    return map_cost + final_in + FINAL_OUT_TOKENS


def ctx_for(prompt_tokens: int, out_tokens: int) -> int:
    need = prompt_tokens + out_tokens + 256
    ctx = 4096
    while ctx < need and ctx < 32768:
        ctx *= 2
    return ctx


# ---- parsing / normalization ------------------------------------------------------------
def parse_output(text: str) -> AnalysisOutput:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise InvalidOutput("no JSON object in the model answer")
    try:
        return AnalysisOutput.model_validate(json.loads(cleaned[start : end + 1]))
    except (ValueError, ValidationError) as exc:
        raise InvalidOutput(f"invalid JSON: {str(exc)[:200]}") from exc


def parse_timestamp(value: str | int | float | None) -> int | None:
    """'mm:ss', 'h:mm:ss', '[mm:ss]' or seconds → milliseconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value * 1000) if value >= 0 else None
    m = re.search(r"(?:(\d+):)?(\d{1,2}):(\d{2})", value)
    if m:
        h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
        return (h * 3600 + mi * 60 + s) * 1000
    if re.fullmatch(r"\s*\d+(\.\d+)?\s*s?\s*", value):
        return int(float(value.strip().rstrip("s")) * 1000)
    return None


def parse_due(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _clean(items: list[str]) -> list[str]:
    return [" ".join(i.split())[:300] for i in items if i.strip()][:20]


def normalize_output(out: AnalysisOutput) -> AnalysisOutput:
    """Enforce the documented limits (summary ≤ 10 lines, bounded lists, clean strings)."""
    lines = [ln.strip() for ln in out.summary.splitlines() if ln.strip()][:10]
    seen: set[str] = set()
    tasks = []
    for t in out.tasks:
        title = " ".join(t.title.split())[:200]
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        tasks.append(
            t.model_copy(update={"title": title, "assignee": " ".join(t.assignee.split())[:200]})
        )
    return AnalysisOutput(
        title=" ".join(out.title.split())[:120],
        summary="\n".join(lines)[:2000],
        decisions=_clean(out.decisions),
        tasks=tasks[:MAX_TASKS],
        open_questions=_clean(out.open_questions),
    )


# ---- the pipeline ---------------------------------------------------------------------------
def run_pipeline(
    provider: LLMProvider,
    segments: list[TranscriptSegment],
    meeting_date: str,
    profile: UserProfile,
    cfg: LLMSettings,
) -> PipelineResult:
    lines = to_lines(segments, profile.name)
    chunks = chunk_lines(lines, cfg.chunk_tokens)
    if not chunks:
        raise InvalidOutput("empty transcript")
    cost = estimate_cost([c.tokens for c in chunks])
    if cost > cfg.max_tokens_per_meeting:
        raise BudgetExceeded(
            f"transcription trop longue pour le budget (≈ {cost} tokens nécessaires, "
            f"budget {cfg.max_tokens_per_meeting}) : augmente le budget ou la taille des blocs"
        )
    budget = Budget(cfg.max_tokens_per_meeting)

    if len(chunks) == 1:
        body, from_notes = chunks[0].text, False
    else:  # one summary per block, then a single final pass over the notes
        notes = []
        for chunk in chunks:
            res = provider.chat(
                CHUNK_SYSTEM,
                chunk.text,
                max_tokens=MAP_OUT_TOKENS,
                num_ctx=ctx_for(chunk.tokens + OVERHEAD_TOKENS, MAP_OUT_TOKENS),
            )
            budget.add(res.tokens_in or chunk.tokens, res.tokens_out or est_tokens(res.text))
            notes.append(res.text.strip())
        body, from_notes = "\n\n".join(notes), True

    user = final_user_prompt(body, meeting_date, profile, from_notes)
    schema = LLM_SCHEMA
    prompt_tokens = est_tokens(user) + est_tokens(FINAL_SYSTEM)
    ctx = ctx_for(prompt_tokens, FINAL_OUT_TOKENS)
    res = provider.chat(
        FINAL_SYSTEM, user, json_schema=schema, max_tokens=FINAL_OUT_TOKENS, num_ctx=ctx
    )
    budget.add(res.tokens_in or prompt_tokens, res.tokens_out or est_tokens(res.text))
    try:
        output = parse_output(res.text)
    except InvalidOutput:
        retry = provider.chat(
            FINAL_SYSTEM,
            f"{user}\n\n{REPAIR}",
            json_schema=schema,
            max_tokens=FINAL_OUT_TOKENS,
            num_ctx=ctx,
        )  # a single repair attempt, still counted in the budget
        budget.add(retry.tokens_in or prompt_tokens, retry.tokens_out or est_tokens(retry.text))
        output = parse_output(retry.text)
    return PipelineResult(
        normalize_output(output), len(chunks), budget.tokens_in, budget.tokens_out
    )
