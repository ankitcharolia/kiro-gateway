# -*- coding: utf-8 -*-
"""
Anthropic-compatible routes backed by ACP (kiro-cli).

Replaces direct-API Anthropic routes with ACP-compliant versions:
  POST /v1/messages  →  ACP session/prompt via kiro-cli

This makes Claude Code, Cursor (Anthropic mode), and similar tools
work through the approved ACP→kiro-cli pathway.
"""

import uuid
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger

from kiro.acp_openai_bridge import anthropic_stream_from_acp, anthropic_complete_from_acp

router = APIRouter(tags=["Anthropic Compatible (ACP)"])


def _get_session_manager(request: Request):
    sm = getattr(request.app.state, "acp_session_manager", None)
    if sm is None:
        raise HTTPException(
            status_code=503,
            detail="ACP session manager not available. Is kiro-cli installed and logged in?"
        )
    return sm


@router.post("/v1/messages")
async def anthropic_messages(request: Request):
    """
    Anthropic-compatible messages endpoint.

    Routes through ACP → kiro-cli (compliant path).
    Supports both streaming (stream=true) and non-streaming.
    """
    sm = _get_session_manager(request)
    body = await request.json()

    messages = body.get("messages", [])
    model = body.get("model", "kiro")
    stream = body.get("stream", False)

    # Include system prompt in messages if provided
    system = body.get("system")
    if system:
        messages = [{"role": "system", "content": system}] + list(messages)

    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    try:
        proc, session_id = await sm.new_session()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create ACP session: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to create ACP session: {e}")

    logger.debug(f"ACP session {session_id} for messages (model={model}, stream={stream})")

    if stream:
        return StreamingResponse(
            anthropic_stream_from_acp(
                process=proc,
                session_id=session_id,
                messages=messages,
                model=model,
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
            result = await anthropic_complete_from_acp(
                process=proc,
                session_id=session_id,
                messages=messages,
                model=model,
            )
            return JSONResponse(content=result)
        except Exception as e:
            logger.error(f"ACP Anthropic completion error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
