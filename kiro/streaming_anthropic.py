"""Stream ACP events -> Anthropic-compatible SSE events."""
from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Dict, Optional

from .models_anthropic import (
    AnthropicResponse, AnthropicUsage,
    TextContentBlock, ThinkingContentBlock, ToolUseContentBlock,
    MessageStartEvent, MessageDeltaEvent, MessageStopEvent,
    MessageDelta, MessageDeltaUsage,
    ContentBlockStartEvent, ContentBlockDeltaEvent, ContentBlockStopEvent,
    TextDelta, ThinkingDelta, InputJsonDelta,
)
from .streaming_core import (
    sse_encode, chunk_to_dict,
    is_text_delta, is_thinking_delta, is_tool_delta,
    is_content_block_start, is_content_block_stop,
    is_message_start, is_message_delta, is_message_stop,
    extract_text_delta, extract_thinking_delta, extract_tool_delta,
    extract_stop_reason, extract_usage,
)


async def acp_stream_to_anthropic_events(
    acp_events: AsyncIterator[Dict[str, Any]],
    model: str,
    request_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """Yield SSE-encoded Anthropic event strings from raw ACP event dicts."""
    rid = request_id or f"msg_{uuid.uuid4().hex}"

    initial_response = AnthropicResponse(
        id=rid, type="message", role="assistant", model=model,
        content=[], stop_reason=None,
        usage=AnthropicUsage(input_tokens=0, output_tokens=0),
    )
    yield sse_encode(chunk_to_dict(MessageStartEvent(type="message_start", message=initial_response)), event="message_start")

    finish_reason: Optional[str] = None
    output_tokens: int = 0
    input_tokens: int = 0

    async for event in acp_events:
        if is_message_start(event):
            u = (event.get("message") or {}).get("usage", {})
            input_tokens = u.get("input_tokens", 0)
            initial_response.usage.input_tokens = input_tokens
            yield sse_encode(chunk_to_dict(MessageStartEvent(type="message_start", message=initial_response)), event="message_start")
            continue

        if is_content_block_start(event):
            idx = event.get("index", 0)
            cb = event.get("content_block", {})
            cb_type = cb.get("type", "text")
            if cb_type == "text":
                block = TextContentBlock(type="text", text="")
            elif cb_type == "thinking":
                block = ThinkingContentBlock(type="thinking", thinking="")
            elif cb_type == "tool_use":
                block = ToolUseContentBlock(
                    type="tool_use", id=cb.get("id", str(uuid.uuid4())),
                    name=cb.get("name", ""), input={},
                )
            else:
                block = TextContentBlock(type="text", text="")
            yield sse_encode(chunk_to_dict(ContentBlockStartEvent(type="content_block_start", index=idx, content_block=block)), event="content_block_start")
            continue

        if is_text_delta(event):
            idx = event.get("index", 0)
            yield sse_encode(chunk_to_dict(ContentBlockDeltaEvent(
                type="content_block_delta", index=idx,
                delta=TextDelta(type="text_delta", text=extract_text_delta(event)),
            )), event="content_block_delta")
            continue

        if is_thinking_delta(event):
            idx = event.get("index", 0)
            yield sse_encode(chunk_to_dict(ContentBlockDeltaEvent(
                type="content_block_delta", index=idx,
                delta=ThinkingDelta(type="thinking_delta", thinking=extract_thinking_delta(event)),
            )), event="content_block_delta")
            continue

        if is_tool_delta(event):
            idx = event.get("index", 0)
            yield sse_encode(chunk_to_dict(ContentBlockDeltaEvent(
                type="content_block_delta", index=idx,
                delta=InputJsonDelta(type="input_json_delta", partial_json=extract_tool_delta(event)),
            )), event="content_block_delta")
            continue

        if is_content_block_stop(event):
            idx = event.get("index", 0)
            yield sse_encode(chunk_to_dict(ContentBlockStopEvent(type="content_block_stop", index=idx)), event="content_block_stop")
            continue

        if is_message_delta(event):
            stop = extract_stop_reason(event)
            if stop:
                finish_reason = stop
            u = extract_usage(event)
            if u:
                output_tokens = u.get("output_tokens", 0)
            yield sse_encode(chunk_to_dict(MessageDeltaEvent(
                type="message_delta",
                delta=MessageDelta(stop_reason=finish_reason),
                usage=MessageDeltaUsage(output_tokens=output_tokens),
            )), event="message_delta")
            continue

        if is_message_stop(event):
            break

    yield sse_encode(chunk_to_dict(MessageStopEvent(type="message_stop")), event="message_stop")
