"""Convert between Anthropic-compatible API shapes and ACP messages."""
from __future__ import annotations

import json
import uuid
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


# ---------------------------------------------------------------------------
# Anthropic request -> ACP request
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

    system_text: Optional[str] = None
    if req.system:
        if isinstance(req.system, str):
            system_text = req.system
        else:
            system_text = " ".join(getattr(b, "text", str(b)) for b in req.system)

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
        top_p=req.top_p,
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
