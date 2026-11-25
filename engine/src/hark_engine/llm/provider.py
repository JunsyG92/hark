"""LLM provider abstraction. Local (Ollama) by default; cloud only by explicit configuration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class LLMUnavailableError(LLMError):
    """The server cannot be reached (Ollama not running, network down, cloud disabled…)."""


class LLMModelMissingError(LLMError):
    """The server is up but the requested model is not installed."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    tokens_in: int
    tokens_out: int


class LLMProvider(Protocol):
    name: str
    model: str

    def available(self) -> tuple[bool, str | None]:
        """(usable now?, reason if not). Must be cheap (a few seconds at most)."""
        ...

    def chat(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int = 1024,
        num_ctx: int = 4096,
    ) -> LLMResult: ...


class ScriptedProvider:
    """Deterministic provider for tests and dev (HARK_FAKE_LLM=1). Never touches a network."""

    name = "fake"

    def __init__(
        self,
        responder: Callable[[str, str, dict[str, Any] | None], str] | None = None,
        model: str = "fake-model",
    ) -> None:
        self.model = model
        self.responder = responder or default_responder
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.ok = True

    def available(self) -> tuple[bool, str | None]:
        return (True, None) if self.ok else (False, "fake provider is down")

    def chat(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int = 1024,
        num_ctx: int = 4096,
    ) -> LLMResult:
        self.calls.append((system, user, json_schema))
        text = self.responder(system, user, json_schema)
        return LLMResult(text, tokens_in=len(user) // 4 + 50, tokens_out=len(text) // 4 + 1)


def default_responder(system: str, user: str, schema: dict[str, Any] | None) -> str:
    """Plausible output built from the prompt (used by the e2e / dev mode)."""
    if schema is None:  # map step: chunk notes
        return "- Point budget Q1 [00:00]\n- Je m'occupe du budget Q1 [00:04]"
    import json

    return json.dumps(
        {
            "title": "Revue budget Q1",
            "summary": "Point sur le budget Q1.\nLe budget est validé avec une réserve.",
            "decisions": ["Le budget Q1 est validé."],
            "tasks": [
                {
                    "title": "Envoyer le budget Q1 à la direction",
                    "assignee": "",
                    "due": None,
                    "confidence": 0.9,
                    "evidence_timestamp": "00:04",
                },
                {
                    "title": "Relire le contrat fournisseur",
                    "assignee": "Paul",
                    "due": "2026-12-05",
                    "confidence": 0.7,
                    "evidence_timestamp": "00:00",
                },
            ],
            "open_questions": ["Qui valide l'enveloppe finale ?"],
        },
        ensure_ascii=False,
    )
