"""Heuristics for detecting and recovering from context-window truncation."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Stop reasons that indicate the model ran out of context rather than
# finishing naturally.
_TRUNCATION_STOP_REASONS = {"max_tokens", "length"}


def is_truncated_response(response: Dict[str, Any]) -> bool:
    """Return True if *response* looks like it was cut short by the context limit."""
    stop_reason = response.get("stop_reason") or response.get("finish_reason", "")
    return stop_reason in _TRUNCATION_STOP_REASONS


def should_inject_recovery(
    messages: List[Dict[str, Any]],
    max_input_tokens: int,
    current_token_estimate: int,
) -> bool:
    """Return True if a recovery / summarisation injection is warranted.

    A recovery is triggered when the estimated token count exceeds
    90 % of *max_input_tokens* and there are enough messages to truncate.
    """
    if len(messages) < 4:  # too short to be worth compressing
        return False
    threshold = int(max_input_tokens * 0.90)
    return current_token_estimate >= threshold


def build_recovery_message(summary: str) -> Dict[str, Any]:
    """Build a synthetic user message that injects a conversation summary."""
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
    """Return at most *max_messages* messages, keeping the system prompt and
    the most recent turns.
    """
    if len(messages) <= max_messages:
        return messages

    # Preserve leading system message if present.
    if messages and messages[0].get("role") == "system":
        return [messages[0]] + messages[-(max_messages - 1) :]
    return messages[-max_messages:]
