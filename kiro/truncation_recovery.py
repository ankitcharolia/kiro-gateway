"""Helpers for injecting truncation-recovery context into requests."""
from __future__ import annotations
import os
from typing import Any


def should_inject_recovery() -> bool:
    """Return True when truncation recovery is enabled (runtime re-read for tests)."""
    val = os.environ.get("TRUNCATION_RECOVERY", "true")
    return val.lower() != "false"


def generate_truncation_tool_result(
    tool_name: str,
    tool_call_id: str,
    truncation_info: dict[str, Any],
) -> dict[str, Any]:
    size = truncation_info.get("size_bytes", 0)
    reason = truncation_info.get("reason", "unknown")
    content = (
        f"[API Limitation] The previous '{tool_name}' call output was truncated "
        f"({size} bytes, reason: {reason}). "
        "The tool completed successfully but the response was too large to pass inline. "
        "If you need the full output, use a targeted follow-up call to retrieve specific sections."
    )
    return {
        "type": "tool_result",
        "tool_use_id": tool_call_id,
        "content": content,
    }


def generate_truncation_user_message() -> str:
    return (
        "[System Notice] Your previous response was truncated because it exceeded "
        "the API output limit. Please continue from where you left off."
    )
