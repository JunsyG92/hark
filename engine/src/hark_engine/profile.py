"""profile.yaml: who the user is, to flag the tasks that concern them. Safe YAML only."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import ProfileDocument, UserProfile

TEMPLATE = """\
# Ton profil : aide Hark à repérer les tâches qui te concernent.
name: ""          # ex. "Mathieu Nesseir" (prénom et nom)
email: ""
nicknames: []     # ex. ["Mat", "Mathieu"] : comment on t'appelle en réunion
role: ""          # ex. "Responsable produit"
team: ""
projects: []      # ex. ["Refonte site", "Budget Q1"]
keywords: []      # mots qui signalent ton domaine
"""


class ProfileError(ValueError):
    pass


def parse_profile(text: str) -> UserProfile:
    try:
        data = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as exc:
        raise ProfileError(f"YAML invalide : {str(exc).splitlines()[0]}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ProfileError("le profil doit être un objet YAML (clé: valeur)")
    try:
        return UserProfile.model_validate(data)
    except ValidationError as exc:
        err = exc.errors()[0]
        where = ".".join(str(p) for p in err["loc"]) or "profil"
        raise ProfileError(f"{where} : {err['msg']}") from exc


def profile_hash(profile: UserProfile) -> str:
    return hashlib.sha256(profile.model_dump_json().encode()).hexdigest()[:16]


class ProfileStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def text(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return TEMPLATE

    def load(self) -> UserProfile:
        try:
            return parse_profile(self.text())
        except ProfileError:
            return (
                UserProfile()
            )  # a broken file never breaks the app: analysis runs without profile

    def document(self) -> ProfileDocument:
        text = self.text()
        try:
            return ProfileDocument(yaml=text, profile=parse_profile(text))
        except ProfileError as exc:
            return ProfileDocument(yaml=text, error=str(exc))

    def save(self, text: str) -> UserProfile:
        profile = parse_profile(text)  # raises ProfileError before anything is written
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")
        return profile
