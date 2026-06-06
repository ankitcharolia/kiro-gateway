"""Payload validation and size-guard helpers."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PAYLOAD_BYTES: int = 10 * 1024 * 1024   # 10 MB
MAX_INPUT_TOKENS: int = 100_000


# ---------------------------------------------------------------------------
# Size helpers
# ---------------------------------------------------------------------------

def check_payload_size(
    payload: Dict[str, Any],
    max_bytes: int = MAX_PAYLOAD_BYTES,
) -> Tuple[bool, int]:
    """Return (ok, size_bytes) for *payload* serialised to JSON."""
    size = len(json.dumps(payload).encode("utf-8"))
    return size <= max_bytes, size


def trim_messages(
    messages: List[Dict[str, Any]],
    max_tokens: int = MAX_INPUT_TOKENS,
) -> Tuple[List[Dict[str, Any]], int]:
    """Drop oldest messages until the estimated token count fits *max_tokens*.

    Returns (trimmed_messages, estimated_tokens).
    """
    from .tokenizer import count_message_tokens

    result = list(messages)
    while result and count_message_tokens(result) > max_tokens:
        # Preserve a leading system message if present.
        if len(result) > 1 and result[0].get("role") == "system":
            result.pop(1)
        else:
            result.pop(0)
    return result, count_message_tokens(result)


def trim_payload_to_limit(
    payload: Dict[str, Any],
    max_tokens: int = MAX_INPUT_TOKENS,
) -> Dict[str, Any]:
    """Return a copy of *payload* with messages trimmed to fit *max_tokens*."""
    messages = payload.get("messages", [])
    trimmed, _ = trim_messages(messages, max_tokens)
    return {**payload, "messages": trimmed}


# ---------------------------------------------------------------------------
# Guard functions
# ---------------------------------------------------------------------------

def guard_openai_request(
    payload: Dict[str, Any],
    max_bytes: int = MAX_PAYLOAD_BYTES,
    max_tokens: int = MAX_INPUT_TOKENS,
) -> Dict[str, Any]:
    """Validate and trim an OpenAI-format request payload.

    Raises ``ValueError`` if the raw payload exceeds *max_bytes*.
    Returns the (possibly trimmed) payload.
    """
    ok, size = check_payload_size(payload, max_bytes)
    if not ok:
        raise ValueError(f"Payload too large: {size} bytes (limit {max_bytes})")
    return trim_payload_to_limit(payload, max_tokens)


def guard_anthropic_request(
    payload: Dict[str, Any],
    max_bytes: int = MAX_PAYLOAD_BYTES,
    max_tokens: int = MAX_INPUT_TOKENS,
) -> Dict[str, Any]:
    """Validate and trim an Anthropic-format request payload.

    Raises ``ValueError`` if the raw payload exceeds *max_bytes*.
    Returns the (possibly trimmed) payload.
    """
    ok, size = check_payload_size(payload, max_bytes)
    if not ok:
        raise ValueError(f"Payload too large: {size} bytes (limit {max_bytes})")
    return trim_payload_to_limit(payload, max_tokens)
