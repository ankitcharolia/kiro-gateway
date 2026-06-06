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
# Unified message / tool types (used by tests)
# ---------------------------------------------------------------------------

class UnifiedMessage:
    """Simple container representing a normalised message."""
    __slots__ = ("role", "content", "tool_calls", "tool_call_id", "name")

    def __init__(
        self,
        role: str,
        content: Any = None,
        tool_calls: Optional[List[Any]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        self.role = role
        self.content = content
        self.tool_calls = tool_calls or []
        self.tool_call_id = tool_call_id
        self.name = name


class UnifiedTool:
    """Simple container representing a normalised tool definition."""
    __slots__ = ("name", "description", "parameters")

    def __init__(self, name: str, description: Optional[str] = None, parameters: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {}


class ThinkingConfig:
    """Simple container for thinking configuration."""
    __slots__ = ("enabled", "budget_tokens")

    def __init__(self, enabled: bool = True, budget_tokens: int = 10_000) -> None:
        self.enabled = enabled
        self.budget_tokens = budget_tokens


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_content(content: Any) -> str:
    """Extract plain text from any content shape.

    Handles: str, None, list of dicts/strings/Pydantic models.
    Skips tool_use, tool_result, tool_reference, image blocks.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("type", "text")
                if t in ("tool_use", "tool_result", "tool_reference", "image", "image_url"):
                    continue
                parts.append(item.get("text", ""))
            else:
                # Pydantic model or object
                t = getattr(item, "type", "text")
                if t in ("tool_use", "tool_result", "tool_reference", "image"):
                    continue
                text = getattr(item, "text", None)
                if text is not None:
                    parts.append(text)
        return "".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# Image extraction helpers (Issue #30 fix)
# ---------------------------------------------------------------------------

def extract_images_from_content(content: Any) -> List[Dict[str, Any]]:
    """Extract image blocks from content, returning list of {media_type, data} dicts."""
    images: List[Dict[str, Any]] = []
    if not isinstance(content, list):
        return images
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type", "")
        if t == "image_url":
            url = (item.get("image_url") or {}).get("url", "")
            if url.startswith("data:"):
                header, data = url.split(",", 1)
                media_type = header.split(";")[0].replace("data:", "")
                images.append({"media_type": media_type, "data": data})
        elif t == "image":
            source = item.get("source") or {}
            if source.get("type") == "base64":
                images.append({"media_type": source.get("media_type", ""), "data": source.get("data", "")})
    return images


def convert_images_to_kiro_format(images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert extracted images to Kiro ACP image block format."""
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["data"],
            },
        }
        for img in images
    ]


# ---------------------------------------------------------------------------
# Message normalisation helpers
# ---------------------------------------------------------------------------

def merge_adjacent_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge consecutive messages with the same role."""
    if not messages:
        return []
    merged: List[Dict[str, Any]] = [dict(messages[0])]
    for msg in messages[1:]:
        if msg.get("role") == merged[-1].get("role"):
            prev = merged[-1]
            prev_content = prev.get("content", "")
            cur_content = msg.get("content", "")
            if isinstance(prev_content, str) and isinstance(cur_content, str):
                prev["content"] = prev_content + "\n" + cur_content
            elif isinstance(prev_content, list) and isinstance(cur_content, list):
                prev["content"] = prev_content + cur_content
            else:
                merged.append(dict(msg))
        else:
            merged.append(dict(msg))
    return merged


def ensure_first_message_is_user(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure the first message is a user message."""
    if not messages:
        return messages
    while messages and messages[0].get("role") != "user":
        messages = messages[1:]
    return messages


