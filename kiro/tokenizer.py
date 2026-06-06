"""Token-count estimation for messages and prompts."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

# Correction factor to better approximate Claude's BPE vocabulary.
CLAUDE_CORRECTION_FACTOR: float = 1.15

# Characters-per-token fallback (used when tiktoken is unavailable).
_CHARS_PER_TOKEN: float = 3.5


def _get_encoding() -> Optional[Any]:
    """Return a tiktoken encoding or None if tiktoken is not installed."""
    try:
        import tiktoken  # type: ignore
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def _raw_tokens(text: str, enc: Optional[Any] = None) -> int:
    if enc is None:
        enc = _get_encoding()
    if enc is not None:
        return max(1, len(enc.encode(text)))
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def count_tokens(
    text: Optional[str],
    apply_claude_correction: bool = True,
) -> int:
    """Estimate the number of tokens in *text*."""
    if not text:
        return 0
    raw = _raw_tokens(text)
    return int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw


def _count_block_tokens(block: Any, enc: Optional[Any], correct: bool) -> int:
    if isinstance(block, str):
        raw = _raw_tokens(block, enc)
        return int(raw * CLAUDE_CORRECTION_FACTOR) if correct else raw
    if isinstance(block, dict):
        btype = block.get("type", "")
        if btype == "text":
            raw = _raw_tokens(block.get("text", ""), enc)
        elif btype == "image":
            raw = 800
        elif btype == "tool_use":
            raw = _raw_tokens(json.dumps(block.get("input", {})), enc) + 10
        elif btype == "tool_result":
            c = block.get("content", "")
            raw = _raw_tokens(c if isinstance(c, str) else json.dumps(c), enc)
        elif btype == "thinking":
            raw = _raw_tokens(block.get("thinking", ""), enc)
        else:
            raw = _raw_tokens(json.dumps(block), enc)
        return int(raw * CLAUDE_CORRECTION_FACTOR) if correct else raw
    return 0


def count_message_tokens(
    messages: Optional[List[Dict[str, Any]]],
    apply_claude_correction: bool = False,
) -> int:
    """Return total estimated token count across a list of chat messages."""
    if not messages:
        return 0
    enc = _get_encoding()
    total = 0
    for msg in messages:
        content = msg.get("content")
        tool_calls = msg.get("tool_calls")
        if isinstance(content, str):
            if content:
                raw = _raw_tokens(content, enc)
                total += int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw
        elif isinstance(content, list):
            for block in content:
                total += _count_block_tokens(block, enc, apply_claude_correction)
        if tool_calls:
            raw = _raw_tokens(json.dumps(tool_calls), enc)
            total += int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw
        total += 4  # per-message overhead
    total += 2  # reply priming
    return total


def count_tools_tokens(
    tools: Optional[List[Dict[str, Any]]],
    apply_claude_correction: bool = False,
) -> int:
    """Estimate tokens consumed by tool definitions."""
    if not tools:
        return 0
    enc = _get_encoding()
    total = 0
    for tool in tools:
        if tool.get("type") == "function" and "function" in tool:
            fn = tool["function"]
            text = fn.get("name", "") + " " + fn.get("description", "") + " " + json.dumps(fn.get("parameters", {}))
        else:
            text = tool.get("name", "") + " " + tool.get("description", "") + " " + json.dumps(tool.get("parameters", tool.get("input_schema", {})))
        raw = _raw_tokens(text, enc)
        total += int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw
    return total


def count_system_tokens(
    system: Optional[Union[str, List[Dict[str, Any]]]],
    apply_claude_correction: bool = False,
) -> int:
    """Estimate tokens for a system prompt."""
    if not system:
        return 0
    enc = _get_encoding()
    if isinstance(system, str):
        raw = _raw_tokens(system, enc)
        return int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw
    if isinstance(system, list):
        total = 0
        for block in system:
            total += _count_block_tokens(block, enc, apply_claude_correction)
        return total
    return 0


def estimate_request_tokens(
    messages: Optional[List[Dict[str, Any]]],
    tools: Optional[List[Dict[str, Any]]] = None,
    system: Optional[Union[str, List[Dict[str, Any]]]] = None,
    apply_claude_correction: bool = False,
) -> int:
    """Combined token estimate: messages + optional tools + optional system."""
    return (
        count_message_tokens(messages, apply_claude_correction)
        + count_tools_tokens(tools, apply_claude_correction)
        + count_system_tokens(system, apply_claude_correction)
    )


# Backward-compat helpers kept from original tokenizer.py
def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def count_content_tokens(content: Union[str, List[Any]]) -> int:
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
