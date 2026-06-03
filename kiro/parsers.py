"""Response body parsers for ACP / Kiro backend messages."""
from __future__ import annotations
import json
from typing import Any


def parse_json_safe(raw: str | bytes) -> Any:
    """Parse JSON without raising; returns None on failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def extract_text_content(blocks: list[dict[str, Any]]) -> str:
    """Concatenate all text blocks from an Anthropic content list."""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def extract_tool_calls(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract tool_use blocks and normalise to OpenAI tool_call format."""
    result: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            result.append({
                "id": block.get("id", ""),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                },
            })
    return result
