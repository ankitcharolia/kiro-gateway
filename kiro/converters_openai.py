"""Convert between OpenAI-compatible API shapes and ACP messages."""
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
)
from .converters_core import (
    OPENAI_TO_ACP_ROLE,
    map_role,
    normalise_content,
    convert_tools,
    extract_thinking,
    new_response_id,
    now_ts,
)
from .models_openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionUsage,
    Message,
    FunctionCall,
    ToolCall,
)


# ---------------------------------------------------------------------------
# OpenAI request -> ACP request
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

    thinking = None
    if getattr(req, "thinking", None):
        thinking = req.thinking
    elif getattr(req, "reasoning_effort", None):
        budget_map = {"low": 1024, "medium": 8192, "high": 32768}
        budget = budget_map.get(req.reasoning_effort, 8192)
        thinking = {"type": "enabled", "budget_tokens": budget}

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


def _map_stop_reason_to_openai(stop_reason: Optional[str]) -> str:
    mapping = {
        "end_turn": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
        "stop_sequence": "stop",
    }
    return mapping.get(stop_reason or "", "stop")
