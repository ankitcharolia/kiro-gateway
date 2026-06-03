"""Core streaming utilities shared across OpenAI and Anthropic shims."""
from __future__ import annotations
import json
from typing import Any, AsyncIterator


async def sse_stream(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    """Yield server-sent event strings from an async event iterator."""
    async for event in events:
        yield f"data: {json.dumps(event)}\n\n"
    yield "data: [DONE]\n\n"


def make_sse_chunk(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def make_sse_done() -> str:
    return "data: [DONE]\n\n"
