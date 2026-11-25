"""Ollama model suggestions by machine power (the user can also type any installed model)."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import LLMProfileId


@dataclass(frozen=True)
class LLMProfile:
    id: LLMProfileId
    label: str
    description: str
    ollama_model: str
    download_gb: float
    min_ram_gb: int


LLM_PROFILES: dict[LLMProfileId, LLMProfile] = {
    LLMProfileId.LIGHT: LLMProfile(
        LLMProfileId.LIGHT,
        "Léger",
        "Petit PC (8 Go de RAM). Résumés corrects, extraction de tâches plus approximative.",
        "qwen2.5:3b-instruct",
        1.9,
        8,
    ),
    LLMProfileId.BALANCED: LLMProfile(
        LLMProfileId.BALANCED,
        "Équilibré",
        "Recommandé : bon français et JSON fiable sur un portable récent (16 Go de RAM).",
        "qwen2.5:7b-instruct",
        4.7,
        16,
    ),
    LLMProfileId.ACCURATE: LLMProfile(
        LLMProfileId.ACCURATE,
        "Précis",
        "Meilleure compréhension des réunions longues. 32 Go de RAM ou carte graphique ≥ 12 Go.",
        "qwen2.5:14b-instruct",
        9.0,
        32,
    ),
}


def recommend_llm(ram_gb: float | None, gpu: bool) -> LLMProfileId:
    if gpu or (ram_gb is not None and ram_gb >= 32):
        return LLMProfileId.ACCURATE if (ram_gb or 0) >= 24 or gpu else LLMProfileId.BALANCED
    if ram_gb is not None and ram_gb < 12:
        return LLMProfileId.LIGHT
    return LLMProfileId.BALANCED
