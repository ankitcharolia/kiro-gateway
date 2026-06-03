"""Resolve model aliases to canonical Kiro model IDs."""
from __future__ import annotations
from kiro.config import DEFAULT_MODEL, HIDDEN_MODELS

_ALIASES: dict[str, str] = {
    "gpt-4": "claude-sonnet-4-5",
    "gpt-4o": "claude-sonnet-4-5",
    "gpt-4-turbo": "claude-opus-4-5",
    "gpt-3.5-turbo": "claude-haiku-4-5",
    "claude-3-opus": "claude-opus-4-5",
    "claude-3-sonnet": "claude-sonnet-4-5",
    "claude-3-haiku": "claude-haiku-4-5",
}


class ModelResolver:
    def __init__(self) -> None:
        self._available: list[str] = list(HIDDEN_MODELS)

    def resolve(self, model_id: str) -> str:
        if model_id in self._available:
            return model_id
        return _ALIASES.get(model_id, DEFAULT_MODEL)

    def get_available_models(self) -> list[str]:
        return list(self._available)

    def set_available_models(self, models: list[str]) -> None:
        self._available = list(models)
