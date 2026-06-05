"""Stream ACP events -> OpenAI-compatible SSE chunks."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from .models_openai import (
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionUsage,
    FunctionCall,
    ToolCall,
)
from .streaming_core import (
    sse_encode, chunk_to_dict,
    is_text_delta, is_thinking_delta, is_tool_delta,
    is_content_block_start, is_content_block_stop,
    is_message_start, is_message_delta, is_message_stop,
    extract_text_delta, extract_thinking_delta, extract_tool_delta,
    extract_stop_reason, extract_usage,
)


def _now() -> int:
    return int(time.time())


def _make_chunk(
    rid: str, model: str,
    delta: ChatCompletionChunkDelta,
    finish_reason: Optional[str] = None,
    usage: Optional[ChatCompletionUsage] = None,
) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=rid, object="chat.completion.chunk",
        created=_now(), model=model,
        choices=[ChatCompletionChunkChoice(index=0, delta=delta, finish_reason=finish_reason)],
        usage=usage,
    )


async def acp_stream_to_openai_chunks(
    acp_events: AsyncIterator[Dict[str, Any]],
    model: str,
    request_id: Optional[str] = None,
    include_usage: bool = False,
) -> AsyncIterator[str]:
    """Yield SSE-encoded OpenAI chunk strings from raw ACP event dicts."""
    rid = request_id or f"chatcmpl-{uuid.uuid4().hex}"
    tool_call_index: Dict[int, Dict[str, Any]] = {}
    block_types: Dict[int, str] = {}
    finish_reason: Optional[str] = None
    final_usage: Optional[ChatCompletionUsage] = None

    # Opening role delta
    yield sse_encode(chunk_to_dict(_make_chunk(rid, model, ChatCompletionChunkDelta(role="assistant"))))

    async for event in acp_events:
        if is_message_start(event):
            u = (event.get("message") or {}).get("usage")
            if u and include_usage:
                final_usage = ChatCompletionUsage(
                    prompt_tokens=u.get("input_tokens", 0),
                    completion_tokens=0,
                    total_tokens=u.get("input_tokens", 0),
                )
            continue

        if is_content_block_start(event):
            idx = event.get("index", 0)
            cb = event.get("content_block", {})
            cb_type = cb.get("type", "text")
            block_types[idx] = cb_type
            if cb_type == "tool_use":
                tool_call_index[idx] = {"id": cb.get("id", str(uuid.uuid4())), "name": cb.get("name", ""), "arguments": ""}
                yield sse_encode(chunk_to_dict(_make_chunk(rid, model, ChatCompletionChunkDelta(
                    tool_calls=[ToolCall(
                        id=tool_call_index[idx]["id"], type="function",
                        function=FunctionCall(name=tool_call_index[idx]["name"], arguments=""),
                    )]
                ))))
            continue

        if is_text_delta(event):
            text = extract_text_delta(event)
            if text:
                yield sse_encode(chunk_to_dict(_make_chunk(rid, model, ChatCompletionChunkDelta(content=text))))
            continue

        if is_thinking_delta(event):
            thinking = extract_thinking_delta(event)
            if thinking:
                yield sse_encode(chunk_to_dict(_make_chunk(rid, model, ChatCompletionChunkDelta(reasoning_content=thinking))))
            continue

        if is_tool_delta(event):
            partial = extract_tool_delta(event)
            idx = event.get("index", 0)
            if idx in tool_call_index:
                tool_call_index[idx]["arguments"] += partial
            if partial:
                yield sse_encode(chunk_to_dict(_make_chunk(rid, model, ChatCompletionChunkDelta(
                    tool_calls=[ToolCall(
                        id=tool_call_index.get(idx, {}).get("id", ""), type="function",
                        function=FunctionCall(name=tool_call_index.get(idx, {}).get("name", ""), arguments=partial),
                    )]
                ))))
            continue

        if is_message_delta(event):
            stop = extract_stop_reason(event)
            if stop:
                reason_map = {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_calls", "stop_sequence": "stop"}
                finish_reason = reason_map.get(stop, "stop")
            if include_usage:
                u = extract_usage(event)
                if u and final_usage:
                    out = u.get("output_tokens", 0)
                    final_usage.completion_tokens = out
                    final_usage.total_tokens = final_usage.prompt_tokens + out
            continue

        if is_message_stop(event):
            break

    yield sse_encode(chunk_to_dict(_make_chunk(
        rid, model, ChatCompletionChunkDelta(),
        finish_reason=finish_reason or "stop",
        usage=final_usage if include_usage else None,
    )))
    yield sse_encode("[DONE]")
