"""Streaming helpers — Anthropic SSE format."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any, AsyncIterator, Dict, Iterator, Optional


def generate_message_id(prefix: str = "msg") -> str:
    """Return a unique Anthropic-style message ID.

    Example: ``"msg_01Abc3XyZ"``
    """
    return f"{prefix}_{secrets.token_urlsafe(12)}"


def _sse_line(event: str, data: Any) -> str:
    """Format a single SSE event line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def build_message_start(model: str, message_id: Optional[str] = None) -> str:
    """Emit the ``message_start`` SSE event."""
    return _sse_line(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id or generate_message_id(),
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )


def build_content_block_start(index: int, block_type: str = "text") -> str:
    """Emit a ``content_block_start`` SSE event."""
    block: Dict[str, Any] = {"type": block_type}
    if block_type == "text":
        block["text"] = ""
    return _sse_line(
        "content_block_start",
        {"type": "content_block_start", "index": index, "content_block": block},
    )


def build_content_block_delta(index: int, text: str) -> str:
    """Emit a ``content_block_delta`` SSE event."""
    return _sse_line(
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "text_delta", "text": text},
        },
    )


def build_content_block_stop(index: int) -> str:
    """Emit a ``content_block_stop`` SSE event."""
    return _sse_line(
        "content_block_stop",
        {"type": "content_block_stop", "index": index},
    )


def build_message_delta(
    stop_reason: str = "end_turn",
    output_tokens: int = 0,
) -> str:
    """Emit a ``message_delta`` SSE event."""
    return _sse_line(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": output_tokens},
        },
    )


def build_message_stop() -> str:
    """Emit the ``message_stop`` SSE event."""
    return _sse_line("message_stop", {"type": "message_stop"})


# ---------------------------------------------------------------------------
# Backward-compat additions expected by tests
# ---------------------------------------------------------------------------

def generate_thinking_signature(thinking_text: str) -> str:
    """Return a deterministic hex signature for a thinking block.

    Used by tests that verify thinking blocks carry a stable identifier.
    """
    return hashlib.sha256(thinking_text.encode()).hexdigest()[:32]


def acp_stream_to_anthropic_events(
    acp_events: Iterator[Dict[str, Any]],
    model: str,
    message_id: Optional[str] = None,
) -> Iterator[str]:
    """Translate ACP stream events into Anthropic SSE strings.

    Yields raw SSE strings ready to be written to the response.
    Accepts a sync iterable of ACP event dicts.
    """
    _id = message_id or generate_message_id()
    yield build_message_start(model, _id)
    idx = 0
    yield build_content_block_start(idx, "text")

    for event in acp_events:
        etype = event.get("event", "")
        data = event.get("data", {})
        if etype == "text_delta":
            text = data.get("text", "")
            if text:
                yield build_content_block_delta(idx, text)
        elif etype in ("message_stop", "end"):
            stop_reason = data.get("stop_reason", "end_turn")
            output_tokens = data.get("usage", {}).get("output_tokens", 0)
            yield build_content_block_stop(idx)
            yield build_message_delta(stop_reason, output_tokens)
            yield build_message_stop()
            return

    yield build_content_block_stop(idx)
    yield build_message_delta("end_turn", 0)
    yield build_message_stop()
