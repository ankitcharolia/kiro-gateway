# -*- coding: utf-8 -*-
"""
Anthropic-compatible shim routes backed by ACP.

Endpoints
---------
The router declares relative paths (``/models``, ``/messages``,
``/messages/count_tokens``). ``main.py`` mounts it under several base-path
prefixes so clients work whichever base URL convention they use:

* ``/v1/...``            — standard Anthropic base URL ``http://host:8000``
* ``/...``               — base URL already includes the version, e.g. ``http://host:8000`` + ``/messages``
* ``/anthropic/v1/...``  — explicit provider-namespaced base URL
* ``/anthropic/...``     — provider-namespaced base URL without a version segment

Fixes
-----
1. STREAMING: Events mirror the Anthropic SSE event taxonomy exactly:
   message_start, content_block_start, content_block_delta (text_delta
   and input_json_delta for tool use), content_block_stop, message_delta,
   message_stop. Tokens arrive as they come from ACP — no buffering.

2. TOOL-CALLING: Full tool_use block support.
   - ACP tool_call events → Anthropic content_block_start[tool_use]
     + input_json_delta chunks + content_block_stop.
   - Client sends back tool_result content blocks in user turn;
     gateway injects them into a follow-up session/prompt.

3. FILESYSTEM/TERMINAL: Capability requests handled transparently by
   CapabilityExecutor. Never interrupts the SSE stream from client's view.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from kiro.acp_models import PromptMessage, ToolResult, FilesystemRoot, TerminalCapability
from kiro.auth import verify_anthropic_key
from kiro.config import DEFAULT_KIRO_MODELS
from kiro.shim_service import ShimService
from kiro.tokenizer import estimate_request_tokens

router = APIRouter(tags=["Anthropic Shim"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AnthropicContentPart(BaseModel):
    type: str
    text: Optional[str] = None
    tool_use_id: Optional[str] = None
    content: Optional[Any] = None
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[dict] = None


class AnthropicMessage(BaseModel):
    role: str
    content: Any  # str | list[content_part]


class AnthropicTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: dict[str, Any] = Field(default_factory=dict)


class AnthropicRequest(BaseModel):
    model: str = "claude-sonnet-4-5"
    messages: list[AnthropicMessage]
    # Anthropic accepts ``system`` as a plain string OR a list of text content
    # blocks (often carrying ``cache_control``). Accept both so SDK/Claude Code
    # style requests validate instead of failing with a 422.
    system: str | list | None = None
    max_tokens: int = 4096
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[list[str]] = None
    tools: Optional[list[AnthropicTool]] = None
    stream: bool = False
    # Gateway extensions
    filesystem_roots: list[dict] = Field(default_factory=list)
    terminal: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _system_to_text(system: str | list | None) -> Optional[str]:
    """Flatten an Anthropic ``system`` field to plain text.

    The Anthropic Messages API accepts ``system`` as either a plain string or a
    list of text content blocks, e.g. ``[{"type": "text", "text": "...",
    "cache_control": {"type": "ephemeral"}}]``. This collapses either shape to a
    single string.

    Args:
        system: The raw ``system`` value (string, list of blocks, or ``None``).

    Returns:
        The concatenated system text, or ``None`` when empty.
    """
    if not system:
        return None
    if isinstance(system, str):
        return system
    parts: list[str] = []
    for block in system:
        if isinstance(block, dict):
            text = block.get("text")
            if text:
                parts.append(text)
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts) or None


def _anthropic_messages_to_acp(
    messages: list[AnthropicMessage],
    system: str | list | None,
) -> list[PromptMessage]:
    result = []
    system_text = _system_to_text(system)
    if system_text:
        result.append(PromptMessage(role="user", content=f"[system]\n{system_text}"))

    for m in messages:
        role = "user" if m.role == "user" else "assistant"

        if isinstance(m.content, str):
            result.append(PromptMessage(role=role, content=m.content))
            continue

        if isinstance(m.content, list):
            parts = []
            for part in m.content:
                if isinstance(part, dict):
                    ptype = part.get("type", "")
                    if ptype == "text":
                        parts.append(part.get("text", ""))
                    elif ptype == "tool_use":
                        parts.append(
                            f"[tool_use id={part.get('id')} name={part.get('name')}]\n"
                            f"{json.dumps(part.get('input', {}))}"
                        )
                    elif ptype == "tool_result":
                        content = part.get("content", "")
                        if isinstance(content, list):
                            content = "\n".join(
                                p.get("text", "") for p in content if isinstance(p, dict)
                            )
                        parts.append(
                            f"[tool_result id={part.get('tool_use_id')}]\n{content}"
                        )
                else:
                    parts.append(str(part))
            result.append(PromptMessage(role=role, content="\n".join(parts)))

    return result


def _anthropic_tools_to_acp(tools: list[AnthropicTool]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "parameters": t.input_schema,
        }
        for t in tools
    ]


def _get_shim(request: Request) -> ShimService:
    return request.app.state.shim_service


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models(shim: ShimService = Depends(_get_shim)):
    """List available models (Anthropic listing shape).

    Serves the live catalogue discovered from kiro-cli (``session/new``) when a
    session has been created; otherwise falls back to the configured
    ``DEFAULT_KIRO_MODELS``.
    """
    live = shim.available_models()
    if live:
        data = [
            {
                "type": "model",
                "id": m["id"],
                "display_name": m.get("name") or m["id"],
            }
            for m in live
        ]
    else:
        data = [
            {"type": "model", "id": model_id, "display_name": model_id}
            for model_id in DEFAULT_KIRO_MODELS
        ]
    return {"data": data}


# ---------------------------------------------------------------------------
# POST /v1/messages
# ---------------------------------------------------------------------------

@router.post("/messages", dependencies=[Depends(verify_anthropic_key)])
async def create_message(
    body: AnthropicRequest,
    shim: ShimService = Depends(_get_shim),
):
    messages = _anthropic_messages_to_acp(body.messages, body.system)
    tools = _anthropic_tools_to_acp(body.tools or [])
    fs_roots = [FilesystemRoot(**r) for r in body.filesystem_roots] if body.filesystem_roots else []
    terminal = TerminalCapability(**body.terminal) if body.terminal else None
    stop = body.stop_sequences or None

    if body.stream:
        return StreamingResponse(
            _stream_response(shim, messages, body.model, body.max_tokens,
                             body.temperature, body.top_p, body.top_k, stop,
                             tools, fs_roots, terminal),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        result = await shim.complete(
            messages=messages,
            model=body.model,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            top_p=body.top_p,
            top_k=body.top_k,
            stop=stop,
            tools=tools,
            filesystem_roots=fs_roots,
            terminal=terminal,
        )
    except Exception as exc:
        logger.error(f"Anthropic shim complete error: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))

    content_blocks: list[dict] = []
    if result["content"]:
        content_blocks.append({"type": "text", "text": result["content"]})
    for tc in result.get("tool_calls", []):
        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", str(uuid.uuid4())),
            "name": tc.get("name", ""),
            "input": tc.get("arguments", {}),
        })

    stop_reason = "tool_use" if result.get("tool_calls") else "end_turn"

    return {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": body.model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": result.get("usage", {}).get("input_tokens", 0),
            "output_tokens": result.get("usage", {}).get("output_tokens", 0),
        },
    }


async def _stream_response(
    shim: ShimService,
    messages: list[PromptMessage],
    model: str,
    max_tokens: int,
    temperature: Optional[float],
    top_p: Optional[float],
    top_k: Optional[int],
    stop: Optional[list[str]],
    tools: list[dict],
    fs_roots: list[FilesystemRoot],
    terminal: Optional[TerminalCapability],
) -> AsyncIterator[str]:
    """
    Translate ACP progress events to Anthropic SSE event taxonomy.

    ACP event → Anthropic SSE:
      (start)        → message_start + content_block_start[text]
      text           → content_block_delta[text_delta]
      thinking       → content_block_delta[text_delta] (inside thinking block)
      tool_call      → content_block_stop (text) +
                        content_block_start[tool_use] +
                        content_block_delta[input_json_delta] +
                        content_block_stop (tool)
      done           → content_block_stop + message_delta + message_stop
      error          → error event
    """
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    input_tokens = 0
    output_tokens = 0
    block_idx = 0
    in_text_block = False
    active_tool_blocks: dict[str, int] = {}  # tool_call_id -> block_index

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    # message_start
    yield sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    })

    # ping
    yield sse("ping", {"type": "ping"})

    try:
        async for event in shim.stream_tokens(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            stop=stop,
            tools=tools,
            filesystem_roots=fs_roots,
            terminal=terminal,
        ):
            etype = event.get("type")

            if etype == "text":
                delta = event.get("content", "")
                if not delta:
                    continue
                if not in_text_block:
                    yield sse("content_block_start", {
                        "type": "content_block_start",
                        "index": block_idx,
                        "content_block": {"type": "text", "text": ""},
                    })
                    in_text_block = True
                yield sse("content_block_delta", {
                    "type": "content_block_delta",
                    "index": block_idx,
                    "delta": {"type": "text_delta", "text": delta},
                })
                output_tokens += 1  # rough count until usage arrives in done event

            elif etype == "thinking":
                # Reasoning is not surfaced on the Anthropic content stream.
                continue

            elif etype == "tool_call":
                tc_id = event.get("id", str(uuid.uuid4()))
                name = event.get("name", "")
                arguments = event.get("arguments", {})

                if tc_id not in active_tool_blocks:
                    # Close the text block if open
                    if in_text_block:
                        yield sse("content_block_stop", {"type": "content_block_stop", "index": block_idx})
                        block_idx += 1
                        in_text_block = False

                    active_tool_blocks[tc_id] = block_idx
                    yield sse("content_block_start", {
                        "type": "content_block_start",
                        "index": block_idx,
                        "content_block": {
                            "type": "tool_use",
                            "id": tc_id,
                            "name": name,
                            "input": {},
                        },
                    })

                    # Stream arguments as input_json_delta
                    if arguments:
                        yield sse("content_block_delta", {
                            "type": "content_block_delta",
                            "index": block_idx,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": json.dumps(arguments),
                            },
                        })

                    yield sse("content_block_stop", {"type": "content_block_stop", "index": block_idx})
                    block_idx += 1

            elif etype == "done":
                # Close open text block
                if in_text_block:
                    yield sse("content_block_stop", {"type": "content_block_stop", "index": block_idx})

                usage = event.get("usage", {}) or {}
                stop_reason = "tool_use" if active_tool_blocks else (
                    event.get("finish_reason") or "end_turn"
                )
                # Normalise OpenAI-style finish reasons to Anthropic vocabulary.
                if stop_reason == "stop":
                    stop_reason = "end_turn"
                elif stop_reason == "length":
                    stop_reason = "max_tokens"

                yield sse("message_delta", {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": stop_reason,
                        "stop_sequence": None,
                    },
                    "usage": {
                        "output_tokens": usage.get("output_tokens", output_tokens),
                    },
                })
                yield sse("message_stop", {"type": "message_stop"})
                break

            elif etype == "error":
                message = event.get("message") or event.get("error") or "Unknown ACP error"
                yield sse("error", {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": message,
                    },
                })
                break

    except Exception as exc:
        logger.error(f"Anthropic stream error: {exc}")
        yield sse("error", {
            "type": "error",
            "error": {"type": "gateway_error", "message": str(exc)},
        })


# ===========================================================================
# Anthropic Token Counting — POST /v1/messages/count_tokens
#
# kiro-cli (ACP) exposes no exact token-count method, so this returns a local
# estimate using the same tokenizer the gateway uses for context-window
# management (tiktoken cl100k_base + a Claude correction factor). It mirrors
# the request shape of /v1/messages and returns {"input_tokens": N}. The value
# is an approximation suitable for budgeting, not an exact server-side count.
# ===========================================================================

class AnthropicCountTokensRequest(BaseModel):
    model: str = "claude-sonnet-4-5"
    messages: list[AnthropicMessage]
    system: str | list | None = None
    tools: Optional[list[AnthropicTool]] = None


@router.post("/messages/count_tokens", dependencies=[Depends(verify_anthropic_key)])
async def count_message_tokens(body: AnthropicCountTokensRequest):
    """Estimate the input token count for an Anthropic Messages request.

    Returns:
        ``{"input_tokens": int}`` — a local tokenizer estimate (not an exact
        server-side count, which kiro-cli/ACP does not expose).
    """
    messages = [
        {"role": m.role, "content": m.content}
        for m in body.messages
    ]
    tools = [
        {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
        for t in (body.tools or [])
    ]
    input_tokens = estimate_request_tokens(
        messages=messages,
        tools=tools or None,
        system=body.system,
    )
    return {"input_tokens": input_tokens}
