"""Markdown export of a meeting (pure)."""

from __future__ import annotations

from .models import Meeting, Speaker, Task, TranscriptSegment

SPEAKER_LABEL = {Speaker.ME: "Moi", Speaker.OTHERS: "Autres"}


def display_title(meeting: Meeting) -> str:
    if meeting.title.strip():
        return meeting.title.strip()
    return f"Réunion du {meeting.started_at.astimezone():%d/%m/%Y %H:%M}"


def format_ts(ms: int) -> str:
    s = max(0, ms // 1000)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def export_markdown(meeting: Meeting, segments: list[TranscriptSegment], tasks: list[Task]) -> str:
    started = meeting.started_at.astimezone()
    facts = [f"Date : {started:%d/%m/%Y %H:%M}"]
    if meeting.duration_ms:
        facts.append(f"Durée : {max(1, round(meeting.duration_ms / 60000))} min")
    if meeting.language:
        facts.append(f"Langue : {meeting.language}")
    if meeting.app:
        facts.append(f"Application : {meeting.app}")
    lines = [f"# {display_title(meeting)}", "", " · ".join(facts), ""]
    if tasks:
        lines += ["## Tâches", ""]
        for t in tasks:
            extra = ", ".join(x for x in (t.assignee, f"échéance {t.due}" if t.due else "") if x)
            lines.append(
                f"- [{'x' if t.column == 'done' else ' '}] {t.title}"
                + (f" ({extra})" if extra else "")
            )
        lines.append("")
    lines += ["## Transcription", ""]
    if not segments:
        lines.append("_Pas de transcription disponible._")
    for seg in segments:
        lines.append(f"**[{format_ts(seg.start_ms)}] {SPEAKER_LABEL[seg.speaker]}** : {seg.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
