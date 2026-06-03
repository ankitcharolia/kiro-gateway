"""Anthropic SSE streaming helpers."""
from __future__ import annotations
import json
from typing import Any, AsyncIterator


def make_anthropic_event(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def stream_anthropic(
    events: AsyncIterator[dict[str, Any]],
    message_id: str,
    model: str,
) -> AsyncIterator[str]:
    yield make_anthropic_event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )
    yield make_anthropic_event(
        "content_block_start",
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    )
    async for event in events:
        if event.get("type") == "text":
            yield make_anthropic_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": event["content"]},
                },
            )
        elif event.get("type") == "done":
            break
    yield make_anthropic_event(
        "content_block_stop", {"type": "content_block_stop", "index": 0}
    )
    yield make_anthropic_event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 0},
        },
    )
    yield make_anthropic_event("message_stop", {"type": "message_stop"})
