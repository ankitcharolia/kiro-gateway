# -*- coding: utf-8 -*-
"""
OpenAI-compatible routes backed by ACP (kiro-cli).

Replaces the direct-API routes with ACP-compliant versions:
  POST /v1/chat/completions  →  ACP session/prompt via kiro-cli
  GET  /v1/models            →  static model list

This makes tools like Cursor, Cline, Kilo Code, OpenCode, Hermes, and
OpenClaw work through the APPROVED ACP→kiro-cli pathway.
"""

import time
import uuid
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger

from kiro.acp_openai_bridge import openai_stream_from_acp, openai_complete_from_acp

router = APIRouter(tags=["OpenAI Compatible (ACP)"])

# Models exposed — kiro-cli selects the actual model based on account tier
KIRO_MODELS = [
    {"id": "claude-sonnet-4-5",      "object": "model", "created": 1700000000, "owned_by": "kiro"},
    {"id": "claude-haiku-4-5",       "object": "model", "created": 1700000000, "owned_by": "kiro"},
    {"id": "claude-opus-4-5",        "object": "model", "created": 1700000000, "owned_by": "kiro"},
    {"id": "claude-sonnet-4",        "object": "model", "created": 1700000000, "owned_by": "kiro"},
    {"id": "amazon-nova-pro",        "object": "model", "created": 1700000000, "owned_by": "kiro"},
    {"id": "amazon-nova-lite",       "object": "model", "created": 1700000000, "owned_by": "kiro"},
    # Generic alias — maps to kiro-cli default model selection
    {"id": "kiro",                   "object": "model", "created": 1700000000, "owned_by": "kiro"},
]


def _get_session_manager(request: Request):
    sm = getattr(request.app.state, "acp_session_manager", None)
    if sm is None:
        raise HTTPException(
            status_code=503,
            detail="ACP session manager not available. Is kiro-cli installed and logged in?"
        )
    return sm


@router.get("/v1/models")
async def list_models():
    """List available Kiro models (via ACP)."""
    return JSONResponse(content={"object": "list", "data": KIRO_MODELS})


@router.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    """Get a specific model."""
    for m in KIRO_MODELS:
        if m["id"] == model_id:
            return JSONResponse(content=m)
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions endpoint.

    Routes through ACP → kiro-cli (compliant path).
    Supports both streaming (stream=true) and non-streaming.
    """
    sm = _get_session_manager(request)
    body = await request.json()

    messages = body.get("messages", [])
    model = body.get("model", "kiro")
    stream = body.get("stream", False)

    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    # Create a fresh ACP session for each completion request.
    # ACP sessions maintain context internally, so each API call gets
    # a clean session with the full message history passed as prompt.
    try:
        proc, session_id = await sm.new_session()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create ACP session: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to create ACP session: {e}")

    logger.debug(f"ACP session {session_id} created for chat/completions (model={model}, stream={stream})")

    if stream:
        return StreamingResponse(
            openai_stream_from_acp(
                process=proc,
                session_id=session_id,
                messages=messages,
                model=model,
                request_id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    else:
        try:
            result = await openai_complete_from_acp(
                process=proc,
                session_id=session_id,
                messages=messages,
                model=model,
            )
            return JSONResponse(content=result)
        except Exception as e:
            logger.error(f"ACP completion error: {e}")
            raise HTTPException(status_code=500, detail=f"ACP completion error: {e}")


@router.get("/health")
async def health(request: Request):
    """Health check."""
    sm = getattr(request.app.state, "acp_session_manager", None)
    proc = getattr(sm, "_process", None) if sm else None
    alive = proc is not None and proc.is_alive
    return {
        "status": "ok" if alive else "starting",
        "mode": "ACP-compliant (kiro-cli)",
        "kiro_cli_alive": alive,
    }
