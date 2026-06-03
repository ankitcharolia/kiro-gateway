"""Convert between internal and OpenAI wire formats."""
from __future__ import annotations
import json
import time
from typing import Any

from kiro.converters_core import normalise_content


def acp_response_to_openai(
    acp_resp: dict[str, Any],
    model: str,
    request_id: str,
) -> dict[str, Any]:
    content = acp_resp.get("content") or ""
    tool_calls = acp_resp.get("tool_calls") or []
    finish_reason = acp_resp.get("finish_reason") or "stop"

    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls

    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {"index": 0, "message": message, "finish_reason": finish_reason}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def openai_messages_to_acp(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for msg in messages:
        result.append({
            "role": msg.get("role", "user"),
            "content": normalise_content(msg.get("content")),
        })
    return result
