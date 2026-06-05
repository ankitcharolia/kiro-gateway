"""Shared conversion helpers used by both OpenAI and Anthropic converters."""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from .acp_models import (
    ACPRequest,
    ACPMessage,
    ACPTool,
    ACPToolCall,
    ACPToolResult,
    ACPContentBlock,
    ACPTextBlock,
    ACPToolUseBlock,
    ACPThinkingBlock,
    ACPImageBlock,
)


# ---------------------------------------------------------------------------
# Role mapping
# ---------------------------------------------------------------------------

OPENAI_TO_ACP_ROLE: Dict[str, str] = {
    "system": "system",
    "user": "user",
    "assistant": "assistant",
    "tool": "tool",
    "function": "tool",
}

ANTHROPIC_TO_ACP_ROLE: Dict[str, str] = {
    "user": "user",
    "assistant": "assistant",
}


def map_role(role: str, mapping: Dict[str, str]) -> str:
    return mapping.get(role, role)


# ---------------------------------------------------------------------------
# Content normalisation
# ---------------------------------------------------------------------------

def normalise_content(content: Any) -> List[ACPContentBlock]:
    """Convert any incoming content shape into a list of ACPContentBlock."""
    if content is None:
        return []
    if isinstance(content, str):
        return [ACPTextBlock(type="text", text=content)]
    if isinstance(content, list):
        blocks: List[ACPContentBlock] = []
        for part in content:
            if isinstance(part, dict):
                blocks.extend(_dict_part_to_blocks(part))
            else:
                t = getattr(part, "type", None)
                if t == "text":
                    blocks.append(ACPTextBlock(type="text", text=getattr(part, "text", "")))
                elif t == "image_url":
                    url = getattr(getattr(part, "image_url", None), "url", "")
                    blocks.append(ACPImageBlock(type="image", source={"type": "url", "url": url}))
                elif t == "tool_result":
                    tool_use_id = getattr(part, "tool_use_id", "")
                    result_content = getattr(part, "content", "")
                    if isinstance(result_content, list):
                        result_content = " ".join(
                            getattr(c, "text", str(c)) for c in result_content
                        )
                    blocks.append(
                        ACPToolResult(
                            type="tool_result",
                            tool_use_id=tool_use_id,
                            content=result_content or "",
                        )
                    )
                else:
                    blocks.append(ACPTextBlock(type="text", text=str(part)))
        return blocks
    return [ACPTextBlock(type="text", text=str(content))]


def _dict_part_to_blocks(part: Dict[str, Any]) -> List[ACPContentBlock]:
    t = part.get("type", "text")
    if t == "text":
        return [ACPTextBlock(type="text", text=part.get("text", ""))]
    if t == "image_url":
        url = (part.get("image_url") or {}).get("url", "")
        return [ACPImageBlock(type="image", source={"type": "url", "url": url})]
    if t == "tool_result":
        content = part.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", str(c)) for c in content)
        return [ACPToolResult(type="tool_result", tool_use_id=part.get("tool_use_id", ""), content=content)]
    if t == "tool_use":
        return [
            ACPToolUseBlock(
                type="tool_use",
                id=part.get("id", str(uuid.uuid4())),
                name=part.get("name", ""),
                input=part.get("input", {}),
            )
        ]
    return [ACPTextBlock(type="text", text=str(part))]


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def convert_tools(tools: Optional[List[Any]]) -> Optional[List[ACPTool]]:
    if not tools:
        return None
    result = []
    for t in tools:
        if isinstance(t, dict):
            fn = t.get("function", t)
            result.append(
                ACPTool(
                    name=fn.get("name", ""),
                    description=fn.get("description"),
                    input_schema=fn.get("parameters") or fn.get("input_schema") or {},
                )
            )
        else:
            fn = getattr(t, "function", t)
            result.append(
                ACPTool(
                    name=getattr(fn, "name", ""),
                    description=getattr(fn, "description", None),
                    input_schema=getattr(fn, "parameters", None)
                    or getattr(fn, "input_schema", {})
                    or {},
                )
            )
    return result or None


# ---------------------------------------------------------------------------
# Thinking-block extraction
# ---------------------------------------------------------------------------

def extract_thinking(
    blocks: List[ACPContentBlock],
) -> Tuple[Optional[str], List[ACPContentBlock]]:
    """Split thinking blocks from other content blocks."""
    thinking_parts: List[str] = []
    rest: List[ACPContentBlock] = []
    for b in blocks:
        if getattr(b, "type", None) == "thinking":
            thinking_parts.append(getattr(b, "thinking", ""))
        else:
            rest.append(b)
    return "\n".join(thinking_parts) or None, rest


# ---------------------------------------------------------------------------
# Response ID / timestamp helpers
# ---------------------------------------------------------------------------

def new_response_id(prefix: str = "chatcmpl") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def now_ts() -> int:
    return int(time.time())
