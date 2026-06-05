"""MCP tool-call helpers and utility functions."""
from __future__ import annotations

import secrets
import string
from typing import Any, Dict, List, Optional


def generate_random_id(prefix: str = "tool", length: int = 8) -> str:
    """Return a short random alphanumeric ID.

    Example: ``"tool_a3f8b2c1"``
    """
    alphabet = string.ascii_lowercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}_{suffix}"


def build_tool_result(
    tool_use_id: str,
    content: Any,
    is_error: bool = False,
) -> Dict[str, Any]:
    """Build an Anthropic-style tool_result content block."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content if isinstance(content, str) else str(content),
        "is_error": is_error,
    }


def extract_tool_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool_use blocks from an assistant message's content list."""
    content = message.get("content", [])
    if isinstance(content, str):
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == "tool_use"]


def has_tool_calls(message: Dict[str, Any]) -> bool:
    """Return True if the message contains at least one tool_use block."""
    return bool(extract_tool_calls(message))
