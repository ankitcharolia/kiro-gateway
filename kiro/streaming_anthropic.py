"""Streaming helpers — Anthropic SSE format."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from typing import Any, AsyncIterator, Callable, Dict, Iterator, Optional

from .streaming_core import FirstTokenTimeoutError, KiroEvent, StreamResult, stream_with_first_token_retry


def format_sse_event(event: str, data: Any) -> str:
    """Format a single Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def generate_message_id(prefix: str = "msg") -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


def generate_thinking_signature(thinking_text: str) -> str:
    """Generate a deterministic signature for a thinking block."""
    return hashlib.sha256(thinking_text.encode()).hexdigest()[:32]


def build_message_start(model: str, message_id: Optional[str] = None) -> str:
    return format_sse_event(
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
    block: Dict[str, Any] = {"type": block_type}
    if block_type == "text":
        block["text"] = ""
    return format_sse_event(
        "content_block_start",
        {"type": "content_block_start", "index": index, "content_block": block},
    )


def build_content_block_delta(index: int, text: str) -> str:
    return format_sse_event(
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "text_delta", "text": text},
        },
    )


def build_content_block_stop(index: int) -> str:
    return format_sse_event(
        "content_block_stop",
        {"type": "content_block_stop", "index": index},
    )


def build_message_delta(stop_reason: str = "end_turn", output_tokens: int = 0) -> str:
    return format_sse_event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": output_tokens},
        },
    )


def build_message_stop() -> str:
    return format_sse_event("message_stop", {"type": "message_stop"})


def acp_stream_to_anthropic_events(
    acp_events: Iterator[Dict[str, Any]],
    model: str,
    message_id: Optional[str] = None,
) -> Iterator[str]:
    """Convert an ACP event iterator to Anthropic SSE strings."""
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


async def stream_kiro_to_anthropic(
    kiro_event_stream: AsyncIterator[KiroEvent],
    model: str,
    message_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """Yield Anthropic-format SSE strings from an async KiroEvent stream."""
    _id = message_id or generate_message_id()
    yield build_message_start(model, _id)
    idx = 0
    yield build_content_block_start(idx, "text")

    async for evt in kiro_event_stream:
        if evt.type == "content" and evt.content:
            yield build_content_block_delta(idx, evt.content)
        elif evt.type == "stop":
            break

    yield build_content_block_stop(idx)
    yield build_message_delta("end_turn", 0)
    yield build_message_stop()


async def stream_with_first_token_retry_anthropic(
    stream_factory: Callable[[], AsyncIterator[KiroEvent]],
    model: str,
    first_token_timeout: float = 30.0,
    max_retries: int = 2,
    message_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """Yield Anthropic SSE strings from *stream_factory* with first-token retry.

    Wraps :func:`stream_with_first_token_retry` and pipes the events through
    :func:`stream_kiro_to_anthropic`.
    """
    async def _gen() -> AsyncIterator[str]:
        retry_stream = stream_with_first_token_retry(
            stream_factory,
            first_token_timeout=first_token_timeout,
            max_retries=max_retries,
        )
        async for chunk in stream_kiro_to_anthropic(retry_stream, model, message_id):
            yield chunk

    async for chunk in _gen():
        yield chunk


async def collect_anthropic_response(
    kiro_event_stream: AsyncIterator[KiroEvent],
    model: str,
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Drain *kiro_event_stream* and return a complete Anthropic response dict."""
    _id = message_id or generate_message_id()
    content_parts = []
    usage: Dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}

    async for evt in kiro_event_stream:
        if evt.type == "content" and evt.content:
            content_parts.append({"type": "text", "text": evt.content})
        elif evt.type == "usage" and evt.usage:
            usage.update(evt.usage)

    return {
        "id": _id,
        "type": "message",
        "role": "assistant",
        "content": content_parts,
        "model": model,
        "stop_reason": "end_turn",
        "usage": usage,
    }
