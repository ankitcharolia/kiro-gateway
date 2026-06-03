"""Convert between internal and Anthropic wire formats."""
from __future__ import annotations
import json
import time
from typing import Any

from kiro.converters_core import normalise_content


def anthropic_messages_to_acp(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text") or "")
            content = "".join(parts)
        result.append({"role": role, "content": content})
    return result


def acp_response_to_anthropic(
    acp_resp: dict[str, Any],
    model: str,
    message_id: str,
) -> dict[str, Any]:
    content_text = acp_resp.get("content") or ""
    tool_calls = acp_resp.get("tool_calls") or []
    stop_reason = acp_resp.get("finish_reason") or "end_turn"

    content_blocks: list[dict[str, Any]] = [{"type": "text", "text": content_text}]
    for tc in tool_calls:
        fn = tc.get("function", {})
        try:
            inp = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            inp = {}
        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "input": inp,
        })

    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
