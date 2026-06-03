"""MCP (Model Context Protocol) tool helpers."""
from __future__ import annotations
from typing import Any


MCP_TOOL_NAMES: frozenset[str] = frozenset({
    "read_file",
    "write_to_file",
    "list_directory",
    "search_files",
    "execute_command",
    "web_search",
    "browser_action",
})


def is_mcp_tool(tool_name: str) -> bool:
    return tool_name in MCP_TOOL_NAMES


def build_mcp_tool_result(
    tool_use_id: str,
    content: Any,
    is_error: bool = False,
) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }
