"""Model ID resolution and capability helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class ModelResolution:
    """Result of resolving a model alias to a canonical model ID."""
    model_id: str
    provider: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    is_claude: bool = False
    is_openai: bool = False


def resolve_model(model_id: str) -> str:
    """Return the canonical model ID for *model_id*, passing through unknowns."""
    return _MODEL_MAP.get(model_id, model_id)


def normalize_model_name(model_id: str) -> str:
    """Normalize *model_id* to its canonical form. Alias for resolve_model."""
    return resolve_model(model_id)


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
    """Alias for resolve_model — maps public IDs to Kiro-internal IDs."""
    return resolve_model(model_id)


def resolve_model_full(model_id: str) -> ModelResolution:
    """Resolve *model_id* and return a full ModelResolution object."""
    canonical = resolve_model(model_id)
    family = extract_model_family(canonical)
    caps = get_capabilities(canonical)
    provider = "anthropic" if family == "claude" else ("openai" if family == "gpt" else "unknown")
    return ModelResolution(
        model_id=canonical,
        provider=provider,
        capabilities=caps,
        is_claude=(family == "claude"),
        is_openai=(family == "gpt"),
    )


def list_models() -> List[str]:
    """Return the list of supported model aliases."""
    return sorted(_MODEL_MAP.keys())


def is_claude_model(model_id: str) -> bool:
    """Return True if *model_id* is a Claude model."""
    return extract_model_family(model_id) == "claude"


def is_openai_model(model_id: str) -> bool:
    """Return True if *model_id* is an OpenAI model."""
    return extract_model_family(model_id) == "gpt"


class ModelInfoCache:
    """Simple in-memory cache of ModelInfo objects keyed by model_id."""

    def __init__(self, models: Optional[List[Dict[str, Any]]] = None) -> None:
        # models is a list of dicts with at least an 'id' key
        self._models: Dict[str, Dict[str, Any]] = {}
        for m in (models or []):
            mid = m.get("id", "")
            if mid:
                self._models[mid] = m

    def get(self, model_id: str) -> Optional[Dict[str, Any]]:
        return self._models.get(model_id)

    def all(self) -> List[Dict[str, Any]]:
        return list(self._models.values())

    def ids(self) -> List[str]:
        return sorted(self._models.keys())


class ModelResolver:
    """Stateful resolver — wraps the module-level helpers for DI / mocking.

    Accepts optional *cache* (a ModelInfoCache) and *hidden_models* (a list of
    model IDs that are valid but not shown in public listings) so that test
    fixtures can inject known state without touching global state.
    """

    def __init__(
        self,
        model_map: Optional[Dict[str, str]] = None,
        cache: Optional[ModelInfoCache] = None,
        hidden_models: Optional[List[str]] = None,
    ) -> None:
        self._map: Dict[str, str] = model_map if model_map is not None else dict(_MODEL_MAP)
        self._cache: ModelInfoCache = cache if cache is not None else ModelInfoCache()
        self._hidden_models: List[str] = list(hidden_models or [])

    # ------------------------------------------------------------------
    # Core resolution
    # ------------------------------------------------------------------

    def resolve(self, model_id: str) -> str:
        """Resolve *model_id* to its canonical form, passing through unknowns."""
        # Check static map first, then cache, then pass through
        if model_id in self._map:
            return self._map[model_id]
        if self._cache.get(model_id):
            return model_id
        # Hidden models are valid pass-throughs
        if model_id in self._hidden_models:
            return model_id
        return model_id

    def get_capabilities(self, model_id: str) -> Dict[str, Any]:
        return get_capabilities(self.resolve(model_id))

    def list_models(self) -> List[str]:
        return sorted(self._map.keys())

    def is_claude(self, model_id: str) -> bool:
        return is_claude_model(self.resolve(model_id))

    def is_openai(self, model_id: str) -> bool:
        return is_openai_model(self.resolve(model_id))

    # ------------------------------------------------------------------
    # Extended helpers used by unit tests
    # ------------------------------------------------------------------

    def get_available_models(self) -> List[str]:
        """Return all public model IDs: static map aliases + cache IDs + hidden models, sorted."""
        ids: set = set(self._map.keys()) | set(self._cache.ids()) | set(self._hidden_models)
        return sorted(ids)

    def get_models_by_family(self, family: str) -> List[str]:
        """Return all available model IDs whose family matches *family* (case-insensitive)."""
        target = family.lower()
        return sorted(
            mid for mid in self.get_available_models()
            if extract_model_family(mid).lower() == target
        )

    def get_suggestions_for_model(self, model_id: str) -> List[str]:
        """Return alternative model IDs in the same family as *model_id*.

        Returns all models in the same family, excluding *model_id* itself.
        If the family is unknown, returns all available models.
        """
        family = extract_model_family(model_id)
        if family == "unknown":
            return [m for m in self.get_available_models() if m != model_id]
        return [m for m in self.get_models_by_family(family) if m != model_id]
