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


def _coerce_int(value: Any) -> int:
    """Coerce a reported token count to a non-negative int, else ``0``.

    Args:
        value: A value that may be an int, numeric string, or ``None``.

    Returns:
        The non-negative integer value, or ``0`` when it cannot be parsed.
    """
    try:
        result = int(value)
    except (TypeError, ValueError):
        return 0
    return result if result > 0 else 0


def estimate_completion_tokens(
    text: Optional[str],
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    apply_claude_correction: bool = True,
) -> int:
    """Estimate output tokens for generated assistant text and tool calls.

    Uses the same tokenizer (and Claude correction factor) as the prompt-side
    estimate so input and output counts are consistent.

    Args:
        text: The generated assistant text (may be empty).
        tool_calls: Generated tool calls, each a dict with ``name`` and either
            ``arguments`` (OpenAI) or ``input`` (Anthropic).
        apply_claude_correction: Whether to apply the Claude correction factor.

    Returns:
        The estimated number of completion tokens.
    """
    total = count_tokens(text, apply_claude_correction) if text else 0
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        args = tc.get("arguments")
        if args is None:
            args = tc.get("input", {})
        args_text = args if isinstance(args, str) else json.dumps(args or {})
        total += count_tokens(args_text, apply_claude_correction)
        total += count_tokens(str(tc.get("name", "")), apply_claude_correction)
        total += 10  # per tool-call structural overhead
    return total


def normalize_usage(
    reported: Optional[Dict[str, Any]],
    prompt_messages: Optional[List[Dict[str, Any]]] = None,
    prompt_tools: Optional[List[Dict[str, Any]]] = None,
    prompt_system: Optional[Union[str, List[Dict[str, Any]]]] = None,
    completion_text: Optional[str] = "",
    completion_tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a normalised usage dict, preferring real counts over estimates.

    kiro-cli (ACP) does not currently report token usage on a ``session/prompt``
    result, so most fields fall back to a tokenizer estimate. When a future
    kiro-cli reports counts, those are surfaced verbatim. Each field is resolved
    independently: a reported, positive value wins; otherwise a consistent
    tokenizer estimate is used so a field is never silently ``0``.

    Args:
        reported: Usage counts reported by kiro-cli (may be ``None`` or empty),
            with keys ``input_tokens`` / ``output_tokens`` / ``total_tokens``
            and optionally ``cache_creation_input_tokens`` /
            ``cache_read_input_tokens``.
        prompt_messages: The request messages (token-view dicts) for the
            input-token estimate.
        prompt_tools: Tool definitions injected into the prompt.
        prompt_system: System prompt (string or block list) for the estimate.
        completion_text: The generated assistant text for the output estimate.
        completion_tool_calls: Generated tool calls for the output estimate.

    Returns:
        A dict with ``input_tokens``, ``output_tokens``, ``total_tokens``,
        ``cache_creation_input_tokens`` and ``cache_read_input_tokens`` (ints)
        and ``estimated`` (bool — ``True`` when any field was estimated rather
        than reported).

        Cache-token fields are **never estimated** — prompt caching is not part
        of the ACP path (kiro-cli exposes no caching mechanism), so they are
        ``0`` unless a future kiro-cli reports real cache counts, in which case
        the reported value is surfaced verbatim.
    """
    reported = reported or {}
    input_reported = _coerce_int(reported.get("input_tokens"))
    output_reported = _coerce_int(reported.get("output_tokens"))
    total_reported = _coerce_int(reported.get("total_tokens"))

    estimated = False

    if input_reported:
        input_tokens = input_reported
    else:
        input_tokens = estimate_request_tokens(prompt_messages, prompt_tools, prompt_system)
        estimated = estimated or input_tokens > 0

    if output_reported:
        output_tokens = output_reported
    else:
        output_tokens = estimate_completion_tokens(completion_text, completion_tool_calls)
        estimated = estimated or output_tokens > 0

    total_tokens = total_reported or (input_tokens + output_tokens)

    # Prompt caching is a no-op over ACP (no caching capability is advertised),
    # so these are 0 today. They are surfaced verbatim if a future kiro-cli
    # reports them, and are never estimated (a cache hit/miss cannot be guessed
    # from text). Reporting them keeps the usage object's shape faithful to the
    # native Anthropic/OpenAI APIs instead of omitting cache tokens entirely.
    cache_creation_input_tokens = _coerce_int(reported.get("cache_creation_input_tokens"))
    cache_read_input_tokens = _coerce_int(reported.get("cache_read_input_tokens"))

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "estimated": estimated,
    }
