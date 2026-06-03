"""Rough token counting (no tiktoken dependency)."""
from __future__ import annotations

_CHARS_PER_TOKEN = 4


def count_tokens(text: str) -> int:
    """Estimate token count — approximately 4 chars per token."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def count_message_tokens(messages: list[dict]) -> int:
    """Sum token estimates across all messages."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, str):
            total += count_tokens(content)
        elif isinstance(content, list):
            for block in content:
                total += count_tokens(str(block.get("text") or ""))
    return total
