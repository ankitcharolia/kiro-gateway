"""Convert between Anthropic-compatible API shapes and ACP messages."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from .acp_models import (
    ACPRequest,
    ACPMessage,
    ACPResponse,
    ACPTextBlock,
    ACPToolUseBlock,
    ACPToolResult,
    ACPThinkingBlock,
    ACPTool,
)
from .converters_core import (
    ANTHROPIC_TO_ACP_ROLE,
    map_role,
    normalise_content,
    convert_tools,
    extract_thinking,
    new_response_id,
    now_ts,
)
from .models_anthropic import (
    AnthropicRequest,
    AnthropicResponse,
    AnthropicUsage,
    TextContentBlock,
    ThinkingContentBlock,
    RedactedThinkingContentBlock,
    ToolUseContentBlock,
    ToolResultContentBlock,
)

try:
    from .models_anthropic import AnthropicMessagesRequest, AnthropicMessage, AnthropicTool, SystemContentBlock  # noqa: F401
except ImportError:
    AnthropicMessagesRequest = AnthropicRequest  # type: ignore[misc,assignment]
    AnthropicMessage = None  # type: ignore[assignment]
    AnthropicTool = None  # type: ignore[assignment]
    SystemContentBlock = None  # type: ignore[assignment]

try:
    from .converters_core import UnifiedMessage, UnifiedTool  # noqa: F401
except ImportError:
    UnifiedMessage = None  # type: ignore[assignment]
    UnifiedTool = None  # type: ignore[assignment]

try:
    from .model_resolver import get_model_id_for_kiro  # noqa: F401
except ImportError:
    def get_model_id_for_kiro(model: str) -> str:  # type: ignore[misc]
        return model

try:
    from .converters_core import build_kiro_payload as _core_build_kiro_payload  # noqa: F401
except ImportError:
    _core_build_kiro_payload = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# ThinkingConfig dataclass
# ---------------------------------------------------------------------------

@dataclass
class ThinkingConfig:
    """Resolved thinking/extended-reasoning configuration."""
    enabled: bool = True
    budget_tokens: Optional[int] = None


# ---------------------------------------------------------------------------
# Helper: extract plain text from Anthropic content
# ---------------------------------------------------------------------------

def convert_anthropic_content_to_text(
    content: Union[str, List[Any], None],
) -> str:
    """Return the concatenated plain-text from any Anthropic message content."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: List[str] = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        elif hasattr(block, "type") and block.type == "text":
            parts.append(getattr(block, "text", ""))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Helper: extract system prompt text
# ---------------------------------------------------------------------------

def extract_system_prompt(
    system: Union[str, List[Any], None],
) -> str:
    """Return the system prompt as a plain string (empty string if absent)."""
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    if not isinstance(system, list):
        return str(system)
    parts: List[str] = []
    for block in system:
        if isinstance(block, dict):
            if block.get("type") == "text":
                txt = block.get("text", "")
                if txt:
                    parts.append(txt)
        elif hasattr(block, "text"):
            txt = getattr(block, "text", "")
            if txt:
                parts.append(txt)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helper: extract tool results
# ---------------------------------------------------------------------------

def _content_to_text(content: Any) -> str:
    """Flatten any tool_result content to a plain string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "".join(texts)
    return str(content)


def extract_tool_results_from_anthropic_content(
    content: Any,
) -> List[Dict[str, Any]]:
    """Extract tool_result blocks from Anthropic message content.

    Returns a list of dicts with keys ``type``, ``tool_use_id``, ``content``.
    Empty/None content is normalised to ``"(empty result)"``.
    Image-only content is also normalised to ``"(empty result)"``.
    """
    if not isinstance(content, list):
        return []
    results: List[Dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict):
            btype = block.get("type")
            tool_use_id = block.get("tool_use_id")
        elif hasattr(block, "type"):
            btype = block.type
            tool_use_id = getattr(block, "tool_use_id", None)
        else:
            continue
        if btype != "tool_result":
            continue
        if not tool_use_id:
            continue
        raw_content = block.get("content") if isinstance(block, dict) else getattr(block, "content", None)
        # Extract only text from nested content list, skip images
        text = _content_to_text(raw_content)
        results.append({
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": text if text else "(empty result)",
        })
    return results


def extract_images_from_tool_results(
    content: Any,
) -> List[Dict[str, Any]]:
    """Extract base64 images embedded inside tool_result content blocks.

    Returns a list of dicts with keys ``media_type`` and ``data``.
    """
    if not isinstance(content, list):
        return []
    images: List[Dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict):
            btype = block.get("type")
            inner = block.get("content")
        elif hasattr(block, "type"):
            btype = block.type
            inner = getattr(block, "content", None)
        else:
            continue
        if btype != "tool_result" or not isinstance(inner, list):
            continue
        for item in inner:
            if isinstance(item, dict) and item.get("type") == "image":
                source = item.get("source", {})
                if isinstance(source, dict) and source.get("type") == "base64":
                    images.append({
                        "media_type": source.get("media_type", ""),
                        "data": source.get("data", ""),
                    })
    return images


def extract_tool_uses_from_anthropic_content(
    content: Any,
) -> List[Dict[str, Any]]:
    """Extract tool_use blocks from Anthropic message content.

    Returns a list of OpenAI-style tool-call dicts::

        [{"id": ..., "type": "function",
          "function": {"name": ..., "arguments": {...}}}]
    """
    if not isinstance(content, list):
        return []
    tool_uses: List[Dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict):
            btype = block.get("type")
            tc_id = block.get("id")
            name = block.get("name")
            inp = block.get("input", {})
        elif hasattr(block, "type"):
            btype = block.type
            tc_id = getattr(block, "id", None)
            name = getattr(block, "name", None)
            inp = getattr(block, "input", {})
        else:
            continue
        if btype != "tool_use":
            continue
        if not tc_id or not name:
            continue
        tool_uses.append({
            "id": tc_id,
            "type": "function",
            "function": {"name": name, "arguments": inp},
        })
    return tool_uses


# ---------------------------------------------------------------------------
# Helper: extract direct images from message content (not inside tool_results)
# ---------------------------------------------------------------------------

def _extract_images_from_content(content: Any) -> List[Dict[str, Any]]:
    if not isinstance(content, list):
        return []
    images: List[Dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "image":
            source = block.get("source", {})
            if isinstance(source, dict) and source.get("type") == "base64":
                images.append({
                    "media_type": source.get("media_type", ""),
                    "data": source.get("data", ""),
                })
    return images


# ---------------------------------------------------------------------------
# convert_anthropic_messages -> List[UnifiedMessage]
# ---------------------------------------------------------------------------

def convert_anthropic_messages(messages: List[Any]) -> List[Any]:
    """Convert a list of Anthropic messages to UnifiedMessage objects.

    Falls back to returning plain dicts when converters_core.UnifiedMessage is
    unavailable, so that callers that only check field access still work.
    """
    import importlib
    try:
        core = importlib.import_module(".converters_core", package="kiro")
        _UnifiedMessage = core.UnifiedMessage
    except (ImportError, AttributeError):
        _UnifiedMessage = None

    result = []
    for msg in messages:
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        content_raw = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)

        text = convert_anthropic_content_to_text(content_raw)
        tool_calls = extract_tool_uses_from_anthropic_content(content_raw)
        tool_results = extract_tool_results_from_anthropic_content(content_raw)
        images = None
        if role == "user":
            imgs = _extract_images_from_content(content_raw)
            imgs += extract_images_from_tool_results(content_raw if isinstance(content_raw, list) else [])
            images = imgs if imgs else None

        if _UnifiedMessage is not None:
            um = _UnifiedMessage(
                role=role,
                content=text,
                tool_calls=tool_calls or None,
                tool_results=tool_results or None,
                images=images,
            )
        else:
            class _UM:  # minimal stand-in
                pass
            um = _UM()
            um.role = role
            um.content = text
            um.tool_calls = tool_calls or None
            um.tool_results = tool_results or None
            um.images = images
        result.append(um)
    return result


# ---------------------------------------------------------------------------
# convert_anthropic_tools -> List[UnifiedTool] | None
# ---------------------------------------------------------------------------

def convert_anthropic_tools(tools: Optional[List[Any]]) -> Optional[List[Any]]:
    """Convert Anthropic tool definitions to UnifiedTool objects."""
    if not tools:
        return None

    import importlib
    try:
        core = importlib.import_module(".converters_core", package="kiro")
        _UnifiedTool = core.UnifiedTool
    except (ImportError, AttributeError):
        _UnifiedTool = None

    result = []
    for tool in tools:
        if isinstance(tool, dict):
            name = tool.get("name", "")
            description = tool.get("description")
            input_schema = tool.get("input_schema", {})
        else:
            name = getattr(tool, "name", "")
            description = getattr(tool, "description", None)
            input_schema = getattr(tool, "input_schema", {})

        if _UnifiedTool is not None:
            result.append(_UnifiedTool(name=name, description=description, input_schema=input_schema))
        else:
            class _UT:
                pass
            ut = _UT()
            ut.name = name
            ut.description = description
            ut.input_schema = input_schema
            result.append(ut)
    return result


# ---------------------------------------------------------------------------
# extract_thinking_config_from_anthropic
# ---------------------------------------------------------------------------

def extract_thinking_config_from_anthropic(request: Any) -> ThinkingConfig:
    """Resolve the thinking configuration from an Anthropic request.

    Returns a :class:`ThinkingConfig` with ``enabled`` and ``budget_tokens``.
    """
    thinking_raw = getattr(request, "thinking", None)
    if thinking_raw is None:
        return ThinkingConfig(enabled=True, budget_tokens=None)

    if isinstance(thinking_raw, dict):
        t_type = thinking_raw.get("type", "enabled")
        budget = thinking_raw.get("budget_tokens")
    else:
        t_type = getattr(thinking_raw, "type", "enabled")
        budget = getattr(thinking_raw, "budget_tokens", None)

    if t_type == "disabled":
        return ThinkingConfig(enabled=False, budget_tokens=None)
    if t_type == "enabled":
        return ThinkingConfig(enabled=True, budget_tokens=budget)
    # Unknown type — default to enabled without budget
    return ThinkingConfig(enabled=True, budget_tokens=None)


# ---------------------------------------------------------------------------
# anthropic_to_kiro — full conversion entry point
# ---------------------------------------------------------------------------

def anthropic_to_kiro(
    request: Any,
    conversation_id: str,
    profile_arn: str,
) -> Dict[str, Any]:
    """Convert an Anthropic Messages request to a Kiro API payload dict.

    This is a high-level wrapper that:
    1. Resolves the model ID via ``get_model_id_for_kiro``
    2. Converts tools, messages, system prompt, and thinking config
    3. Delegates to ``converters_core.build_kiro_payload``
    """
    import importlib
    core = importlib.import_module(".converters_core", package="kiro")

    model_id = get_model_id_for_kiro(getattr(request, "model", ""))
    messages = convert_anthropic_messages(getattr(request, "messages", []))
    tools = convert_anthropic_tools(getattr(request, "tools", None))
    system = extract_system_prompt(getattr(request, "system", None)) or None
    thinking_cfg = extract_thinking_config_from_anthropic(request)

    return core.build_kiro_payload(
        messages=messages,
        model=model_id,
        conversation_id=conversation_id,
        profile_arn=profile_arn,
        tools=tools,
        system=system,
        max_tokens=getattr(request, "max_tokens", 4096),
        thinking_config=thinking_cfg,
    )


# ---------------------------------------------------------------------------
# Anthropic request -> ACP request  (kept for ACP pipeline compatibility)
# ---------------------------------------------------------------------------

def anthropic_request_to_acp(req: AnthropicRequest) -> ACPRequest:
    acp_messages: List[ACPMessage] = []

    for msg in req.messages:
        blocks = normalise_content(msg.content)
        acp_messages.append(
            ACPMessage(
                role=map_role(msg.role, ANTHROPIC_TO_ACP_ROLE),
                content=blocks,
            )
        )

    system_text: Optional[str] = extract_system_prompt(req.system) or None

    thinking = None
    if req.thinking:
        thinking = {"type": req.thinking.type, "budget_tokens": req.thinking.budget_tokens}

    tool_choice = None
    if req.tool_choice:
        tc = req.tool_choice
        tc_type = getattr(tc, "type", None)
        tool_choice = {"type": tc_type}
        if tc_type == "tool":
            tool_choice["name"] = getattr(tc, "name", "")

    return ACPRequest(
        model=req.model,
        messages=acp_messages,
        system=system_text,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        top_p=getattr(req, "top_p", None),
        stream=req.stream or False,
        tools=convert_tools(req.tools),
        stop_sequences=req.stop_sequences,
        thinking=thinking,
        tool_choice=tool_choice,
    )


# ---------------------------------------------------------------------------
# ACP response -> Anthropic response
# ---------------------------------------------------------------------------

def acp_response_to_anthropic(
    acp_resp: ACPResponse,
    model: str,
    request_id: Optional[str] = None,
) -> AnthropicResponse:
    rid = request_id or new_response_id(prefix="msg")
    content_blocks: List[Any] = []

    for block in (acp_resp.content or []):
        btype = getattr(block, "type", None)
        if btype == "text":
            content_blocks.append(TextContentBlock(type="text", text=getattr(block, "text", "")))
        elif btype == "thinking":
            content_blocks.append(
                ThinkingContentBlock(
                    type="thinking",
                    thinking=getattr(block, "thinking", ""),
                    signature=getattr(block, "signature", None),
                )
            )
        elif btype == "redacted_thinking":
            content_blocks.append(
                RedactedThinkingContentBlock(type="redacted_thinking", data=getattr(block, "data", ""))
            )
        elif btype == "tool_use":
            content_blocks.append(
                ToolUseContentBlock(
                    type="tool_use",
                    id=getattr(block, "id", str(uuid.uuid4())),
                    name=getattr(block, "name", ""),
                    input=getattr(block, "input", {}),
                )
            )

    stop_reason = getattr(acp_resp, "stop_reason", None) or "end_turn"
    usage = getattr(acp_resp, "usage", None)
    anthropic_usage = AnthropicUsage(
        input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
        output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
    )

    return AnthropicResponse(
        id=rid,
        type="message",
        role="assistant",
        model=model,
        content=content_blocks,
        stop_reason=stop_reason,
        stop_sequence=getattr(acp_resp, "stop_sequence", None),
        usage=anthropic_usage,
    )
