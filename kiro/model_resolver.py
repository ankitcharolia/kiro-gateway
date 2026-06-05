"""Model alias resolution and capability flags."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ModelCapabilities:
    """Feature flags for a resolved model."""
    supports_thinking: bool = False
    supports_vision: bool = False
    supports_tools: bool = True
    context_window: int = 200_000
    max_output_tokens: int = 64_000


# ---------------------------------------------------------------------------
# Alias table  (client-supplied name -> canonical Kiro model id)
# ---------------------------------------------------------------------------

_ALIASES: Dict[str, str] = {
    # Anthropic surface aliases
    "claude-sonnet-4-5":              "claude-sonnet-4-5",
    "claude-sonnet-4":                "claude-sonnet-4-5",
    "claude-3-7-sonnet-20250219":     "claude-sonnet-4-5",
    "claude-3-5-sonnet-20241022":     "claude-sonnet-4-5",
    "claude-3-5-sonnet-20240620":     "claude-sonnet-4-5",
    "claude-opus-4":                  "claude-opus-4",
    "claude-3-opus-20240229":         "claude-opus-4",
    "claude-haiku-3-5":               "claude-haiku-3-5",
    "claude-3-5-haiku-20241022":      "claude-haiku-3-5",
    "claude-3-haiku-20240307":        "claude-haiku-3-5",
    # OpenAI surface aliases (map to best available Kiro model)
    "gpt-4o":                         "claude-sonnet-4-5",
    "gpt-4o-mini":                    "claude-haiku-3-5",
    "gpt-4-turbo":                    "claude-sonnet-4-5",
    "gpt-4":                          "claude-sonnet-4-5",
    "o1":                             "claude-opus-4",
    "o1-mini":                        "claude-sonnet-4-5",
    "o3-mini":                        "claude-sonnet-4-5",
}

_CAPABILITIES: Dict[str, ModelCapabilities] = {
    "claude-sonnet-4-5": ModelCapabilities(
        supports_thinking=True,
        supports_vision=True,
        supports_tools=True,
        context_window=200_000,
        max_output_tokens=64_000,
    ),
    "claude-opus-4": ModelCapabilities(
        supports_thinking=True,
        supports_vision=True,
        supports_tools=True,
        context_window=200_000,
        max_output_tokens=32_000,
    ),
    "claude-haiku-3-5": ModelCapabilities(
        supports_thinking=False,
        supports_vision=True,
        supports_tools=True,
        context_window=200_000,
        max_output_tokens=8_192,
    ),
}

_DEFAULT_CAPABILITIES = ModelCapabilities()


def resolve_model(requested: str, default: str = "claude-sonnet-4-5") -> str:
    """Return the canonical Kiro model ID for a client-supplied name."""
    name = (requested or default).strip()
    return _ALIASES.get(name, name)


def get_capabilities(model_id: str) -> ModelCapabilities:
    """Return capability flags for a canonical model ID."""
    return _CAPABILITIES.get(model_id, _DEFAULT_CAPABILITIES)


def list_models() -> List[Dict[str, object]]:
    """Return an OpenAI-compatible model list payload."""
    seen: Dict[str, bool] = {}
    entries = []
    for alias, canonical in _ALIASES.items():
        if canonical in seen:
            continue
        seen[canonical] = True
        cap = get_capabilities(canonical)
        entries.append({
            "id": alias,
            "object": "model",
            "created": 1_700_000_000,
            "owned_by": "kiro",
            "capabilities": {
                "thinking": cap.supports_thinking,
                "vision": cap.supports_vision,
                "tools": cap.supports_tools,
            },
        })
    return entries
