"""Model ID resolution — maps external model names to Kiro-internal IDs."""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Canonical model list
# ---------------------------------------------------------------------------

KIRO_MODELS = [
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "claude-haiku-3-5",
    "claude-3-7-sonnet",
    "claude-3-5-sonnet-v2",
    "claude-3-5-haiku",
]

DEFAULT_MODEL = "claude-sonnet-4-5"

# Aliases from OpenAI / generic names used by harnesses.
_ALIAS_MAP: dict[str, str] = {
    # OpenAI compat aliases
    "gpt-4": "claude-sonnet-4-5",
    "gpt-4o": "claude-sonnet-4-5",
    "gpt-4-turbo": "claude-sonnet-4-5",
    "gpt-3.5-turbo": "claude-haiku-3-5",
    # Anthropic short names
    "claude-3-sonnet": "claude-3-7-sonnet",
    "claude-3-haiku": "claude-haiku-3-5",
    "claude-3-opus": "claude-opus-4-5",
    "claude-sonnet": "claude-sonnet-4-5",
    "claude-opus": "claude-opus-4-5",
    "claude-haiku": "claude-haiku-3-5",
    # Generic
    "default": DEFAULT_MODEL,
}


def resolve_model(model_id: Optional[str]) -> str:
    """Return the canonical Kiro model ID for *model_id*.

    Falls back to DEFAULT_MODEL if the name is unknown.
    """
    if not model_id:
        return DEFAULT_MODEL

    # Direct match
    if model_id in KIRO_MODELS:
        return model_id

    # Alias lookup (case-insensitive)
    lower = model_id.lower()
    if lower in _ALIAS_MAP:
        return _ALIAS_MAP[lower]

    # Partial / fuzzy: return first model that contains the query as substring
    for m in KIRO_MODELS:
        if lower in m or m in lower:
            return m

    return DEFAULT_MODEL


# Backward-compat alias
normalize_model_name = resolve_model
