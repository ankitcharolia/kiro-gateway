"""Sliding-window message truncation with token-budget tracking."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .tokenizer import count_tokens, count_messages_tokens

logger = logging.getLogger(__name__)

# Default context window budgets (input tokens)
DEFAULT_CONTEXT_WINDOW = 180_000
# Reserve this many tokens for the model's output
OUTPUT_RESERVE = 8_192
# Minimum messages to keep regardless of token budget (system + latest user)
MIN_MESSAGES_TO_KEEP = 2


@dataclass
class TruncationState:
    """Tracks how many messages have been truncated and the current token budget."""
    original_count: int = 0
    current_count: int = 0
    truncated_count: int = 0
    input_tokens_estimated: int = 0
    was_truncated: bool = False
    truncation_rounds: int = 0


def _message_to_text(msg: Any) -> str:
    """Extract plain text from an ACP or dict message for token counting."""
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(getattr(block, "text", "") or "")
        return " ".join(parts)
    return str(content or "")


def estimate_conversation_tokens(
    messages: List[Any],
    system: Optional[str] = None,
    model: Optional[str] = None,
) -> int:
    """Estimate total token usage for a conversation."""
    total = 0
    if system:
        total += count_tokens(system, model)
    for msg in messages:
        total += count_tokens(_message_to_text(msg), model) + 4
    return total


def truncate_messages(
    messages: List[Any],
    system: Optional[str] = None,
    model: Optional[str] = None,
    context_window: int = DEFAULT_CONTEXT_WINDOW,
    output_reserve: int = OUTPUT_RESERVE,
) -> tuple[List[Any], TruncationState]:
    """
    Truncate messages to fit within the available context window.

    Strategy:
      1. Always keep the system prompt (passed separately).
      2. Always keep the last message (latest user turn).
      3. Remove oldest non-system messages first until the budget is met.

    Returns the (possibly-shortened) message list and a TruncationState.
    """
    budget = context_window - output_reserve
    state = TruncationState(original_count=len(messages), current_count=len(messages))

    system_tokens = count_tokens(system or "", model)
    budget -= system_tokens

    if len(messages) <= MIN_MESSAGES_TO_KEEP:
        state.input_tokens_estimated = estimate_conversation_tokens(messages, system, model)
        return messages, state

    working = list(messages)
    rounds = 0

    while len(working) > MIN_MESSAGES_TO_KEEP:
        estimated = sum(count_tokens(_message_to_text(m), model) + 4 for m in working)
        if estimated <= budget:
            break
        # Drop oldest message (index 0 is earliest non-system turn)
        working.pop(0)
        rounds += 1

    state.current_count = len(working)
    state.truncated_count = len(messages) - len(working)
    state.was_truncated = state.truncated_count > 0
    state.truncation_rounds = rounds
    state.input_tokens_estimated = sum(count_tokens(_message_to_text(m), model) + 4 for m in working)

    if state.was_truncated:
        logger.info(
            "Truncated %d messages (%d -> %d) to fit context window of %d tokens",
            state.truncated_count, state.original_count, state.current_count, context_window,
        )

    return working, state
