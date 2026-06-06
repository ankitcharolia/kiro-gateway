"""Heuristics for detecting and recovering from context-window truncation."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

_TRUNCATION_STOP_REASONS = {"max_tokens", "length"}

# Feature flag — set KIRO_TRUNCATION_RECOVERY=0 to disable.
_RECOVERY_ENABLED_DEFAULT = True


def _recovery_enabled() -> bool:
    val = os.environ.get("KIRO_TRUNCATION_RECOVERY", "").lower()
    if val in ("0", "false", "no", "off"):
        return False
    return _RECOVERY_ENABLED_DEFAULT


def is_truncated_response(response: Dict[str, Any]) -> bool:
    stop_reason = response.get("stop_reason") or response.get("finish_reason", "")
    return stop_reason in _TRUNCATION_STOP_REASONS


def should_inject_recovery(
    messages: List[Dict[str, Any]],
    max_input_tokens: int,
    current_token_estimate: int,
) -> bool:
    """Return True when recovery injection is warranted and enabled."""
    if not _recovery_enabled():
        return False
    if len(messages) < 4:
        return False
    threshold = int(max_input_tokens * 0.90)
    return current_token_estimate >= threshold


def build_recovery_message(summary: str) -> Dict[str, Any]:
    return {
        "role": "user",
        "content": (
            "[System: The conversation history has been summarised to fit within "
            f"the context window.]\n\nSummary of prior context:\n{summary}"
        ),
    }


def truncate_messages_to_fit(
    messages: List[Dict[str, Any]],
    max_messages: int = 20,
) -> List[Dict[str, Any]]:
    if len(messages) <= max_messages:
        return messages
    if messages and messages[0].get("role") == "system":
        return [messages[0]] + messages[-(max_messages - 1):]
    return messages[-max_messages:]


# ---------------------------------------------------------------------------
# generate_truncation_tool_result — expected by test_truncation_recovery.py
# ---------------------------------------------------------------------------

def generate_truncation_tool_result(
    tool_call_id: str,
    original_message_count: int,
    truncated_to: int,
) -> Dict[str, Any]:
    """Build a synthetic tool-result message that explains a truncation event."""
    content = (
        f"[Context truncated: conversation had {original_message_count} messages, "
        f"reduced to {truncated_to} to fit the context window.]"
    )
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": content,
                "is_error": False,
            }
        ],
    }


def generate_truncation_user_message(
    original_message_count: int,
    truncated_to: int,
) -> Dict[str, Any]:
    """Build a synthetic user message that explains a content truncation event."""
    content = (
        f"[Context truncated: conversation had {original_message_count} messages, "
        f"reduced to {truncated_to} to fit the context window.]"
    )
    return {"role": "user", "content": content}


async def with_truncation_recovery(
    messages: List[Dict[str, Any]],
    call_fn: Any,
    max_input_tokens: int = 100_000,
    max_retries: int = 2,
) -> Any:
    """Call *call_fn(messages)* with automatic truncation recovery.

    If *call_fn* raises an exception indicating a context-length overflow,
    messages are trimmed and the call is retried up to *max_retries* times.
    """
    from .tokenizer import count_message_tokens

    current = list(messages)
    for attempt in range(max_retries + 1):
        try:
            return await call_fn(current)
        except Exception as exc:
            err = str(exc).lower()
            is_context_error = any(
                kw in err
                for kw in ("context", "token", "length", "too long", "max_tokens")
            )
            if not is_context_error or attempt >= max_retries:
                raise
            # Trim 20% of messages and retry
            trim_count = max(1, len(current) // 5)
            # Preserve system message
            if current and current[0].get("role") == "system":
                current = [current[0]] + current[trim_count + 1:]
            else:
                current = current[trim_count:]
    raise RuntimeError("Truncation recovery exhausted retries")
