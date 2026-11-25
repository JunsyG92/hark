"""Ollama provider: a local server on 127.0.0.1 (nothing leaves the machine)."""

from __future__ import annotations

from typing import Any

import httpx

from .provider import LLMModelMissingError, LLMResult, LLMUnavailableError


def _name_matches(wanted: str, installed: str) -> bool:
    """`qwen2.5:7b-instruct` matches itself; a bare name matches its `:latest` tag."""
    if wanted == installed:
        return True
    return ":" not in wanted and installed == f"{wanted}:latest"


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_s: float = 900.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout_s

    def installed_models(self, timeout_s: float = 3.0) -> list[str]:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=timeout_s)
            resp.raise_for_status()
            return [str(m.get("name", "")) for m in resp.json().get("models", [])]
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMUnavailableError(
                f"Ollama injoignable sur {self.base_url} (lancé ?) : {type(exc).__name__}"
            ) from exc

    def available(self) -> tuple[bool, str | None]:
        try:
            models = self.installed_models()
        except LLMUnavailableError as exc:
            return False, str(exc)
        if not any(_name_matches(self.model, m) for m in models):
            return False, f"modèle « {self.model} » absent : lance `ollama pull {self.model}`"
        return True, None

    def chat(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int = 1024,
        num_ctx: int = 4096,
    ) -> LLMResult:
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": num_ctx},
        }
        if json_schema is not None:
            body["format"] = json_schema  # structured outputs
        try:
            resp = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama injoignable : {type(exc).__name__}") from exc
        if resp.status_code == 404:
            raise LLMModelMissingError(
                f"modèle « {self.model} » absent : `ollama pull {self.model}`"
            )
        if resp.status_code >= 400:
            raise LLMUnavailableError(f"Ollama a répondu {resp.status_code} : {resp.text[:200]}")
        data = resp.json()
        return LLMResult(
            text=str(data.get("message", {}).get("content", "")),
            tokens_in=int(data.get("prompt_eval_count", 0)),
            tokens_out=int(data.get("eval_count", 0)),
        )

    def pull(self, model: str) -> None:
        """Ask the local Ollama server to download a model (Ollama does the network part)."""
        try:
            resp = httpx.post(
                f"{self.base_url}/api/pull",
                json={"model": model, "stream": False},
                timeout=3 * 3600.0,  # a multi-GB download
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"téléchargement impossible : {type(exc).__name__}") from exc
