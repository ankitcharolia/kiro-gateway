"""Shared conversion utilities (message normalisation)."""
from __future__ import annotations
from typing import Any


def normalise_content(content: Any) -> str:
    """Flatten content to a plain string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or "")
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def role_to_anthropic(role: str) -> str:
    mapping = {"user": "user", "assistant": "assistant", "tool": "user", "system": "user"}
    return mapping.get(role, "user")
