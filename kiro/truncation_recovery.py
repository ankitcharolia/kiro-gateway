"""Heuristics for detecting and recovering from context-window truncation."""
from __future__ import annotations

import functools
from typing import Any, Callable, Dict, List, Optional, TypeVar

_TRUNCATION_STOP_REASONS = {"max_tokens", "length"}

F = TypeVar("F", bound=Callable[..., Any])


def is_truncated_response(response: Dict[str, Any]) -> bool:
    stop_reason = response.get("stop_reason") or response.get("finish_reason", "")
    return stop_reason in _TRUNCATION_STOP_REASONS


def should_inject_recovery(
    messages: List[Dict[str, Any]],
    max_input_tokens: int,
    current_token_estimate: int,
) -> bool:
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
# Backward-compat additions expected by tests
# ---------------------------------------------------------------------------

def generate_truncation_tool_result(
    tool_use_id: str,
    summary: Optional[str] = None,
) -> Dict[str, Any]:
    content = summary or (
        "[Context truncated: previous tool output was removed to fit "
        "within the context window. Please re-request if needed.]"
    )
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
                "is_error": False,
            }
        ],
    }


def generate_truncation_user_message(
    summary: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a synthetic user message that signals context truncation."""
    return build_recovery_message(
        summary
        or "Prior context was truncated to fit within the context window."
    )


def with_truncation_recovery(
    max_input_tokens: int = 100_000,
    max_messages: int = 20,
) -> Callable[[F], F]:
    """Decorator that trims the ``messages`` kwarg before calling the wrapped function.

    Usage::

        @with_truncation_recovery(max_input_tokens=80_000)
        async def handle(messages, ...):
            ...
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if "messages" in kwargs:
                kwargs["messages"] = truncate_messages_to_fit(
                    kwargs["messages"], max_messages
                )
            return await fn(*args, **kwargs)
        return wrapper  # type: ignore[return-value]
    return decorator
