"""Sanitise and guard outgoing payloads before they reach Kiro."""
from __future__ import annotations
from typing import Any


def strip_unknown_params(payload: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    """Remove keys not in *allowed*."""
    return {k: v for k, v in payload.items() if k in allowed}


def clamp_max_tokens(max_tokens: int | None, ceiling: int = 8192) -> int:
    """Ensure max_tokens is within the allowed ceiling."""
    if max_tokens is None:
        return ceiling
    return min(max_tokens, ceiling)


def sanitise_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove None-valued fields from each message dict."""
    return [{k: v for k, v in msg.items() if v is not None} for msg in messages]