def normalize_message_roles(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise role names (function -> tool, etc.)."""
    result = []
    for msg in messages:
        m = dict(msg)
        if m.get("role") == "function":
            m["role"] = "tool"
        result.append(m)
    return result


def ensure_alternating_roles(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure messages alternate between user and assistant."""
    return merge_adjacent_messages(messages)


def ensure_assistant_before_tool_results(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Insert a placeholder assistant message before orphaned tool results."""
    result: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "tool" and (not result or result[-1].get("role") != "assistant"):
            result.append({"role": "assistant", "content": ""})
        result.append(msg)
    return result


def strip_all_tool_content(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove all tool_use and tool_result content blocks from messages."""
    result = []
    for msg in messages:
        m = dict(msg)
        content = m.get("content")
        if isinstance(content, list):
            m["content"] = [
                b for b in content
                if not (isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result"))
            ]
        result.append(m)
    return result


def build_kiro_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build Kiro-compatible message history from incoming messages."""
    msgs = normalize_message_roles(messages)
    msgs = ensure_first_message_is_user(msgs)
    msgs = ensure_assistant_before_tool_results(msgs)
    msgs = merge_adjacent_messages(msgs)
    return msgs


def build_kiro_payload(
    messages: List[Dict[str, Any]],
    model: str,
    max_tokens: int = 4096,
    system: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    temperature: Optional[float] = None,
    stream: bool = False,
) -> Dict[str, Any]:
    """Build a complete Kiro ACP request payload dict."""
    payload: Dict[str, Any] = {
        "model": model,
        "messages": build_kiro_history(messages),
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = tools
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


# ---------------------------------------------------------------------------
# Tool helpers
# ---------------------------------------------------------------------------

def process_tools_with_long_descriptions(
    tools: Optional[List[Any]],
    max_description_length: int = 1024,
) -> Optional[List[Any]]:
    """Truncate overly long tool descriptions."""
    if not tools:
        return tools
    result = []
    for t in tools:
        if isinstance(t, dict):
            tool = dict(t)
            fn = tool.get("function", {})
            if isinstance(fn, dict) and len(fn.get("description", "")) > max_description_length:
                fn = dict(fn)
                fn["description"] = fn["description"][:max_description_length] + "..."
                tool["function"] = fn
            result.append(tool)
        else:
            result.append(t)
    return result


def inject_thinking_tags(content: str, budget_tokens: int = 10_000) -> str:
    """Wrap content with thinking budget XML tags."""
    return f"<thinking>\n{content}\n</thinking>"


def extract_tool_results_from_content(content: Any) -> List[Dict[str, Any]]:
    """Extract tool_result blocks from content."""
    if not isinstance(content, list):
        return []
    return [
        b for b in content
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]


def extract_tool_uses_from_message(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool_use blocks from a message."""
    content = message.get("content", [])
    if not isinstance(content, list):
        return []
    return [
        b for b in content
        if isinstance(b, dict) and b.get("type") == "tool_use"
    ]


def sanitize_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Remove unsupported JSON Schema keys for Kiro tool input schemas."""
    UNSUPPORTED = {"exclusiveMinimum", "exclusiveMaximum", "$schema", "$id", "definitions"}
    if not isinstance(schema, dict):
        return schema
    return {
        k: sanitize_json_schema(v) if isinstance(v, dict) else v
        for k, v in schema.items()
        if k not in UNSUPPORTED
    }


def convert_tools_to_kiro_format(tools: Optional[List[Any]]) -> Optional[List[Dict[str, Any]]]:
    """Convert OpenAI/Anthropic tool definitions to Kiro ACP format."""
    return convert_tools(tools) and [
        {
            "name": getattr(t, "name", t.get("name", "") if isinstance(t, dict) else ""),
            "description": getattr(t, "description", t.get("description") if isinstance(t, dict) else None),
            "input_schema": getattr(t, "input_schema", t.get("input_schema", {}) if isinstance(t, dict) else {}),
        }
        for t in (convert_tools(tools) or [])
    ]


def convert_tool_results_to_kiro_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert tool result messages to Kiro ACP format."""
    return messages


def tool_calls_to_text(tool_calls: List[Any]) -> str:
    """Render tool calls as readable text for models that don't support tools."""
    import json as _json
    parts = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            fn = tc.get("function", {})
            name = fn.get("name", "unknown")
            args = fn.get("arguments", "{}")
        else:
            fn = getattr(tc, "function", tc)
            name = getattr(fn, "name", "unknown")
            args = getattr(fn, "arguments", "{}")
        parts.append(f"[Tool: {name}] {args}")
    return "\n".join(parts)


def tool_results_to_text(messages: List[Dict[str, Any]]) -> str:
    """Render tool result messages as readable text."""
    parts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    parts.append(f"[Result] {b.get('content', '')}")
        elif isinstance(content, str):
            parts.append(content)
    return "\n".join(parts)


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
