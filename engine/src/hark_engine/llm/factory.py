"""Build the active provider from settings (cloud only if explicitly selected AND enabled)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..auth import load_secret
from ..store import SettingsRepository
from .cloud import CloudProvider
from .ollama import OllamaProvider
from .provider import LLMProvider

CLOUD_KEY_NAME = "cloud-api-key"


def make_provider_factory(
    settings: SettingsRepository, data_dir: Path
) -> Callable[[], LLMProvider]:
    def factory() -> LLMProvider:
        cfg = settings.get_llm()
        if cfg.provider == "cloud":
            return CloudProvider(
                settings.get_cloud(), lambda: load_secret(data_dir, CLOUD_KEY_NAME)
            )
        return OllamaProvider(cfg.ollama_url, cfg.model)

    return factory
