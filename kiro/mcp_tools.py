"""MCP (Model Context Protocol) tool call helpers."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx


class MCPToolError(Exception):
    """Raised when an MCP tool call fails."""
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        self.status_code = status_code
        super().__init__(message)


def build_tool_call_payload(
    tool_name: str,
    tool_input: Dict[str, Any],
    call_id: Optional[str] = None,
) -> Dict[str, Any]:
    import secrets
    return {
        "id": call_id or f"call_{secrets.token_hex(8)}",
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
