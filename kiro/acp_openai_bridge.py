# -*- coding: utf-8 -*-
"""
ACP ↔ OpenAI / Anthropic bridge.

Translates:
  OpenAI  chat/completions  →  ACP session/prompt  →  OpenAI streaming SSE
  Anthropic messages        →  ACP session/prompt  →  Anthropic streaming SSE

This is the core of the compliance story: all AI completions now flow
through kiro-cli (the authorized client) via the ACP protocol, not through
direct Kiro internal API calls.
"""

import asyncio
import json
import time
import uuid
from typing import AsyncIterator, Optional, Any
from loguru import logger

from kiro.acp_client import (
    KiroCLIProcess,
    SessionUpdate,
    UPDATE_AGENT_MESSAGE_CHUNK,
    UPDATE_THOUGHT_MESSAGE_CHUNK,
    UPDATE_TOOL_CALL,
    UPDATE_TOOL_CALL_UPDATE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_prompt_text(messages: list[dict]) -> str:
    """
    Flatten an OpenAI/Anthropic messages array into a plain-text prompt
    suitable for the ACP session/prompt content field.

    ACP is conversation-aware (each session maintains history), so for
    multi-turn conversations we include the full message thread so that
    kiro-cli has complete context.
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            # OpenAI content blocks [{"type": "text", "text": "..."}]
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            content = "\n".join(text_parts)

        if role == "system":
            parts.append(f"<system>\n{content}\n</system>")
        elif role == "assistant":
            parts.append(f"<assistant>\n{content}\n</assistant>")
        else:
            parts.append(content)

    return "\n\n".join(parts)


def _sse_line(data: str) -> bytes:
    return f"data: {data}\n\n".encode()


def _sse_done() -> bytes:
    return b"data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# OpenAI Streaming Bridge
# ---------------------------------------------------------------------------

async def openai_stream_from_acp(
    process: KiroCLIProcess,
    session_id: str,
    messages: list[dict],
    model: str = "kiro",
    request_id: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """
    Stream OpenAI-compatible SSE chunks from an ACP session/prompt call.

    Yields bytes suitable for a FastAPI StreamingResponse.

    SSE format:
        data: {"id": "...", "object": "chat.completion.chunk", ...}\n\n
        data: [DONE]\n\n
    """
    completion_id = request_id or f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    prompt_text = _build_prompt_text(messages)

    # Opening chunk — empty delta with role
    opening = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": ""},
            "finish_reason": None,
        }],
    }
    yield _sse_line(json.dumps(opening))

    stop_reason = "stop"

    try:
        async for update in process.session_prompt(session_id, prompt_text):
            update: SessionUpdate

            if update.update_type == UPDATE_AGENT_MESSAGE_CHUNK:
                text = update.data.get("text", "")
                if text:
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": None,
                        }],
                    }
                    yield _sse_line(json.dumps(chunk))

            elif update.update_type == UPDATE_THOUGHT_MESSAGE_CHUNK:
                # Expose reasoning as a special delta (compatible with extended thinking)
                text = update.data.get("text", "")
                if text:
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": ""},  # suppress in content
                            "finish_reason": None,
                        }],
                        "_reasoning": text,  # non-standard extension
                    }
                    yield _sse_line(json.dumps(chunk))

            elif update.update_type == UPDATE_TOOL_CALL:
                # Tool call started — emit as OpenAI tool_calls delta
                tool_id = update.data.get("id", f"call_{uuid.uuid4().hex[:8]}")
                tool_name = update.data.get("title", "unknown")
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "id": tool_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": ""},
                            }]
                        },
                        "finish_reason": None,
                    }],
                }
                yield _sse_line(json.dumps(chunk))

            elif update.update_type == "done":
                raw_stop = update.data.get("stop_reason", "end_turn")
                stop_reason = _map_stop_reason(raw_stop)

    except Exception as e:
        logger.error(f"ACP streaming error: {e}")
        error_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n[Gateway error: {e}]"},
                "finish_reason": "stop",
            }],
        }
        yield _sse_line(json.dumps(error_chunk))
        yield _sse_done()
        return

    # Final chunk with finish_reason
    final = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": stop_reason,
        }],
    }
    yield _sse_line(json.dumps(final))
    yield _sse_done()


async def openai_complete_from_acp(
    process: KiroCLIProcess,
    session_id: str,
    messages: list[dict],
    model: str = "kiro",
) -> dict:
    """
    Non-streaming OpenAI completion from ACP.

    Collects all agent_message_chunk updates and returns a single
    chat.completion object.
    """
    prompt_text = _build_prompt_text(messages)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    content_parts = []
    stop_reason = "stop"

    async for update in process.session_prompt(session_id, prompt_text):
        if update.update_type == UPDATE_AGENT_MESSAGE_CHUNK:
            text = update.data.get("text", "")
            if text:
                content_parts.append(text)
        elif update.update_type == "done":
            raw_stop = update.data.get("stop_reason", "end_turn")
            stop_reason = _map_stop_reason(raw_stop)

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "".join(content_parts),
            },
            "finish_reason": stop_reason,
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


# ---------------------------------------------------------------------------
# Anthropic Streaming Bridge
# ---------------------------------------------------------------------------

async def anthropic_stream_from_acp(
    process: KiroCLIProcess,
    session_id: str,
    messages: list[dict],
    model: str = "kiro",
) -> AsyncIterator[bytes]:
    """
    Stream Anthropic-compatible SSE events from an ACP session.

    Anthropic streaming SSE format:
        data: {"type": "message_start", ...}
        data: {"type": "content_block_start", ...}
        data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "..."}}
        data: {"type": "content_block_stop"}
        data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}
        data: {"type": "message_stop"}
    """
    message_id = f"msg_{uuid.uuid4().hex[:24]}"
    prompt_text = _build_prompt_text(messages)

    yield _sse_line(json.dumps({
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
    }))
    yield _sse_line(json.dumps({"type": "content_block_start", "index": 0,
                                "content_block": {"type": "text", "text": ""}}))
    yield _sse_line(json.dumps({"type": "ping"}))

    stop_reason = "end_turn"

    try:
        async for update in process.session_prompt(session_id, prompt_text):
            if update.update_type == UPDATE_AGENT_MESSAGE_CHUNK:
                text = update.data.get("text", "")
                if text:
                    yield _sse_line(json.dumps({
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": text},
                    }))
            elif update.update_type == "done":
                stop_reason = update.data.get("stop_reason", "end_turn")

    except Exception as e:
        logger.error(f"ACP→Anthropic streaming error: {e}")
        yield _sse_line(json.dumps({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": f"\n[Gateway error: {e}]"},
        }))

    yield _sse_line(json.dumps({"type": "content_block_stop", "index": 0}))
    yield _sse_line(json.dumps({
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": 0},
    }))
    yield _sse_line(json.dumps({"type": "message_stop"}))


async def anthropic_complete_from_acp(
    process: KiroCLIProcess,
    session_id: str,
    messages: list[dict],
    model: str = "kiro",
) -> dict:
    """Non-streaming Anthropic completion from ACP."""
    prompt_text = _build_prompt_text(messages)
    content_parts = []
    stop_reason = "end_turn"

    async for update in process.session_prompt(session_id, prompt_text):
        if update.update_type == UPDATE_AGENT_MESSAGE_CHUNK:
            text = update.data.get("text", "")
            if text:
                content_parts.append(text)
        elif update.update_type == "done":
            stop_reason = update.data.get("stop_reason", "end_turn")

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": "".join(content_parts)}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _map_stop_reason(acp_reason: str) -> str:
    """Map ACP stop reasons to OpenAI finish_reason values."""
    mapping = {
        "end_turn": "stop",
        "cancelled": "stop",
        "error": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
    }
    return mapping.get(acp_reason, "stop")
