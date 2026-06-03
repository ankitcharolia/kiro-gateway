# -*- coding: utf-8 -*-
"""
Native ACP endpoints.

Exposes /acp/* routes so ACP-native clients (Zed, JetBrains, Neovim,
OpenCode, Kilo Code in ACP mode) can connect directly without the
OpenAI/Anthropic translation layer.

These routes proxy ACP JSON-RPC messages directly to the kiro-cli
subprocess, making this gateway a transparent ACP relay.

Endpoints:
    POST /acp/initialize
    POST /acp/session/new
    POST /acp/session/prompt      (streaming SSE)
    POST /acp/session/cancel
    GET  /acp/health
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger

from kiro.acp_client import SessionUpdate

router = APIRouter(prefix="/acp", tags=["ACP Native"])


def _get_session_manager(request: Request):
    sm = getattr(request.app.state, "acp_session_manager", None)
    if sm is None:
        raise HTTPException(status_code=503, detail="ACP session manager not available")
    return sm


@router.get("/health")
async def acp_health(request: Request):
    """Health check for the ACP relay."""
    sm = _get_session_manager(request)
    proc = getattr(sm, "_process", None)
    alive = proc is not None and proc.is_alive
    return {
        "status": "ok" if alive else "degraded",
        "kiro_cli_alive": alive,
        "compliance": "single-account ACP mode",
    }


@router.post("/initialize")
async def acp_initialize(request: Request):
    """ACP initialize handshake (passthrough)."""
    sm = _get_session_manager(request)
    proc = await sm.get_process()
    result = await proc.initialize()
    return JSONResponse(content={"jsonrpc": "2.0", "result": result})


@router.post("/session/new")
async def acp_session_new(request: Request):
    """Create a new ACP session."""
    sm = _get_session_manager(request)
    body = await request.json()
    cwd = body.get("cwd")
    proc, session_id = await sm.new_session(cwd=cwd)
    return JSONResponse(content={"jsonrpc": "2.0", "result": {"sessionId": session_id}})


@router.post("/session/prompt")
async def acp_session_prompt(request: Request):
    """
    Send a prompt to an ACP session and stream session/update notifications.

    Request body:
        {"sessionId": "...", "prompt": {"content": [{"type": "text", "text": "..."}]}}

    Response: SSE stream of session/update JSON-RPC notifications,
              terminated by a session/done event.
    """
    sm = _get_session_manager(request)
    body = await request.json()

    session_id = body.get("sessionId")
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId is required")

    prompt = body.get("prompt", {})
    content_blocks = prompt.get("content", [])
    text_parts = [
        block.get("text", "")
        for block in content_blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    prompt_text = "\n".join(text_parts)

    if not prompt_text.strip():
        raise HTTPException(status_code=400, detail="prompt content text is required")

    proc = await sm.get_process()

    async def event_stream():
        try:
            async for update in proc.session_prompt(session_id, prompt_text):
                update: SessionUpdate
                # Emit as ACP-format SSE notification
                notification = {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": session_id,
                        "update": {"type": update.update_type, **update.data},
                    },
                }
                yield f"data: {json.dumps(notification)}\n\n"
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"ACP native stream error: {e}")
            error_event = {"jsonrpc": "2.0", "method": "session/error",
                           "params": {"sessionId": session_id, "error": str(e)}}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/session/cancel")
async def acp_session_cancel(request: Request):
    """Cancel an in-progress ACP session prompt."""
    sm = _get_session_manager(request)
    body = await request.json()
    session_id = body.get("sessionId")
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId is required")
    proc = await sm.get_process()
    await proc.session_cancel(session_id)
    return JSONResponse(content={"jsonrpc": "2.0", "result": {"cancelled": True}})
