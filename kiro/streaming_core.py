"""Shared streaming utilities for both OpenAI and Anthropic SSE paths."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional


def sse_encode(data: Any, event: Optional[str] = None) -> str:
    """Encode a dict or string as an SSE frame."""
    if data == "[DONE]":
        return "data: [DONE]\n\n"
    payload = json.dumps(data) if not isinstance(data, str) else data
    if event:
        return f"event: {event}\ndata: {payload}\n\n"
    return f"data: {payload}\n\n"


def chunk_to_dict(chunk: Any) -> Dict[str, Any]:
    if hasattr(chunk, "model_dump"):
        return chunk.model_dump(exclude_none=True)
    if hasattr(chunk, "dict"):
        return chunk.dict(exclude_none=True)
    if isinstance(chunk, dict):
        return chunk
    return {"data": str(chunk)}


# ---------------------------------------------------------------------------
# ACP event type predicates
# ---------------------------------------------------------------------------

def is_text_delta(event: Dict[str, Any]) -> bool:
    return event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta"

def is_thinking_delta(event: Dict[str, Any]) -> bool:
    return event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "thinking_delta"

def is_tool_delta(event: Dict[str, Any]) -> bool:
    return event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "input_json_delta"

def is_content_block_start(event: Dict[str, Any]) -> bool:
    return event.get("type") == "content_block_start"

def is_content_block_stop(event: Dict[str, Any]) -> bool:
    return event.get("type") == "content_block_stop"

def is_message_start(event: Dict[str, Any]) -> bool:
    return event.get("type") == "message_start"

def is_message_delta(event: Dict[str, Any]) -> bool:
    return event.get("type") == "message_delta"

def is_message_stop(event: Dict[str, Any]) -> bool:
    return event.get("type") == "message_stop"


# ---------------------------------------------------------------------------
# Delta extractors
# ---------------------------------------------------------------------------

def extract_text_delta(event: Dict[str, Any]) -> str:
    return event.get("delta", {}).get("text", "")

def extract_thinking_delta(event: Dict[str, Any]) -> str:
    return event.get("delta", {}).get("thinking", "")

def extract_tool_delta(event: Dict[str, Any]) -> str:
    return event.get("delta", {}).get("partial_json", "")

def extract_stop_reason(event: Dict[str, Any]) -> Optional[str]:
    return event.get("delta", {}).get("stop_reason")

def extract_usage(event: Dict[str, Any]) -> Optional[Dict[str, int]]:
    return event.get("usage")
