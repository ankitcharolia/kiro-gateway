# -*- coding: utf-8 -*-
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["OpenAI Shim"])


class OpenAIMessage(BaseModel):
    role: str
    content: Any


class OpenAIChatRequest(BaseModel):
    model: str
    messages: list[OpenAIMessage] = Field(default_factory=list)
    stream: bool = False


@router.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "kiro-acp", "object": "model", "owned_by": "kiro"},
            {"id": "kiro-acp-agent", "object": "model", "owned_by": "kiro"},
        ],
    }


@router.post("/v1/chat/completions")
async def chat_completions(body: OpenAIChatRequest, request: Request):
    shim = request.app.state.shim_service
    prompt_text = "\n".join(
        [m.content if isinstance(m.content, str) else str(m.content) for m in body.messages]
    ).strip()
    result = await shim.run_prompt(prompt_text)
    return {
        "id": f"chatcmpl-{result['session_id']}",
        "object": "chat.completion",
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": result["text"] or "",
                },
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "acp": {
            "session_id": result["session_id"],
            "stop": result["stop"],
            "tool_events": result["tool_events"],
        },
    }
