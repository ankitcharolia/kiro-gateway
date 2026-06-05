"""Streaming helpers — OpenAI SSE format."""
from __future__ import annotations

import json
import secrets
import time
from typing import Any, Dict, Iterator, List, Optional


def generate_chunk_id(prefix: str = "chatcmpl") -> str:
    """Return a unique OpenAI-style completion ID."""
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
    """Build and serialise a single OpenAI streaming chunk."""
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
    """Translate ACP stream events into OpenAI SSE chunks.

    Yields raw SSE strings ready to be written to the response.
    """
    _id = chunk_id or generate_chunk_id()
    _created = int(time.time())

    # role header
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


# Backward-compat alias
stream_kiro_to_openai = acp_stream_to_openai_chunks
