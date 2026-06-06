"""Token-counting utilities for context-window management."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

CLAUDE_CORRECTION_FACTOR: float = 1.15
_CHARS_PER_TOKEN: float = 4.0


def _get_encoding() -> Optional[Any]:
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
    return max(1, len(text) // int(_CHARS_PER_TOKEN) + (1 if len(text) % int(_CHARS_PER_TOKEN) else 0))


def count_tokens(
    text: Optional[str],
    apply_claude_correction: bool = True,
) -> int:
    """Estimate the number of tokens in *text*."""
    if not text:
        return 0
    raw = _raw_tokens(text)
    return int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw


def _count_block_tokens(block: Any, enc: Optional[Any], apply_claude_correction: bool) -> int:
    if isinstance(block, str):
        raw = _raw_tokens(block, enc)
        return int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw
    if isinstance(block, dict):
        btype = block.get("type", "")
        if btype == "text":
            raw = _raw_tokens(block.get("text", ""), enc)
        elif btype == "image":
            raw = 800
        elif btype == "tool_use":
            raw = _raw_tokens(json.dumps(block.get("input", {})), enc) + 10
        elif btype == "tool_result":
            content = block.get("content", "")
            if isinstance(content, str):
                raw = _raw_tokens(content, enc)
            elif isinstance(content, list):
                raw = sum(_count_block_tokens(b, enc, False) for b in content)
            else:
                raw = _raw_tokens(str(content), enc)
        elif btype == "thinking":
            raw = _raw_tokens(block.get("thinking", ""), enc)
        else:
            raw = _raw_tokens(json.dumps(block), enc)
        return int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw
    return 0


def count_message_tokens(
    messages: Optional[List[Dict[str, Any]]],
    apply_claude_correction: bool = True,
) -> int:
    """Estimate total tokens for a list of chat messages."""
    if not messages:
        return 0
    enc = _get_encoding()
    total = 0
    for msg in messages:
        content = msg.get("content")
        tool_calls = msg.get("tool_calls")
        tool_call_id = msg.get("tool_call_id")

        if tool_call_id:
            raw = _raw_tokens(str(tool_call_id), enc)
            total += int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw

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
    return total


def count_tools_tokens(
    tools: Optional[List[Dict[str, Any]]],
    apply_claude_correction: bool = True,
) -> int:
    """Estimate tokens consumed by tool definitions injected into the prompt."""
    if not tools:
        return 0
    enc = _get_encoding()
    total = 0
    for tool in tools:
        if tool.get("type") == "function" and "function" in tool:
            fn = tool["function"]
            name = fn.get("name", "")
            description = fn.get("description", "")
            parameters = fn.get("parameters", {})
        else:
            name = tool.get("name", "")
            description = tool.get("description", "")
            parameters = tool.get("parameters", tool.get("input_schema", {}))
        text = name + " " + description + " " + json.dumps(parameters)
        raw = _raw_tokens(text, enc)
        total += int(raw * CLAUDE_CORRECTION_FACTOR) if apply_claude_correction else raw
    return total


def count_system_tokens(
    system: Optional[Union[str, List[Dict[str, Any]]]],
    apply_claude_correction: bool = True,
) -> int:
    """Estimate tokens for a system prompt (string or list of Anthropic blocks)."""
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
    apply_claude_correction: bool = True,
) -> int:
    """Combined token estimate: messages + optional tools + optional system."""
    return (
        count_message_tokens(messages, apply_claude_correction)
        + count_tools_tokens(tools, apply_claude_correction)
        + count_system_tokens(system, apply_claude_correction)
    )


def estimate_tokens(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Backward-compatible alias for estimate_request_tokens."""
    return estimate_request_tokens(messages, tools)
