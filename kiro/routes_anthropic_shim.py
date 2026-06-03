# -*- coding: utf-8 -*-
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["Anthropic Shim"])


class AnthropicMessage(BaseModel):
    role: str
    content: Any


class AnthropicMessagesRequest(BaseModel):
    model: str
    messages: list[AnthropicMessage] = Field(default_factory=list)
    max_tokens: int = 4096
    stream: bool = False


@router.post("/v1/messages")
async def messages(body: AnthropicMessagesRequest, request: Request):
    shim = request.app.state.shim_service
    prompt_text = "\n".join(
        [m.content if isinstance(m.content, str) else str(m.content) for m in body.messages]
    ).strip()
    result = await shim.run_prompt(prompt_text)
    return {
        "id": f"msg_{result['session_id']}",
        "type": "message",
        "role": "assistant",
        "model": body.model,
        "content": [{"type": "text", "text": result["text"] or ""}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "acp": {
            "session_id": result["session_id"],
            "stop": result["stop"],
            "tool_events": result["tool_events"],
        },
    }
