"""Token-counting utilities for context-window management."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Union

# Characters-per-token approximation (conservative for mixed content).
_CHARS_PER_TOKEN: float = 3.5


def _text_tokens(text: str) -> int:
    """Rough token estimate for a plain string."""
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def count_tokens(text: str) -> int:
    """Estimate the number of tokens in *text*."""
    return _text_tokens(text)


def count_message_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens for a list of chat messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _text_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        total += _text_tokens(block.get("text", ""))
                    elif block.get("type") == "image":
                        total += 800  # flat image cost estimate
                    else:
                        total += _text_tokens(json.dumps(block))
                else:
                    total += _text_tokens(str(block))
        # per-message overhead
        total += 4
    return total


def count_tools_tokens(tools: List[Dict[str, Any]]) -> int:
    """Estimate tokens consumed by tool definitions injected into the prompt."""
    if not tools:
        return 0
    return _text_tokens(json.dumps(tools))


def estimate_tokens(
    messages: List[Dict[str, Any]],
    tools: Union[List[Dict[str, Any]], None] = None,
) -> int:
    """Combined estimate: messages + optional tool definitions."""
    return count_message_tokens(messages) + count_tools_tokens(tools or [])
