"""Model info cache."""
from __future__ import annotations
import time
from typing import Any, Optional

from kiro.config import DEFAULT_MAX_INPUT_TOKENS


class ModelInfoCache:
    """In-memory cache for Kiro model metadata."""

    def __init__(self, cache_ttl: float = 300.0) -> None:
        self._cache_ttl = cache_ttl
        self._store: dict[str, dict[str, Any]] = {}
        self._last_update: Optional[float] = None

    @property
    def last_update_time(self) -> Optional[float]:
        return self._last_update

    @property
    def size(self) -> int:
        return len(self._store)

    def is_empty(self) -> bool:
        return len(self._store) == 0

    async def update(self, models: list[dict[str, Any]]) -> None:
        self._store = {m["modelId"]: m for m in models if "modelId" in m}
        self._last_update = time.time()

    def get(self, model_id: str) -> Optional[dict[str, Any]]:
        return self._store.get(model_id)

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._store.values())

    def get_max_input_tokens(self, model_id: str) -> int:
        entry = self._store.get(model_id)
        if entry is None:
            return DEFAULT_MAX_INPUT_TOKENS
        limits = entry.get("tokenLimits") or {}
        val = limits.get("maxInputTokens")
        if val is None:
            return DEFAULT_MAX_INPUT_TOKENS
        return int(val)

    def is_stale(self) -> bool:
        if self._last_update is None:
            return True
        return (time.time() - self._last_update) > self._cache_ttl

    def clear(self) -> None:
        self._store.clear()
        self._last_update = None
