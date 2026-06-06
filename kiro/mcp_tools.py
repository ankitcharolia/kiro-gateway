"""MCP (Model Context Protocol) tool call helpers."""
from __future__ import annotations

import json
import secrets
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx


class MCPToolError(Exception):
    """Raised when an MCP tool call fails."""
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        self.status_code = status_code
        super().__init__(message)


def generate_random_id(prefix: str = "id") -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def build_tool_call_payload(
    tool_name: str,
    tool_input: Dict[str, Any],
    call_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": call_id or generate_random_id("call"),
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(tool_input),
        },
    }


def format_tool_result(
    tool_use_id: str,
    result: Any,
    is_error: bool = False,
) -> Dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result if isinstance(result, str) else json.dumps(result),
                "is_error": is_error,
            }
        ],
    }


def extract_query_from_messages(messages: List[Dict[str, Any]]) -> str:
    """Extract the last user message text as the search query."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
    return ""


async def call_mcp_tool(
    endpoint: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
) -> Any:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            endpoint,
            json={"name": tool_name, "input": tool_input},
            headers=headers or {},
        )
        if resp.status_code >= 400:
            raise MCPToolError(
                f"MCP tool call failed: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json()


async def call_kiro_mcp_api(
    endpoint: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    auth_token: Optional[str] = None,
    timeout: float = 30.0,
) -> Any:
    headers: Dict[str, str] = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    return await call_mcp_tool(endpoint, tool_name, tool_input, headers, timeout)


def list_mcp_tools(
    tools: List[Dict[str, Any]],
) -> List[str]:
    return [t.get("name", "") for t in tools if t.get("name")]


def generate_search_summary(
    results: List[Dict[str, Any]],
    max_results: int = 5,
) -> str:
    if not results:
        return "No results found."
    lines: List[str] = []
    for i, r in enumerate(results[:max_results], 1):
        if isinstance(r, dict):
            title = r.get("title") or r.get("name") or "(untitled)"
            snippet = r.get("snippet") or r.get("description") or ""
            url = r.get("url") or r.get("link") or ""
            parts = [f"{i}. {title}"]
            if snippet:
                parts.append(f"   {snippet}")
            if url:
                parts.append(f"   {url}")
            lines.append("\n".join(parts))
        else:
            lines.append(f"{i}. {r}")
    return "\n\n".join(lines)


async def handle_native_web_search(
    query: str,
    endpoint: str,
    auth_token: Optional[str] = None,
    max_results: int = 5,
    timeout: float = 30.0,
) -> str:
    """Call a native web-search MCP tool and return a formatted summary."""
    try:
        results = await call_kiro_mcp_api(
            endpoint=endpoint,
            tool_name="web_search",
            tool_input={"query": query, "max_results": max_results},
            auth_token=auth_token,
            timeout=timeout,
        )
        items: List[Dict[str, Any]] = []
        if isinstance(results, list):
            items = results
        elif isinstance(results, dict):
            items = results.get("results", results.get("items", []))
        return generate_search_summary(items, max_results=max_results)
    except MCPToolError as exc:
        return f"Web search failed: {exc}"


async def generate_anthropic_web_search_sse(
    query: str,
    endpoint: str,
    auth_token: Optional[str] = None,
    max_results: int = 5,
    timeout: float = 30.0,
) -> AsyncIterator[str]:
    """Yield Anthropic-compatible SSE lines for a web search result."""
    import json as _json

    summary = await handle_native_web_search(
        query=query,
        endpoint=endpoint,
        auth_token=auth_token,
        max_results=max_results,
        timeout=timeout,
    )

    # Yield a minimal Anthropic streaming SSE sequence
    events = [
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                   "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                   "delta": {"type": "text_delta", "text": summary}}),
        ("content_block_stop",  {"type": "content_block_stop", "index": 0}),
        ("message_stop",        {"type": "message_stop"}),
    ]
    for event_type, data in events:
        yield f"event: {event_type}\ndata: {_json.dumps(data)}\n\n"
