"""Convert between OpenAI-compatible API shapes and ACP / Kiro messages."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from .acp_models import (
    ACPRequest,
    ACPMessage,
    ACPResponse,
    ACPTextBlock,
    ACPToolUseBlock,
    ACPToolResult,
    ACPThinkingBlock,
)
from .converters_core import (
    OPENAI_TO_ACP_ROLE,
    map_role,
    normalise_content,
    convert_tools,
    extract_thinking,
    new_response_id,
    now_ts,
    UnifiedMessage,
    UnifiedTool,
)
from .models_openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionUsage,
    Message,
    FunctionCall,
    ToolCall,
    ChatMessage,
    Tool,
)

import logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Image extraction helpers
# ---------------------------------------------------------------------------

def _extract_images_from_tool_message(content) -> List[Dict[str, str]]:
    """Extract base64 images from a tool message content list."""
    images: List[Dict[str, str]] = []
    if not isinstance(content, list):
        return images
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image_url":
            url = (block.get("image_url") or {}).get("url", "")
            # data:image/<type>;base64,<data>
            m = re.match(r"data:(image/[^;]+);base64,(.+)", url)
            if m:
                images.append({"media_type": m.group(1), "data": m.group(2)})
    return images


def _extract_text_from_content(content) -> str:
    """Extract plain text from a content value (str or list of blocks)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# convert_openai_messages_to_unified
# ---------------------------------------------------------------------------

def convert_openai_messages_to_unified(
    messages: List[ChatMessage],
) -> Tuple[Optional[str], List[UnifiedMessage]]:
    """Convert a list of OpenAI ChatMessage objects to unified format.

    Returns:
        (system_prompt, unified_messages)
    """
    system_parts: List[str] = []
    unified: List[UnifiedMessage] = []

    i = 0
    while i < len(messages):
        msg = messages[i]
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", None)

        # ── system ──────────────────────────────────────────────────────────
        if role == "system":
            text = _extract_text_from_content(content)
            if text:
                system_parts.append(text)
            i += 1
            continue

        # ── tool results ─────────────────────────────────────────────────────
        # Collect consecutive tool messages into a single user message with
        # tool_results so the unified format matches Kiro's expectations.
        if role == "tool":
            tool_results = []
            while i < len(messages) and getattr(messages[i], "role", None) == "tool":
                m = messages[i]
                tc_id = getattr(m, "tool_call_id", None) or ""
                raw_content = getattr(m, "content", "")
                text_content = _extract_text_from_content(raw_content) or "(empty result)"
                # Also collect any images embedded in tool content
                images = _extract_images_from_tool_message(
                    raw_content if isinstance(raw_content, list) else []
                )
                tool_results.append({
                    "tool_use_id": tc_id,
                    "content": text_content,
                    **({"images": images} if images else {}),
                })
                i += 1
            unified.append(
                UnifiedMessage(role="user", content=None, tool_results=tool_results)
            )
            continue

        # ── user ─────────────────────────────────────────────────────────────
        if role == "user":
            text = _extract_text_from_content(content)
            images = _extract_images_from_tool_message(
                content if isinstance(content, list) else []
            ) if role == "user" else None
            unified.append(
                UnifiedMessage(
                    role="user",
                    content=text or None,
                    images=images if images else None,
                )
            )
            i += 1
            continue

        # ── assistant ────────────────────────────────────────────────────────
        if role == "assistant":
            text = _extract_text_from_content(content)
            tool_calls_raw = getattr(msg, "tool_calls", None)
            tool_calls = None
            if tool_calls_raw:
                tool_calls = []
                for tc in tool_calls_raw:
                    if isinstance(tc, dict):
                        tool_calls.append(tc)
                    else:
                        tool_calls.append({
                            "id": getattr(tc, "id", str(uuid.uuid4())),
                            "type": getattr(tc, "type", "function"),
                            "function": {
                                "name": getattr(getattr(tc, "function", tc), "name", ""),
                                "arguments": getattr(getattr(tc, "function", tc), "arguments", "{}"),
                            },
                        })
            unified.append(
                UnifiedMessage(
                    role="assistant",
                    content=text or None,
                    tool_calls=tool_calls,
                )
            )
            i += 1
            continue

        # ── fallback ─────────────────────────────────────────────────────────
        text = _extract_text_from_content(content)
        unified.append(UnifiedMessage(role=role, content=text or None))
        i += 1

    system_prompt = "\n".join(system_parts) if system_parts else None

    tool_calls_count = sum(1 for m in unified if m.tool_calls)
    tool_results_count = sum(1 for m in unified if m.tool_results)
    images_count = sum(len(m.images) for m in unified if m.images)
    logger.debug(
        "Converted %d OpenAI messages: %d tool_calls, %d tool_results, %d images",
        len(unified),
        tool_calls_count,
        tool_results_count,
        images_count,
    )

    return system_prompt, unified


# ---------------------------------------------------------------------------
# convert_openai_tools_to_unified
# ---------------------------------------------------------------------------

def convert_openai_tools_to_unified(
    tools: Optional[List[Tool]],
) -> Optional[List[UnifiedTool]]:
    """Convert OpenAI Tool objects to UnifiedTool list.

    Supports both standard OpenAI nested format (tool.function) and Cursor IDE
    flat format (tool.name / tool.input_schema directly on the Tool object).
    """
    if not tools:
        return None

    result: List[UnifiedTool] = []
    for tool in tools:
        if getattr(tool, "type", None) != "function":
            continue

        fn = getattr(tool, "function", None)

        if fn is not None:
            # Standard OpenAI format: { type: "function", function: { name, description, parameters } }
            name = getattr(fn, "name", None)
            description = getattr(fn, "description", "") or ""
            schema = getattr(fn, "parameters", None) or {}
        else:
            # Cursor flat format: { type: "function", name, description, input_schema }
            name = getattr(tool, "name", None)
            description = getattr(tool, "description", "") or ""
            schema = getattr(tool, "input_schema", None) or {}

        if not name:
            logger.debug("Skipping tool with no name: %s", tool)
            continue

        result.append(UnifiedTool(name=name, description=description, input_schema=schema))

    return result if result else None


# ---------------------------------------------------------------------------
# Thinking / reasoning helpers
# ---------------------------------------------------------------------------

def reasoning_effort_to_budget(effort: Optional[str]) -> Optional[int]:
    """Map OpenAI reasoning_effort string to a token budget integer."""
    if effort is None:
        return None
    mapping = {"low": 1024, "medium": 8192, "high": 32768}
    return mapping.get(effort.lower())


def extract_thinking_config_from_openai(
    req: ChatCompletionRequest,
) -> Optional[Dict[str, Any]]:
    """Extract an Anthropic-style thinking config dict from an OpenAI request.

    Checks both ``req.thinking`` (explicit) and ``req.reasoning_effort``
    (OpenAI o-series style).
    """
    if getattr(req, "thinking", None):
        return req.thinking
    effort = getattr(req, "reasoning_effort", None)
    if effort:
        budget = reasoning_effort_to_budget(effort)
        if budget:
            return {"type": "enabled", "budget_tokens": budget}
    return None


# ---------------------------------------------------------------------------
# OpenAI request -> ACP request  (original path, kept for compatibility)
# ---------------------------------------------------------------------------

def openai_request_to_acp(req: ChatCompletionRequest) -> ACPRequest:
    """Convert an OpenAI ChatCompletionRequest into an ACPRequest."""
    acp_messages: List[ACPMessage] = []
    system_text: Optional[str] = None

    for msg in req.messages:
        role = msg.role if hasattr(msg, "role") else msg["role"]
        content = getattr(msg, "content", None)
        tool_calls = getattr(msg, "tool_calls", None)
        tool_call_id = getattr(msg, "tool_call_id", None)

        if role == "system":
            if isinstance(content, str):
                system_text = (system_text + "\n" + content) if system_text else content
            continue

        blocks = normalise_content(content)

        if tool_calls:
            for tc in tool_calls:
                tc_id = getattr(tc, "id", str(uuid.uuid4()))
                fn = getattr(tc, "function", tc)
                name = getattr(fn, "name", "")
                try:
                    args = json.loads(getattr(fn, "arguments", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                blocks.append(ACPToolUseBlock(type="tool_use", id=tc_id, name=name, input=args))

        if role == "tool" and tool_call_id:
            text = content if isinstance(content, str) else json.dumps(content)
            blocks = [ACPToolResult(type="tool_result", tool_use_id=tool_call_id, content=text)]

        acp_messages.append(
            ACPMessage(
                role=map_role(role, OPENAI_TO_ACP_ROLE),
                content=blocks,
            )
        )

    thinking = extract_thinking_config_from_openai(req)

    return ACPRequest(
        model=req.model,
        messages=acp_messages,
        system=system_text,
        max_tokens=req.max_tokens or 4096,
        temperature=req.temperature,
        top_p=req.top_p,
        stream=req.stream or False,
        tools=convert_tools(req.tools),
        stop_sequences=([req.stop] if isinstance(req.stop, str) else req.stop) if req.stop else None,
        thinking=thinking,
    )


# ---------------------------------------------------------------------------
# ACP response -> OpenAI response
# ---------------------------------------------------------------------------

def acp_response_to_openai(
    acp_resp: ACPResponse,
    model: str,
    request_id: Optional[str] = None,
) -> ChatCompletionResponse:
    rid = request_id or new_response_id()
    content_parts: List[str] = []
    tool_calls: List[ToolCall] = []

    for block in (acp_resp.content or []):
        btype = getattr(block, "type", None)
        if btype == "text":
            content_parts.append(getattr(block, "text", ""))
        elif btype == "tool_use":
            tc_id = getattr(block, "id", str(uuid.uuid4()))
            name = getattr(block, "name", "")
            args = getattr(block, "input", {})
            tool_calls.append(
                ToolCall(
                    id=tc_id,
                    type="function",
                    function=FunctionCall(
                        name=name,
                        arguments=json.dumps(args) if isinstance(args, dict) else str(args),
                    ),
                )
            )

    text_content: Optional[str] = "".join(content_parts) or None
    stop_reason = getattr(acp_resp, "stop_reason", None)
    finish_reason = _map_stop_reason_to_openai(stop_reason)

    usage = getattr(acp_resp, "usage", None)
    oai_usage = None
    if usage:
        oai_usage = ChatCompletionUsage(
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            total_tokens=getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0),
        )

    return ChatCompletionResponse(
        id=rid,
        object="chat.completion",
        created=now_ts(),
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=Message(
                    role="assistant",
                    content=text_content,
                    tool_calls=tool_calls or None,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=oai_usage,
    )


def build_kiro_payload(
    req: ChatCompletionRequest,
    conversation_id: str,
    profile_arn: str,
) -> Dict[str, Any]:
    """Convert an OpenAI ChatCompletionRequest to a Kiro API payload dict."""
    from .converters_core import build_kiro_payload as _core_build  # lazy import
    acp_req = openai_request_to_acp(req)
    return _core_build(acp_req, conversation_id, profile_arn)


def _map_stop_reason_to_openai(stop_reason: Optional[str]) -> str:
    mapping = {
        "end_turn": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
        "stop_sequence": "stop",
    }
    return mapping.get(stop_reason or "", "stop")
