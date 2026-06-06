"""Model ID resolution and capability helpers."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Internal mapping: kiro model alias -> real model ID
# ---------------------------------------------------------------------------

_MODEL_MAP: Dict[str, str] = {
    "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku": "claude-3-5-haiku-20241022",
    "claude-3-opus": "claude-3-opus-20240229",
    "claude-3-sonnet": "claude-3-sonnet-20240229",
    "claude-3-haiku": "claude-3-haiku-20240307",
    "claude-sonnet-4": "claude-sonnet-4-5",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt-4": "gpt-4",
    "gpt-3.5-turbo": "gpt-3.5-turbo",
}

_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "claude": {
        "vision": True,
        "tools": True,
        "streaming": True,
        "thinking": True,
        "max_output_tokens": 8192,
    },
    "gpt": {
        "vision": True,
        "tools": True,
        "streaming": True,
        "thinking": False,
        "max_output_tokens": 4096,
    },
    "default": {
        "vision": False,
        "tools": False,
        "streaming": True,
        "thinking": False,
        "max_output_tokens": 4096,
    },
}


def resolve_model(model_id: str) -> str:
    """Return the canonical model ID for *model_id*, passing through unknowns."""
    return _MODEL_MAP.get(model_id, model_id)


def extract_model_family(model_id: str) -> str:
    """Return a short family name for *model_id* (e.g. 'claude', 'gpt')."""
    lower = model_id.lower()
    if "claude" in lower:
        return "claude"
    if "gpt" in lower:
        return "gpt"
    if "gemini" in lower:
        return "gemini"
    if "llama" in lower:
        return "llama"
    return "unknown"


def get_capabilities(model_id: str) -> Dict[str, Any]:
    """Return a capabilities dict for *model_id*."""
    family = extract_model_family(model_id)
    return dict(_CAPABILITIES.get(family, _CAPABILITIES["default"]))


def get_model_id_for_kiro(model_id: str) -> str:
    """Alias for :func:`resolve_model` — maps public IDs to Kiro-internal IDs."""
    return resolve_model(model_id)


def list_models() -> List[str]:
    """Return the list of supported model aliases."""
    return sorted(_MODEL_MAP.keys())


def is_claude_model(model_id: str) -> bool:
    """Return True if *model_id* is a Claude model."""
    return extract_model_family(model_id) == "claude"


def is_openai_model(model_id: str) -> bool:
    """Return True if *model_id* is an OpenAI model."""
    return extract_model_family(model_id) == "gpt"
