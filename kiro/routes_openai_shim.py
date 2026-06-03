# -*- coding: utf-8 -*-
"""
OpenAI-compatible shim routes backed by ACP.

Endpoints
---------
GET  /v1/models
POST /v1/chat/completions   (streaming + non-streaming)

Fixes
-----
1. STREAMING: Events are yielded token-by-token from ACP progress
   notifications. No buffering. Clients see tokens as kiro-cli emits them.

2. TOOL-CALLING: Full parallel + sequential tool_call round-trip.
   - tool_use events from ACP are translated to OpenAI function_call deltas.
   - Caller sends back tool role messages; these are injected as a
     follow-up session/prompt so kiro-cli sees them.

3. FILESYSTEM/TERMINAL: Capability requests are handled transparently
   by CapabilityExecutor. The token stream is not interrupted.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from kiro.acp_models import PromptMessage, ToolResult, FilesystemRoot, TerminalCapability
from kiro.shim_service import ShimService

router = APIRouter(prefix="/v1", tags=["OpenAI Shim"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class OAIToolFunction(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class OAITool(BaseModel):
    type: str = "function"
    function: OAIToolFunction


class OAIMessage(BaseModel):
    role: str
    content: Optional[Any] = None  # str | list[content_part]
    name: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None


class OAIChatRequest(BaseModel):
    model: str = "claude-sonnet-4-5"
    messages: list[OAIMessage]
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: Optional[list[OAITool]] = None
    # Gateway extensions (optional, ignored by standard clients)
    filesystem_roots: list[dict] = Field(default_factory=list)
    terminal: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _oai_messages_to_acp(messages: list[OAIMessage]) -> list[PromptMessage]:
    """Convert OpenAI message list to ACP PromptMessage list."""
    result = []
    for m in messages:
        role = m.role
        if role == "system":
            role = "user"  # ACP uses user role for system context
        if role not in ("user", "assistant", "tool"):
            role = "user"

        # Flatten content
        if isinstance(m.content, list):
            text_parts = []
            for part in m.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "tool_result":
                        text_parts.append(str(part.get("content", "")))
                else:
                    text_parts.append(str(part))
            content = "\n".join(text_parts)
        else:
            content = m.content or ""

        # tool role: wrap with tool_call_id context
        if m.role == "tool" and m.tool_call_id:
            content = f"[tool_result id={m.tool_call_id}]\n{content}"

        result.append(PromptMessage(role=role, content=str(content)))
    return result


def _acp_tool_calls_to_oai(tool_calls: list[dict]) -> list[dict]:
    """Convert ACP ToolCall list to OpenAI tool_calls format."""
    result = []
    for tc in tool_calls:
        result.append({
            "id": tc.get("id", str(uuid.uuid4())),
            "type": "function",
            "function": {
                "name": tc.get("name", ""),
                "arguments": json.dumps(tc.get("arguments", {})),
            },
        })
    return result


def _get_shim(request: Request) -> ShimService:
    return request.app.state.shim_service


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models():
    models = [
        {"id": "claude-sonnet-4-5", "object": "model", "owned_by": "kiro"},
        {"id": "claude-opus-4-5", "object": "model", "owned_by": "kiro"},
        {"id": "claude-haiku-3-5", "object": "model", "owned_by": "kiro"},
    ]
    return {"object": "list", "data": models}


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------

@router.post("/chat/completions")
async def chat_completions(
    body: OAIChatRequest,
    shim: ShimService = Depends(_get_shim),
):
    messages = _oai_messages_to_acp(body.messages)
    tools = [t.model_dump() for t in (body.tools or [])]
    fs_roots = [FilesystemRoot(**r) for r in body.filesystem_roots] if body.filesystem_roots else []
    terminal = TerminalCapability(**body.terminal) if body.terminal else None

    if body.stream:
        return StreamingResponse(
            _stream_response(shim, messages, body.model, body.max_tokens,
                             body.temperature, tools, fs_roots, terminal),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming
    try:
        result = await shim.complete(
            messages=messages,
            model=body.model,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            tools=tools,
            filesystem_roots=fs_roots,
            terminal=terminal,
        )
    except Exception as exc:
        logger.error(f"OpenAI shim complete error: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))

    tool_calls = _acp_tool_calls_to_oai(result.get("tool_calls", []))
    finish_reason = "tool_calls" if tool_calls else result.get("finish_reason", "stop")

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": result["content"] if not tool_calls else None,
                "tool_calls": tool_calls if tool_calls else None,
            },
            "finish_reason": finish_reason,
        }],
        "usage": {
            "prompt_tokens": result.get("usage", {}).get("input_tokens", 0),
            "completion_tokens": result.get("usage", {}).get("output_tokens", 0),
            "total_tokens": result.get("usage", {}).get("total_tokens", 0),
        },
    }


async def _stream_response(
    shim: ShimService,
    messages: list[PromptMessage],
    model: str,
    max_tokens: Optional[int],
    temperature: Optional[float],
    tools: list[dict],
    fs_roots: list[FilesystemRoot],
    terminal: Optional[TerminalCapability],
) -> AsyncIterator[str]:
    """
    Translate ACP progress events to OpenAI streaming SSE format.

    ACP event types → OpenAI SSE:
      text       → delta.content chunk
      tool_call  → delta.tool_calls chunk (name + arguments streaming)
      thinking   → delta.content chunk (prefixed with <thinking>)
      done       → [DONE] + finish_reason
      error      → error chunk
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    active_tool_idx: dict[str, int] = {}  # tool_call_id -> index
    tool_counter = 0

    def chunk(delta: dict, finish_reason: Optional[str] = None) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }],
        }
        return f"data: {json.dumps(payload)}\n\n"

    # Opening role chunk
    yield chunk({"role": "assistant", "content": ""})

    try:
        async for event in shim.stream_tokens(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            filesystem_roots=fs_roots,
            terminal=terminal,
        ):
            if event.type == "text" and event.delta:
                yield chunk({"content": event.delta})

            elif event.type == "thinking" and event.delta:
                # Surface thinking as content for clients that support it
                yield chunk({"content": event.delta})

            elif event.type == "tool_call" and event.tool_call:
                tc = event.tool_call
                if tc.id not in active_tool_idx:
                    idx = tool_counter
                    active_tool_idx[tc.id] = idx
                    tool_counter += 1
                    # Header chunk: id + function name
                    yield chunk({"tool_calls": [{
                        "index": idx,
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": ""},
                    }]})
                else:
                    idx = active_tool_idx[tc.id]

                # Arguments streaming chunk
                args_str = json.dumps(tc.arguments) if tc.arguments else ""
                if args_str:
                    yield chunk({"tool_calls": [{
                        "index": idx,
                        "function": {"arguments": args_str},
                    }]})

            elif event.type == "done":
                finish_reason = "tool_calls" if active_tool_idx else (
                    event.finish_reason or "stop"
                )
                yield chunk({}, finish_reason=finish_reason)
                yield "data: [DONE]\n\n"
                break

            elif event.type == "error":
                error_payload = {"error": {"message": event.error or "Unknown error", "type": "acp_error"}}
                yield f"data: {json.dumps(error_payload)}\n\n"
                yield "data: [DONE]\n\n"
                break

    except Exception as exc:
        logger.error(f"OpenAI stream error: {exc}")
        error_payload = {"error": {"message": str(exc), "type": "gateway_error"}}
        yield f"data: {json.dumps(error_payload)}\n\n"
        yield "data: [DONE]\n\n"
