"""Token-count estimation for messages and prompts."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Union

# Rough chars-per-token ratio for Claude models (conservative estimate).
_CHARS_PER_TOKEN: float = 3.5


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text* using a character ratio."""
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def count_content_tokens(content: Union[str, List[Any]]) -> int:
    """Count estimated tokens in a message *content* field.

    Handles both plain strings and structured content blocks.
    """
    if isinstance(content, str):
        return estimate_tokens(content)
    total = 0
    for block in content:
        if isinstance(block, dict):
            btype = block.get("type", "")
            if btype == "text":
                total += estimate_tokens(block.get("text", ""))
            elif btype == "tool_use":
                total += estimate_tokens(json.dumps(block.get("input", {})))
            elif btype == "tool_result":
                c = block.get("content", "")
                total += estimate_tokens(c if isinstance(c, str) else json.dumps(c))
            else:
                total += estimate_tokens(json.dumps(block))
        else:
            total += estimate_tokens(str(block))
    return total


def count_message_tokens(messages: List[Dict[str, Any]]) -> int:
    """Return total estimated token count across a list of chat messages.

    Each message contributes ~4 overhead tokens (role + delimiters) plus
    its content tokens.
    """
    total = 0
    for msg in messages:
        total += 4  # overhead per message
        total += count_content_tokens(msg.get("content", ""))
    total += 2  # reply priming overhead
    return total
