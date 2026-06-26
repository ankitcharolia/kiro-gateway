# -*- coding: utf-8 -*-
"""
Native ACP endpoints.

Exposes ACP as HTTP for editors that support the ACP-over-HTTP transport
(Zed, JetBrains Kiro plugin, etc.) rather than the stdio transport.

Endpoints
---------
POST /acp/chat            — non-streaming ACP chat
POST /acp/chat/stream     — SSE streaming ACP chat with real event mirror
GET  /acp/session/new     — create a session and return its ID
DELETE /acp/session/{id}  — close a session
"""
from __future__ import annotations

import json
import asyncio
from typing import Optional, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from kiro.acp_models import (
    ACPChatRequest, ACPChatResponse,
    PromptMessage, PromptParams, ProgressParams,
    GatewayCapabilities,
    ToolResult,
)
from kiro.shim_service import ShimService
from kiro.config import settings

router = APIRouter(prefix="/acp", tags=["ACP"])


def _get_shim(request: Request) -> ShimService:
    return request.app.state.shim_service


# ---------------------------------------------------------------------------
# Non-streaming
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ACPChatResponse)
async def acp_chat(
    body: ACPChatRequest,
    shim: ShimService = Depends(_get_shim),
) -> ACPChatResponse:
    """Non-streaming ACP chat completion."""
    try:
        result = await shim.complete(
            messages=body.messages,
            model=body.model,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            tools=body.tools or [],
            filesystem_roots=body.filesystem_roots or [],
            terminal=body.terminal,
        )
    except Exception as exc:
        logger.error(f"ACP chat error: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))

    from kiro.acp_models import ToolCall
    tool_calls = [
        ToolCall(**tc) if isinstance(tc, dict) else tc
        for tc in result.get("tool_calls", [])
    ]

    return ACPChatResponse(
        session_id="",
        content=result["content"],
        tool_calls=tool_calls,
        finish_reason=result.get("finish_reason", "stop"),
        usage=result.get("usage", {}),
    )


# ---------------------------------------------------------------------------
# Streaming — real ACP event mirror over SSE
# ---------------------------------------------------------------------------

@router.post("/chat/stream")
async def acp_chat_stream(
    body: ACPChatRequest,
    shim: ShimService = Depends(_get_shim),
) -> StreamingResponse:
    """
    SSE streaming ACP chat.

    Each SSE event maps 1:1 to an ACP progress notification:
      event: acp_text       — delta text token
      event: acp_tool_call  — tool call from the model
      event: acp_thinking   — thinking/reasoning delta
      event: acp_plan       — task list / plan (gated by ACP_SURFACE_THINKING)
      event: acp_done       — stream finished (includes usage)
      event: acp_error      — error
      event: acp_capability — capability request forwarded to caller
    """
    async def generate() -> AsyncIterator[str]:
        try:
            async for event in shim.stream_tokens(
                messages=body.messages,
                model=body.model,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
                tools=body.tools or [],
                filesystem_roots=body.filesystem_roots or [],
                terminal=body.terminal,
            ):
                etype = event.get("type", "text")
                if etype == "plan" and not settings.ACP_SURFACE_THINKING:
                    continue
                yield f"event: acp_{etype}\ndata: {json.dumps(event)}\n\n"
                if etype in ("done", "error"):
                    break
        except Exception as exc:
            logger.error(f"ACP stream error: {exc}")
            yield f"event: acp_error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
