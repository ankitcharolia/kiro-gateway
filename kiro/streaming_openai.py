"""OpenAI SSE streaming helpers."""
from __future__ import annotations
import json
import time
from typing import Any, AsyncIterator


def make_openai_chunk(
    chunk_id: str,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


async def stream_openai(
    events: AsyncIterator[dict[str, Any]],
    chunk_id: str,
    model: str,
) -> AsyncIterator[str]:
    async for event in events:
        if event.get("type") == "text":
            chunk = make_openai_chunk(chunk_id, model, {"content": event["content"]})
            yield f"data: {json.dumps(chunk)}\n\n"
        elif event.get("type") == "done":
            chunk = make_openai_chunk(
                chunk_id, model, {}, finish_reason=event.get("finish_reason", "stop")
            )
            yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"
