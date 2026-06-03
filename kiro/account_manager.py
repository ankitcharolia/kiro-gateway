"""Single-account manager (compliance mode only)."""
from __future__ import annotations


class AccountManager:
    """Manages a single Kiro account credential set."""

    def __init__(self) -> None:
        self._models: list[str] = []

    def set_available_models(self, models: list[str]) -> None:
        self._models = list(models)

    def get_all_available_models(self) -> list[str]:
        return list(self._models)

    def get_available_models(self) -> list[str]:
        return list(self._models)

    def is_ready(self) -> bool:
        return True
