"""Does this task concern the user? (pure heuristics on the profile and the user's own track)."""

from __future__ import annotations

import re
import unicodedata

from ..models import Speaker, TranscriptSegment, UserProfile

SELF_WORDS = {"moi", "me", "je", "moi-meme", "myself", "i", "self"}
# Said by the user on the microphone track: a commitment to do something.
COMMIT_PHRASES = (
    "je m'en occupe", "je m'occupe", "je m'en charge", "je me charge", "je le fais",
    "je la fais", "je vais", "je prends", "je gere", "je regarde", "je te l'envoie",
    "je vous l'envoie", "on me l'assigne",
    "i'll", "i will", "i can take", "i'm on it", "i am on it", "let me", "i'll take",
)  # fmt: skip
# The commitment follows the request ("qui prend ça ?" → "je m'en occupe"), it does not precede it.
WINDOW_BEFORE_MS = 1_000
WINDOW_AFTER_MS = 15_000


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def name_tokens(profile: UserProfile) -> set[str]:
    tokens: set[str] = set()
    for source in [profile.name, *profile.nicknames]:
        for tok in re.split(r"[\s\-]+", normalize(source)):
            if len(tok) >= 2:
                tokens.add(tok)
    return tokens


def is_mine(
    assignee: str,
    evidence_ms: int | None,
    segments: list[TranscriptSegment],
    profile: UserProfile,
) -> bool:
    a = normalize(assignee)
    if a:
        if a in SELF_WORDS:
            return True
        # a name that is not the user's = explicitly assigned to someone else
        return bool(set(re.split(r"[\s,/&\-]+", a)) & name_tokens(profile))
    # No assignee: did the user commit to it, on their own track, around that moment?
    if evidence_ms is None:
        return False
    lo, hi = evidence_ms - WINDOW_BEFORE_MS, evidence_ms + WINDOW_AFTER_MS
    return any(
        seg.speaker is Speaker.ME
        and seg.end_ms >= lo
        and seg.start_ms <= hi
        and any(phrase in normalize(seg.text) for phrase in COMMIT_PHRASES)
        for seg in segments
    )
