"""Model ID resolution — maps external model names to Kiro-internal IDs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Canonical model list
# ---------------------------------------------------------------------------

KIRO_MODELS: List[str] = [
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "claude-haiku-3-5",
    "claude-3-7-sonnet",
    "claude-3-5-sonnet-v2",
    "claude-3-5-haiku",
]

DEFAULT_MODEL = "claude-sonnet-4-5"

# Aliases from OpenAI / generic names used by harnesses.
_ALIAS_MAP: Dict[str, str] = {
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

# Model capabilities map
_CAPABILITIES: Dict[str, Dict[str, object]] = {
    "claude-sonnet-4-5": {"vision": True, "tools": True, "thinking": True, "max_tokens": 8192, "context": 200000},
    "claude-opus-4-5":   {"vision": True, "tools": True, "thinking": True, "max_tokens": 8192, "context": 200000},
    "claude-haiku-3-5":  {"vision": True, "tools": True, "thinking": False, "max_tokens": 8192, "context": 200000},
    "claude-3-7-sonnet": {"vision": True, "tools": True, "thinking": True, "max_tokens": 8192, "context": 200000},
    "claude-3-5-sonnet-v2": {"vision": True, "tools": True, "thinking": False, "max_tokens": 8192, "context": 200000},
    "claude-3-5-haiku":  {"vision": True, "tools": True, "thinking": False, "max_tokens": 8192, "context": 200000},
}


# ---------------------------------------------------------------------------
# ModelResolution dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelResolution:
    """Result of resolving an incoming model name."""
    requested: str
    resolved: str
    is_alias: bool = False
    is_passthrough: bool = False


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def resolve_model(model_id: Optional[str]) -> str:
    """Return the canonical Kiro model ID for *model_id*.

    Falls back to DEFAULT_MODEL if the name is unknown.
    """
    if not model_id:
        return DEFAULT_MODEL

    if model_id in KIRO_MODELS:
        return model_id

    lower = model_id.lower()
    if lower in _ALIAS_MAP:
        return _ALIAS_MAP[lower]

    for m in KIRO_MODELS:
        if lower in m or m in lower:
            return m

    return DEFAULT_MODEL


# Backward-compat alias
normalize_model_name = resolve_model


def get_model_id_for_kiro(model_id: Optional[str]) -> str:
    """Resolve *model_id* to a Kiro-internal model identifier."""
    return resolve_model(model_id)


def list_models() -> List[str]:
    """Return the list of all supported canonical model IDs."""
    return list(KIRO_MODELS)


def get_capabilities(model_id: Optional[str]) -> Dict[str, object]:
    """Return capability flags for *model_id*.

    Falls back to the DEFAULT_MODEL capabilities if unknown.
    """
    canonical = resolve_model(model_id)
    return dict(_CAPABILITIES.get(canonical, _CAPABILITIES[DEFAULT_MODEL]))


def extract_model_family(model_id: Optional[str]) -> str:
    """Return the high-level family name (e.g. 'sonnet', 'haiku', 'opus')."""
    resolved = resolve_model(model_id)
    for family in ("opus", "sonnet", "haiku"):
        if family in resolved:
            return family
    return "sonnet"


# ---------------------------------------------------------------------------
# ModelResolver class (tests import this by name)
# ---------------------------------------------------------------------------

class ModelResolver:
    """Stateful wrapper around the module-level resolution functions.

    Accepts an optional :class:`~kiro.cache.ModelInfoCache` to honour
    dynamically discovered models returned by the Kiro API.
    """

    def __init__(self, cache=None) -> None:
        self._cache = cache

    def resolve(self, model_id: Optional[str]) -> ModelResolution:
        """Resolve *model_id* and return a :class:`ModelResolution`."""
        resolved = resolve_model(model_id)
        is_alias = bool(model_id) and model_id != resolved and model_id not in KIRO_MODELS
        is_passthrough = resolved == DEFAULT_MODEL and bool(model_id) and model_id not in KIRO_MODELS and (model_id or "").lower() not in _ALIAS_MAP
        return ModelResolution(
            requested=model_id or "",
            resolved=resolved,
            is_alias=is_alias,
            is_passthrough=is_passthrough,
        )

    def get_capabilities(self, model_id: Optional[str]) -> Dict[str, object]:
        return get_capabilities(model_id)

    def list_models(self) -> List[str]:
        return list_models()
