"""Provider selection by env (D-04)."""

from __future__ import annotations

from app.providers.base import ModelProvider
from app.providers.deterministic_mock import DeterministicMockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.settings import Settings


def build_provider(settings: Settings) -> ModelProvider:
    kind = settings.model_provider
    if kind == "deterministic_mock":
        return DeterministicMockProvider(model=settings.model_name or "ryde-mock-judge-1")
    if kind == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.model_base_url,
            model=settings.model_name,
            api_key=settings.model_api_key,
            timeout_s=settings.model_timeout_s,
        )
    raise ValueError(f"unknown MODEL_PROVIDER {kind!r}")
