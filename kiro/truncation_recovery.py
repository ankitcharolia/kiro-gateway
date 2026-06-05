"""Retry-on-context-overflow with progressive message truncation."""
from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, List, Optional, TypeVar

from .truncation_state import truncate_messages, TruncationState, MIN_MESSAGES_TO_KEEP

logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP / ACP status codes that indicate a context-length overflow
_OVERFLOW_SIGNALS = {
    "context_length_exceeded",
    "max_tokens_exceeded",
    "prompt_too_long",
    "context_window_exceeded",
}

MAX_RECOVERY_ATTEMPTS = 4


def _is_overflow_error(exc: Exception) -> bool:
    """Heuristic: does this exception look like a context-overflow?"""
    msg = str(exc).lower()
    return any(sig in msg for sig in _OVERFLOW_SIGNALS)


async def with_truncation_recovery(
    messages: List[Any],
    system: Optional[str],
    model: Optional[str],
    invoke: Callable[..., Coroutine[Any, Any, T]],
    context_window: int = 180_000,
    output_reserve: int = 8_192,
) -> tuple[T, TruncationState]:
    """
    Call *invoke(messages, system)* and, if a context-overflow error occurs,
    progressively truncate *messages* and retry up to MAX_RECOVERY_ATTEMPTS times.

    Args:
        messages:       List of ACP/dict messages for this request.
        system:         System prompt string (or None).
        model:          Model name for token-counting heuristics.
        invoke:         Async callable ``(messages, system) -> response``.
        context_window: Max input token budget.
        output_reserve: Tokens reserved for model output.

    Returns:
        Tuple of (response, final_truncation_state).
    """
    working_messages = list(messages)
    cumulative_state = TruncationState(original_count=len(messages), current_count=len(messages))

    for attempt in range(MAX_RECOVERY_ATTEMPTS + 1):
        try:
            result = await invoke(working_messages, system)
            cumulative_state.current_count = len(working_messages)
            cumulative_state.truncated_count = len(messages) - len(working_messages)
            cumulative_state.was_truncated = cumulative_state.truncated_count > 0
            return result, cumulative_state

        except Exception as exc:
            if not _is_overflow_error(exc):
                raise

            if len(working_messages) <= MIN_MESSAGES_TO_KEEP:
                logger.error(
                    "Context overflow even with minimal message history (%d messages). "
                    "Cannot truncate further.",
                    len(working_messages),
                )
                raise

            logger.warning(
                "Context overflow on attempt %d/%d — truncating messages (currently %d).",
                attempt + 1, MAX_RECOVERY_ATTEMPTS, len(working_messages),
            )
            # Reduce context window by 20% per retry to force more aggressive truncation
            adjusted_window = int(context_window * (0.8 ** (attempt + 1)))
            working_messages, state = truncate_messages(
                working_messages,
                system=system,
                model=model,
                context_window=adjusted_window,
                output_reserve=output_reserve,
            )
            cumulative_state.truncation_rounds += state.truncation_rounds

    # Should be unreachable
    raise RuntimeError("Exceeded maximum truncation recovery attempts")
