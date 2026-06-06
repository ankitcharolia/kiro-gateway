"""MCP tool-call helpers, web-search utilities, and SSE emitters."""
from __future__ import annotations

import json
import secrets
import string
from typing import Any, AsyncIterator, Dict, List, Optional


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

def generate_random_id(prefix: str = "tool", length: int = 8) -> str:
    """Return a short random alphanumeric ID."""
    alphabet = string.ascii_lowercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}_{suffix}"


# ---------------------------------------------------------------------------
# Tool result builders
# ---------------------------------------------------------------------------

def build_tool_result(
    tool_use_id: str,
    content: Any,
    is_error: bool = False,
) -> Dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content if isinstance(content, str) else str(content),
        "is_error": is_error,
    }


def extract_tool_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = message.get("content", [])
    if isinstance(content, str):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


def has_tool_calls(message: Dict[str, Any]) -> bool:
    return bool(extract_tool_calls(message))


# ---------------------------------------------------------------------------
# Kiro MCP API caller (async)
# ---------------------------------------------------------------------------

async def call_kiro_mcp_api(
    session_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    http_client: Any = None,
    base_url: str = "",
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Call the Kiro MCP API for *tool_name* with *tool_input*.

    Returns the raw JSON response dict from the API, or an error dict.
    When *http_client* is None, the function returns a stub response
    (useful in testing without a live Kiro instance).
    """
    if http_client is None:
        return {"type": "tool_result", "content": "", "is_error": False}

    payload = {
        "sessionId": session_id,
        "toolName": tool_name,
        "toolInput": tool_input,
    }
    try:
        resp = await http_client.post(
            f"{base_url}/mcp/call",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"type": "tool_result", "content": str(exc), "is_error": True}


# ---------------------------------------------------------------------------
# Web-search helpers
# ---------------------------------------------------------------------------

def extract_query_from_messages(messages: List[Dict[str, Any]]) -> str:
    """Extract the most recent user query string from a message list."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
    return ""


def generate_search_summary(
    query: str,
    results: List[Dict[str, Any]],
    max_results: int = 5,
) -> str:
    """Build a human-readable summary string from web-search *results*."""
    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results[:max_results], 1):
        title = r.get("title", "(no title)")
        url = r.get("url", "")
        snippet = r.get("snippet", r.get("description", ""))
        lines.append(f"{i}. {title}")
        if url:
            lines.append(f"   URL: {url}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


async def handle_native_web_search(
    query: str,
    http_client: Any = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Perform a native web search via the Kiro MCP API.

    Returns a tool-result-shaped dict with ``content`` as a text summary.
    """
    results = await call_kiro_mcp_api(
        session_id="web_search",
        tool_name="web_search",
        tool_input={"query": query, "maxResults": max_results},
        http_client=http_client,
    )
    raw = results.get("content", [])
    if isinstance(raw, list):
        summary = generate_search_summary(query, raw, max_results)
    else:
        summary = str(raw)
    return {"type": "tool_result", "content": summary, "is_error": False}


# ---------------------------------------------------------------------------
# SSE emitters for web_search tool results
# ---------------------------------------------------------------------------

def generate_anthropic_web_search_sse(
    tool_use_id: str,
    content: str,
) -> List[str]:
    """Return a list of Anthropic-format SSE strings for a web_search result."""
    from .streaming_anthropic import format_sse_event
    events = [
        format_sse_event(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_result", "tool_use_id": tool_use_id},
            },
        ),
        format_sse_event(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": content},
            },
        ),
        format_sse_event("content_block_stop", {"type": "content_block_stop", "index": 0}),
    ]
    return events


def generate_openai_web_search_sse(
    tool_call_id: str,
    content: str,
    model: str = "claude-sonnet-4-5",
) -> List[str]:
    """Return a list of OpenAI-format SSE strings for a web_search result."""
    import time
    chunk_id = generate_random_id("chatcmpl")
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": content,
                },
                "finish_reason": None,
            }
        ],
    }
    return [f"data: {json.dumps(chunk)}\n\n"]
