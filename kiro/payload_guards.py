"""Payload validation and trimming guards."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from .tokenizer import count_message_tokens


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class PayloadTrimStats:
    """Statistics about a trim operation."""
    original_message_count: int = 0
    trimmed_message_count: int = 0
    original_token_estimate: int = 0
    trimmed_token_estimate: int = 0
    messages_removed: int = 0

    @property
    def was_trimmed(self) -> bool:
        return self.messages_removed > 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _payload_bytes(payload: Dict[str, Any]) -> int:
    """Rough byte size of a JSON payload."""
    return len(json.dumps(payload, ensure_ascii=False).encode())


# ---------------------------------------------------------------------------
# trim_messages / trim_payload helpers
# ---------------------------------------------------------------------------

def trim_messages(
    messages: List[Dict[str, Any]],
    max_input_tokens: int,
    preserve_system: bool = True,
) -> Tuple[List[Dict[str, Any]], PayloadTrimStats]:
    """Trim *messages* so estimated tokens fit in *max_input_tokens*."""
    stats = PayloadTrimStats(
        original_message_count=len(messages),
        original_token_estimate=count_message_tokens(messages),
    )

    if stats.original_token_estimate <= max_input_tokens:
        stats.trimmed_message_count = len(messages)
        stats.trimmed_token_estimate = stats.original_token_estimate
        return messages, stats

    result: List[Dict[str, Any]] = []
    system_msg: Optional[Dict[str, Any]] = None
    rest = list(messages)

    if preserve_system and rest and rest[0].get("role") == "system":
        system_msg = rest.pop(0)

    while rest and count_message_tokens(
        ([system_msg] if system_msg else []) + rest
    ) > max_input_tokens:
        rest.pop(0)
        stats.messages_removed += 1

    result = ([system_msg] if system_msg else []) + rest
    stats.trimmed_message_count = len(result)
    stats.trimmed_token_estimate = count_message_tokens(result)
    return result, stats


def validate_max_tokens(requested: Optional[int], hard_limit: int = 8192) -> int:
    if requested is None:
        return hard_limit
    return min(requested, hard_limit)


# ---------------------------------------------------------------------------
# check_payload_size / trim_payload_to_limit (tests expect these names)
# ---------------------------------------------------------------------------

MAX_PAYLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MB default


def check_payload_size(
    payload: Dict[str, Any],
    max_bytes: int = MAX_PAYLOAD_BYTES,
) -> bool:
    """Return True if *payload* is within the byte limit, False otherwise."""
    return _payload_bytes(payload) <= max_bytes


def trim_payload_to_limit(
    payload: Dict[str, Any],
    max_bytes: int = MAX_PAYLOAD_BYTES,
) -> Tuple[Dict[str, Any], bool]:
    """Trim history items from a Kiro-shaped payload until it fits *max_bytes*.

    Returns ``(trimmed_payload, was_trimmed)``.
    """
    if _payload_bytes(payload) <= max_bytes:
        return payload, False

    import copy
    p = copy.deepcopy(payload)
    history: List[Dict[str, Any]] = (
        p.get("conversationState", {}).get("history", [])
    )

    while history and _payload_bytes(p) > max_bytes:
        history.pop(0)

    return p, True


# ---------------------------------------------------------------------------
# guard_openai_request / guard_anthropic_request (top-level test shims)
# ---------------------------------------------------------------------------

def guard_openai_request(request: Any) -> None:
    """Validate an OpenAI ChatCompletionRequest.

    Raises :class:`fastapi.HTTPException` (422) when the request is invalid.
    """
    # Mutual exclusion: thinking + tools is unsupported
    has_thinking = bool(getattr(request, "thinking", None))
    has_tools = bool(getattr(request, "tools", None))
    if has_thinking and has_tools:
        raise HTTPException(
            status_code=422,
            detail="thinking and tools cannot be used simultaneously",
        )

    # Validate max_tokens
    max_tokens = getattr(request, "max_tokens", None)
    if max_tokens is not None and max_tokens <= 0:
        raise HTTPException(
            status_code=422,
            detail="max_tokens must be a positive integer",
        )


def guard_anthropic_request(request: Any) -> None:
    """Validate an Anthropic AnthropicRequest.

    Raises :class:`fastapi.HTTPException` (422) when the request is invalid.
    """
    max_tokens = getattr(request, "max_tokens", None)
    if max_tokens is not None and max_tokens <= 0:
        raise HTTPException(
            status_code=422,
            detail="max_tokens must be a positive integer",
        )
