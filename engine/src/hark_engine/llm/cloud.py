"""Optional cloud provider (OpenAI-compatible chat API). DISABLED by default.

Using it sends transcript text outside this machine, so it only works when the user explicitly
enabled it AND acknowledged that, and an API key was stored. Network access is opened only
around the call itself (`allow_network`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx

from ..models import CloudSettings
from ..net import allow_network
from .provider import LLMResult, LLMUnavailableError

log = logging.getLogger(__name__)


class CloudProvider:
    name = "cloud"

    def __init__(
        self,
        settings: CloudSettings,
        get_key: Callable[[], str | None],
        timeout_s: float = 300.0,
    ) -> None:
        self._settings = settings
        self._get_key = get_key
        self._timeout = timeout_s
        self.model = settings.model

    def _check(self) -> str:
        s = self._settings
        if not (s.enabled and s.acknowledged):
            raise LLMUnavailableError("fournisseur cloud désactivé")
        if not s.base_url.startswith("https://") and not s.base_url.startswith("http://127.0.0.1"):
            raise LLMUnavailableError("l'URL du fournisseur cloud doit commencer par https://")
        key = self._get_key()
        if not key or not s.model:
            raise LLMUnavailableError("clé d'API ou modèle cloud manquant")
        return key

    def available(self) -> tuple[bool, str | None]:
        try:
            self._check()
        except LLMUnavailableError as exc:
            return False, str(exc)
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
        key = self._check()
        body: dict[str, Any] = {
            "model": self._settings.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_schema is not None:
            body["response_format"] = {"type": "json_object"}
        log.warning("cloud LLM call: transcript text leaves this machine (user opted in)")
        try:
            with allow_network():
                resp = httpx.post(
                    f"{self._settings.base_url.rstrip('/')}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=self._timeout,
                )
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(
                f"fournisseur cloud injoignable : {type(exc).__name__}"
            ) from exc
        if resp.status_code >= 400:
            raise LLMUnavailableError(f"fournisseur cloud : HTTP {resp.status_code}")
        data = resp.json()
        usage = data.get("usage", {})
        return LLMResult(
            text=str(data["choices"][0]["message"]["content"]),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )
