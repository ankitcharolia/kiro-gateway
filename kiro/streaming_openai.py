"""Streaming helpers — OpenAI SSE format."""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Any, AsyncIterator, Callable, Dict, Iterator, Optional

from .streaming_core import FirstTokenTimeoutError, KiroEvent, stream_with_first_token_retry


def generate_chunk_id(prefix: str = "chatcmpl") -> str:
    return f"{prefix}-{secrets.token_hex(12)}"


def _sse_line(data: Any) -> str:
    if data == "[DONE]":
        return "data: [DONE]\n\n"
    return f"data: {json.dumps(data)}\n\n"


def build_chunk(
    chunk_id: str,
    model: str,
    delta: Dict[str, Any],
    finish_reason: Optional[str] = None,
    created: Optional[int] = None,
) -> str:
    return _sse_line(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created or int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
    )


def acp_stream_to_openai_chunks(
    acp_events: Iterator[Dict[str, Any]],
    model: str,
    chunk_id: Optional[str] = None,
) -> Iterator[str]:
    _id = chunk_id or generate_chunk_id()
    _created = int(time.time())
    yield build_chunk(_id, model, {"role": "assistant", "content": ""}, created=_created)

    for event in acp_events:
        etype = event.get("event", "")
        data = event.get("data", {})
        if etype == "text_delta":
            text = data.get("text", "")
            if text:
                yield build_chunk(_id, model, {"content": text}, created=_created)
        elif etype in ("message_stop", "end"):
            stop_reason = data.get("stop_reason", "stop")
            openai_reason = "tool_calls" if stop_reason == "tool_use" else "stop"
            yield build_chunk(_id, model, {}, finish_reason=openai_reason, created=_created)
            break

    yield _sse_line("[DONE]")


# Backward-compat aliases
stream_kiro_to_openai = acp_stream_to_openai_chunks


def stream_kiro_to_openai_internal(
    acp_events: Iterator[Dict[str, Any]],
    model: str,
    chunk_id: Optional[str] = None,
) -> Iterator[str]:
    """Alias for acp_stream_to_openai_chunks used internally by the shim."""
    yield from acp_stream_to_openai_chunks(acp_events, model, chunk_id)


async def collect_stream_response(
    kiro_event_stream: AsyncIterator[KiroEvent],
    model: str,
    chunk_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Drain *kiro_event_stream* and return a complete OpenAI response dict."""
    _id = chunk_id or generate_chunk_id()
    text_parts = []
    usage: Dict[str, Any] = {}

    async for evt in kiro_event_stream:
        if evt.type == "content" and evt.content:
            text_parts.append(evt.content)
        elif evt.type == "usage" and evt.usage:
            usage.update(evt.usage)

    return {
        "id": _id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "".join(text_parts)},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }
