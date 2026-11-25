"""Prompts. Bump PROMPT_VERSION whenever one changes (it is part of the cache hash)."""

from __future__ import annotations

from ..models import UserProfile

PROMPT_VERSION = "1"

CHUNK_SYSTEM = (
    "Tu résumes un passage de transcription de réunion. Réponds en français, en puces concises "
    "(150 mots maximum). Conserve UNIQUEMENT ce qui est dit : décisions, engagements (qui fait quoi, "
    "pour quand), questions restées ouvertes. Pour chaque puce garde l'horodatage [mm:ss] de la ligne "
    "source. N'invente rien."
)

FINAL_SYSTEM = (
    "Tu analyses une réunion à partir de sa transcription (ou de notes horodatées). "
    "Réponds UNIQUEMENT par un objet JSON avec les clés : "
    '"title" (titre court, 8 mots max), '
    '"summary" (10 lignes maximum, une idée par ligne), '
    '"decisions" (liste de décisions prises), '
    '"tasks" (liste d\'actions concrètes ; chacune : "title", "assignee" (nom tel que prononcé, sinon ""), '
    '"due" (date ISO AAAA-MM-JJ UNIQUEMENT si une échéance est dite, sinon chaîne vide ""), '
    '"confidence" (0 à 1), "evidence_timestamp" (l\'horodatage [mm:ss] de la ligne source)), '
    '"open_questions" (questions sans réponse). '
    "Règles : n'invente rien, ne crée une tâche que pour une action réellement annoncée ou demandée, "
    'écris dans la langue de la réunion, "Moi" désigne l\'utilisateur.'
)

REPAIR = (
    "Ta réponse n'était pas un JSON valide au format demandé. Renvoie UNIQUEMENT l'objet JSON demandé, "
    "sans texte autour."
)


def profile_context(profile: UserProfile) -> str:
    parts = []
    if profile.name:
        parts.append(f"Nom de l'utilisateur (« Moi ») : {profile.name}")
    if profile.nicknames:
        parts.append(f"Surnoms : {', '.join(profile.nicknames)}")
    if profile.role:
        parts.append(f"Rôle : {profile.role}")
    if profile.team:
        parts.append(f"Équipe : {profile.team}")
    if profile.projects:
        parts.append(f"Projets : {', '.join(profile.projects)}")
    if profile.keywords:
        parts.append(f"Mots-clés : {', '.join(profile.keywords)}")
    return "\n".join(parts)


def final_user_prompt(body: str, meeting_date: str, profile: UserProfile, from_notes: bool) -> str:
    head = f"Date de la réunion : {meeting_date} (sert à convertir « vendredi prochain » en date ISO).\n"
    ctx = profile_context(profile)
    if ctx:
        head += f"Contexte :\n{ctx}\n"
    kind = "Notes horodatées de la réunion" if from_notes else "Transcription de la réunion"
    return f"{head}\n{kind} :\n{body}"
