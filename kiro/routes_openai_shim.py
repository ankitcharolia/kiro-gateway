# -*- coding: utf-8 -*-
"""
OpenAI-compatible shim routes backed by ACP.

Endpoints
---------
GET  /v1/models
POST /v1/chat/completions   (streaming + non-streaming)

Fixes
-----
1. STREAMING: Events are yielded token-by-token from ACP progress
   notifications. No buffering. Clients see tokens as kiro-cli emits them.

2. TOOL-CALLING: Full parallel + sequential tool_call round-trip.
   - tool_use events from ACP are translated to OpenAI function_call deltas.
   - Caller sends back tool role messages; these are injected as a
     follow-up session/prompt so kiro-cli sees them.

3. FILESYSTEM/TERMINAL: Capability requests are handled transparently
   by CapabilityExecutor. The token stream is not interrupted.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from kiro.acp_models import PromptMessage, ToolResult, FilesystemRoot, TerminalCapability
from kiro.auth import verify_openai_key
from kiro.config import DEFAULT_KIRO_MODELS
from kiro.error_mapping import MappedError, classify_event, classify_exception
from kiro.shim_service import ShimService
from kiro.tokenizer import normalize_usage

router = APIRouter(prefix="/v1", tags=["OpenAI Shim"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class OAIToolFunction(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class OAITool(BaseModel):
    type: str = "function"
    function: OAIToolFunction


class OAIMessage(BaseModel):
    role: str
    content: Optional[Any] = None  # str | list[content_part]
    name: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None


class OAIChatRequest(BaseModel):
    model: str = "claude-sonnet-4-5"
    messages: list[OAIMessage]
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    # stop may be a single string or a list of strings (OpenAI spec).
    stop: Optional[Any] = None
    tools: Optional[list[OAITool]] = None
    # Streaming usage opt-in: {"include_usage": true} appends a final usage-only
    # chunk to the SSE stream (OpenAI semantics).
    stream_options: Optional[dict] = None
    # logprobs are not supported by the ACP path (kiro-cli exposes none); the
    # fields are accepted for API compatibility and reported back as null.
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    # Gateway extensions (optional, ignored by standard clients)
    filesystem_roots: list[dict] = Field(default_factory=list)
    terminal: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _oai_messages_to_acp(messages: list[OAIMessage]) -> list[PromptMessage]:
    """Convert an OpenAI message list to an ACP ``PromptMessage`` list.

    Role handling preserves instruction provenance instead of silently
    flattening it into anonymous user text:

    * ``system`` and ``developer`` are kept as distinct roles. ACP has no
      dedicated system channel, so the prompt serialiser
      (:func:`ACPClient._build_prompt_blocks`) renders them with explicit
      ``System:`` / ``Developer:`` labels, keeping each message separate and in
      order rather than merging them.
    * ``assistant`` is preserved.
    * ``tool`` (and any other role) is rendered as ``user`` content; tool
      results additionally carry a ``[tool_result id=...]`` marker for context.

    Args:
        messages: The OpenAI request messages.

    Returns:
        A list of :class:`PromptMessage` preserving role provenance.
    """
    result = []
    for m in messages:
        role = m.role
        if role in ("system", "developer"):
            acp_role = role
        elif role == "assistant":
            acp_role = "assistant"
        else:
            # user, tool, function, or anything unexpected → user content.
            acp_role = "user"

        # Flatten content
        if isinstance(m.content, list):
            text_parts = []
            for part in m.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "tool_result":
                        text_parts.append(str(part.get("content", "")))
                else:
                    text_parts.append(str(part))
            content = "\n".join(text_parts)
        else:
            content = m.content or ""

        # tool role: wrap with tool_call_id context
        if m.role == "tool" and m.tool_call_id:
            content = f"[tool_result id={m.tool_call_id}]\n{content}"

        result.append(PromptMessage(role=acp_role, content=str(content)))
    return result


def _acp_tool_calls_to_oai(tool_calls: list[dict]) -> list[dict]:
    """Convert ACP ToolCall list to OpenAI tool_calls format."""
    result = []
    for tc in tool_calls:
        result.append({
            "id": tc.get("id", str(uuid.uuid4())),
            "type": "function",
            "function": {
                "name": tc.get("name", ""),
                "arguments": json.dumps(tc.get("arguments", {})),
            },
        })
    return result


def _get_shim(request: Request) -> ShimService:
    return request.app.state.shim_service


def _openai_error_response(mapped: MappedError) -> JSONResponse:
    """Build a native OpenAI error ``JSONResponse`` from a classified error.

    Args:
        mapped: The classified error carrying the status code, message, native
            ``type`` and optional ``Retry-After`` hint.

    Returns:
        A :class:`JSONResponse` with the OpenAI ``{"error": {...}}`` body, the
        mapped HTTP status code, and a ``Retry-After`` header when available.
    """
    return JSONResponse(
        status_code=mapped.status_code,
        content=mapped.to_openai_error(),
        headers=mapped.headers(),
    )


def _normalize_stop(stop: Any) -> Optional[list[str]]:
    """Normalise an OpenAI ``stop`` value to a list of strings or ``None``.

    The OpenAI API accepts ``stop`` as a single string or a list of strings.

    Args:
        stop: The raw ``stop`` value (string, list, or ``None``).

    Returns:
        A list of non-empty stop strings, or ``None`` when nothing is set.
    """
    if stop is None:
        return None
    if isinstance(stop, str):
        return [stop] if stop else None
    if isinstance(stop, list):
        cleaned = [str(s) for s in stop if s]
        return cleaned or None
    return None


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models(shim: ShimService = Depends(_get_shim)):
    """List available models.

    Serves the live catalogue discovered from kiro-cli (``session/new``) when a
    session has been created; otherwise falls back to the configured
    ``DEFAULT_KIRO_MODELS`` so discovery works before the first completion.
    """
    live = shim.available_models()
    model_ids = [m["id"] for m in live] if live else list(DEFAULT_KIRO_MODELS)
    models = [
        {"id": model_id, "object": "model", "owned_by": "kiro"}
        for model_id in model_ids
    ]
    return {"object": "list", "data": models}


@router.get("/models/{model_id:path}")
async def retrieve_model(model_id: str, shim: ShimService = Depends(_get_shim)):
    """Retrieve a single model object (OpenAI ``GET /v1/models/{model}``).

    Some harnesses (e.g. hermes-agent) probe this endpoint to confirm a model
    exists and to read its metadata. The gateway forwards any model id to
    kiro-cli via ``session/set_model``, so this is permissive: it returns a
    valid model object for the requested id, using the live catalogue entry
    when one is known. The ``{model_id:path}`` converter accepts ids that
    contain slashes (e.g. ``vendor/model``).

    Args:
        model_id: The requested model id.
        shim: The shared ShimService (for the live catalogue).

    Returns:
        An OpenAI model object ``{"id", "object": "model", "created",
        "owned_by"}``.
    """
    return {
        "id": model_id,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "kiro",
    }


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------

@router.post("/chat/completions", dependencies=[Depends(verify_openai_key)])
async def chat_completions(
    body: OAIChatRequest,
    shim: ShimService = Depends(_get_shim),
):
    messages = _oai_messages_to_acp(body.messages)
    tools = [t.model_dump() for t in (body.tools or [])]
    fs_roots = [FilesystemRoot(**r) for r in body.filesystem_roots] if body.filesystem_roots else []
    terminal = TerminalCapability(**body.terminal) if body.terminal else None
    stop = _normalize_stop(body.stop)

    if body.stream:
        include_usage = bool((body.stream_options or {}).get("include_usage"))
        return StreamingResponse(
            _stream_response(shim, messages, body.model, body.max_tokens,
                             body.temperature, body.top_p, stop, tools, fs_roots,
                             terminal, include_usage),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming
    try:
        result = await shim.complete(
            messages=messages,
            model=body.model,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            top_p=body.top_p,
            stop=stop,
            tools=tools,
            filesystem_roots=fs_roots,
            terminal=terminal,
        )
    except Exception as exc:
        mapped = classify_exception(exc)
        logger.error(
            f"OpenAI shim complete error (status={mapped.status_code}): {exc}"
        )
        return _openai_error_response(mapped)

    tool_calls = _acp_tool_calls_to_oai(result.get("tool_calls", []))
    finish_reason = "tool_calls" if tool_calls else result.get("finish_reason", "stop")

    usage = normalize_usage(
        result.get("usage"),
        prompt_messages=[m.model_dump() for m in body.messages],
        prompt_tools=tools,
        completion_text=result.get("content") or "",
        completion_tool_calls=result.get("tool_calls"),
    )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": result["content"] if not tool_calls else None,
                "tool_calls": tool_calls if tool_calls else None,
            },
            # logprobs are unsupported by the ACP path; reported as null.
            "logprobs": None,
            "finish_reason": finish_reason,
        }],
        "usage": {
            "prompt_tokens": usage["input_tokens"],
            "completion_tokens": usage["output_tokens"],
            "total_tokens": usage["total_tokens"],
        },
    }


async def _stream_response(
    shim: ShimService,
    messages: list[PromptMessage],
    model: str,
    max_tokens: Optional[int],
    temperature: Optional[float],
    top_p: Optional[float],
    stop: Optional[list[str]],
    tools: list[dict],
    fs_roots: list[FilesystemRoot],
    terminal: Optional[TerminalCapability],
    include_usage: bool = False,
) -> AsyncIterator[str]:
    """
    Translate ACP progress events to OpenAI streaming SSE format.

    ACP event types → OpenAI SSE:
      text       → delta.content chunk
      tool_call  → delta.tool_calls chunk (name + arguments streaming)
      thinking   → delta.content chunk (prefixed with <thinking>)
      done       → [DONE] + finish_reason
      error      → error chunk
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    active_tool_idx: dict[str, int] = {}  # tool_call_id -> index
    tool_counter = 0
    # Accumulators for the optional usage chunk (stream_options.include_usage).
    text_acc: list[str] = []
    collected_tool_calls: dict[str, dict] = {}  # tool_call_id -> {name, arguments}

    def chunk(delta: dict, finish_reason: Optional[str] = None) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }],
        }
        return f"data: {json.dumps(payload)}\n\n"

    # Opening role chunk
    yield chunk({"role": "assistant", "content": ""})

    try:
        async for event in shim.stream_tokens(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
            tools=tools,
            filesystem_roots=fs_roots,
            terminal=terminal,
        ):
            etype = event.get("type")

            if etype == "text":
                delta = event.get("content", "")
                if delta:
                    text_acc.append(delta)
                    yield chunk({"content": delta})

            elif etype == "thinking":
                # Reasoning is not emitted on the OpenAI surface to keep the
                # assistant message clean; clients receive only final content.
                continue

            elif etype == "tool_call":
                tc_id = event.get("id", str(uuid.uuid4()))
                name = event.get("name", "")
                arguments = event.get("arguments", {})
                collected_tool_calls[tc_id] = {"name": name, "arguments": arguments}
                if tc_id not in active_tool_idx:
                    idx = tool_counter
                    active_tool_idx[tc_id] = idx
                    tool_counter += 1
                    yield chunk({"tool_calls": [{
                        "index": idx,
                        "id": tc_id,
                        "type": "function",
                        "function": {"name": name, "arguments": ""},
                    }]})
                else:
                    idx = active_tool_idx[tc_id]

                args_str = json.dumps(arguments) if arguments else ""
                if args_str:
                    yield chunk({"tool_calls": [{
                        "index": idx,
                        "function": {"arguments": args_str},
                    }]})

            elif etype == "done":
                finish_reason = "tool_calls" if active_tool_idx else (
                    event.get("finish_reason") or "stop"
                )
                yield chunk({}, finish_reason=finish_reason)
                if include_usage:
                    usage = normalize_usage(
                        event.get("usage"),
                        prompt_messages=[{"role": m.role, "content": m.content} for m in messages],
                        prompt_tools=tools,
                        completion_text="".join(text_acc),
                        completion_tool_calls=list(collected_tool_calls.values()),
                    )
                    yield (
                        "data: "
                        + json.dumps({
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [],
                            "usage": {
                                "prompt_tokens": usage["input_tokens"],
                                "completion_tokens": usage["output_tokens"],
                                "total_tokens": usage["total_tokens"],
                            },
                        })
                        + "\n\n"
                    )
                yield "data: [DONE]\n\n"
                break

            elif etype == "error":
                mapped = classify_event(event)
                error_payload = {"error": {
                    "message": mapped.message,
                    "type": mapped.openai_type,
                    "code": None,
                    "param": None,
                }}
                yield f"data: {json.dumps(error_payload)}\n\n"
                yield "data: [DONE]\n\n"
                break

    except Exception as exc:
        mapped = classify_exception(exc)
        logger.error(f"OpenAI stream error (status={mapped.status_code}): {exc}")
        error_payload = {"error": {
            "message": mapped.message,
            "type": mapped.openai_type,
            "code": None,
            "param": None,
        }}
        yield f"data: {json.dumps(error_payload)}\n\n"
        yield "data: [DONE]\n\n"


# ===========================================================================
# OpenAI Responses API — POST /v1/responses
#
# The Responses API is a text-generation endpoint, so it maps onto the same
# ShimService → ACP path as /v1/chat/completions. This is a faithful subset:
# it supports string or structured `input`, `instructions`, tools, streaming
# and non-streaming. Stateful features (`previous_response_id`, server-side
# storage) are not supported because each gateway request opens a fresh,
# isolated ACP session.
# ===========================================================================

class OAIResponsesRequest(BaseModel):
    model: str = "claude-sonnet-4-5"
    # input: a plain string, or a list of message items
    # ({"role": ..., "content": str | list[part]}).
    input: Any
    instructions: Optional[str] = None
    stream: bool = False
    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    tools: Optional[list[dict]] = None
    # Gateway extensions (optional, ignored by standard clients)
    filesystem_roots: list[dict] = Field(default_factory=list)
    terminal: Optional[dict] = None


def _responses_input_to_acp(
    input_value: Any,
    instructions: Optional[str],
) -> list[PromptMessage]:
    """Convert a Responses API ``input`` (+ ``instructions``) to ACP messages.

    Args:
        input_value: Either a plain string prompt or a list of message items.
            Each item is ``{"role": str, "content": str | list[part]}`` where a
            part is ``{"type": "input_text"|"output_text"|"text", "text": str}``.
        instructions: Optional system-style instructions prepended to the turn.

    Returns:
        A list of :class:`PromptMessage` for ``ShimService``.
    """
    messages: list[PromptMessage] = []
    if instructions:
        # The Responses API ``instructions`` field is system-level guidance.
        # Preserve it as a distinct system role (rendered with a ``System:``
        # label) rather than collapsing it into anonymous user text.
        messages.append(PromptMessage(role="system", content=str(instructions)))

    if isinstance(input_value, str):
        messages.append(PromptMessage(role="user", content=input_value))
        return messages

    if isinstance(input_value, list):
        for item in input_value:
            if not isinstance(item, dict):
                messages.append(PromptMessage(role="user", content=str(item)))
                continue
            role = item.get("role", "user")
            if role not in ("user", "assistant"):
                role = "user"
            content = item.get("content", "")
            if isinstance(content, list):
                text_parts: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in ("input_text", "output_text", "text"):
                            text_parts.append(part.get("text", ""))
                        else:
                            text_parts.append(str(part.get("text", "")))
                    else:
                        text_parts.append(str(part))
                content = "\n".join(p for p in text_parts if p)
            messages.append(PromptMessage(role=role, content=str(content)))
        return messages

    # Fallback: stringify anything else.
    messages.append(PromptMessage(role="user", content=str(input_value)))
    return messages


def _build_response_object(
    response_id: str,
    model: str,
    created: int,
    text: str,
    tool_calls: list[dict],
    usage: dict,
    status: str = "completed",
) -> dict:
    """Assemble a Responses API ``response`` object from aggregated output."""
    output: list[dict] = []
    if text:
        output.append({
            "type": "message",
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        })
    for tc in tool_calls:
        output.append({
            "type": "function_call",
            "id": f"fc_{uuid.uuid4().hex[:24]}",
            "call_id": tc.get("id", f"call_{uuid.uuid4().hex[:24]}"),
            "name": tc.get("name", ""),
            "arguments": json.dumps(tc.get("arguments", {})),
            "status": "completed",
        })
    return {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "status": status,
        "model": model,
        "output": output,
        "output_text": text,
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


@router.post("/responses", dependencies=[Depends(verify_openai_key)])
async def create_response(
    body: OAIResponsesRequest,
    shim: ShimService = Depends(_get_shim),
):
    """OpenAI Responses API endpoint, backed by ACP via ShimService."""
    messages = _responses_input_to_acp(body.input, body.instructions)
    tools = list(body.tools or [])
    fs_roots = [FilesystemRoot(**r) for r in body.filesystem_roots] if body.filesystem_roots else []
    terminal = TerminalCapability(**body.terminal) if body.terminal else None

    if body.stream:
        return StreamingResponse(
            _responses_stream(shim, messages, body.model, body.max_output_tokens,
                              body.temperature, body.top_p, tools, fs_roots, terminal),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        result = await shim.complete(
            messages=messages,
            model=body.model,
            max_tokens=body.max_output_tokens,
            temperature=body.temperature,
            top_p=body.top_p,
            tools=tools,
            filesystem_roots=fs_roots,
            terminal=terminal,
        )
    except Exception as exc:
        mapped = classify_exception(exc)
        logger.error(
            f"OpenAI responses complete error (status={mapped.status_code}): {exc}"
        )
        return _openai_error_response(mapped)

    response_id = f"resp_{uuid.uuid4().hex[:24]}"
    text = result.get("content", "") or ""
    usage = normalize_usage(
        result.get("usage"),
        prompt_messages=[{"role": m.role, "content": m.content} for m in messages],
        prompt_tools=tools,
        completion_text=text,
        completion_tool_calls=result.get("tool_calls"),
    )
    return _build_response_object(
        response_id=response_id,
        model=body.model,
        created=int(time.time()),
        text=text,
        tool_calls=result.get("tool_calls", []),
        usage=usage,
    )


async def _responses_stream(
    shim: ShimService,
    messages: list[PromptMessage],
    model: str,
    max_output_tokens: Optional[int],
    temperature: Optional[float],
    top_p: Optional[float],
    tools: list[dict],
    fs_roots: list[FilesystemRoot],
    terminal: Optional[TerminalCapability],
) -> AsyncIterator[str]:
    """Translate ACP events into Responses API SSE semantic events.

    Emits the core event sequence consumed by the OpenAI SDK:
    ``response.created`` → output item / content part wrappers →
    ``response.output_text.delta`` (and ``response.function_call_arguments.*``
    for tool calls) → ``response.completed``.
    """
    response_id = f"resp_{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    message_item_id = f"msg_{uuid.uuid4().hex[:24]}"
    seq = 0
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    text_item_open = False
    output_index = 0
    # tool_call_id -> output_index
    tool_output_index: dict[str, int] = {}

    def sse(event: str, data: dict) -> str:
        nonlocal seq
        data.setdefault("type", event)
        data["sequence_number"] = seq
        seq += 1
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    def base_response(status: str) -> dict:
        return {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": status,
            "model": model,
            "output": [],
        }

    # response.created + in_progress
    yield sse("response.created", {"response": base_response("in_progress")})
    yield sse("response.in_progress", {"response": base_response("in_progress")})

    try:
        async for event in shim.stream_tokens(
            messages=messages,
            model=model,
            max_tokens=max_output_tokens,
            temperature=temperature,
            top_p=top_p,
            tools=tools,
            filesystem_roots=fs_roots,
            terminal=terminal,
        ):
            etype = event.get("type")

            if etype == "text":
                delta = event.get("content", "")
                if not delta:
                    continue
                if not text_item_open:
                    yield sse("response.output_item.added", {
                        "output_index": output_index,
                        "item": {
                            "type": "message", "id": message_item_id,
                            "status": "in_progress", "role": "assistant", "content": [],
                        },
                    })
                    yield sse("response.content_part.added", {
                        "item_id": message_item_id, "output_index": output_index,
                        "content_index": 0,
                        "part": {"type": "output_text", "text": "", "annotations": []},
                    })
                    text_item_open = True
                text_parts.append(delta)
                yield sse("response.output_text.delta", {
                    "item_id": message_item_id, "output_index": output_index,
                    "content_index": 0, "delta": delta,
                })

            elif etype == "thinking":
                # Reasoning is not surfaced on the Responses output stream.
                continue

            elif etype == "tool_call":
                # Close the text item first if it is open.
                if text_item_open:
                    full_text = "".join(text_parts)
                    yield sse("response.output_text.done", {
                        "item_id": message_item_id, "output_index": output_index,
                        "content_index": 0, "text": full_text,
                    })
                    yield sse("response.content_part.done", {
                        "item_id": message_item_id, "output_index": output_index,
                        "content_index": 0,
                        "part": {"type": "output_text", "text": full_text, "annotations": []},
                    })
                    yield sse("response.output_item.done", {
                        "output_index": output_index,
                        "item": {
                            "type": "message", "id": message_item_id, "status": "completed",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": full_text, "annotations": []}],
                        },
                    })
                    text_item_open = False

                tc_id = event.get("id", f"call_{uuid.uuid4().hex[:24]}")
                name = event.get("name", "")
                arguments = event.get("arguments", {})
                if tc_id not in tool_output_index:
                    output_index += 1
                    tool_output_index[tc_id] = output_index
                    fc_item_id = f"fc_{uuid.uuid4().hex[:24]}"
                    tool_calls.append({"id": tc_id, "name": name, "arguments": arguments,
                                       "item_id": fc_item_id})
                    yield sse("response.output_item.added", {
                        "output_index": output_index,
                        "item": {
                            "type": "function_call", "id": fc_item_id, "call_id": tc_id,
                            "name": name, "arguments": "", "status": "in_progress",
                        },
                    })
                    args_str = json.dumps(arguments) if arguments else ""
                    if args_str:
                        yield sse("response.function_call_arguments.delta", {
                            "item_id": fc_item_id, "output_index": output_index, "delta": args_str,
                        })
                    yield sse("response.function_call_arguments.done", {
                        "item_id": fc_item_id, "output_index": output_index, "arguments": args_str,
                    })
                    yield sse("response.output_item.done", {
                        "output_index": output_index,
                        "item": {
                            "type": "function_call", "id": fc_item_id, "call_id": tc_id,
                            "name": name, "arguments": args_str, "status": "completed",
                        },
                    })

            elif etype == "done":
                # Close a still-open text item.
                if text_item_open:
                    full_text = "".join(text_parts)
                    yield sse("response.output_text.done", {
                        "item_id": message_item_id, "output_index": output_index,
                        "content_index": 0, "text": full_text,
                    })
                    yield sse("response.content_part.done", {
                        "item_id": message_item_id, "output_index": output_index,
                        "content_index": 0,
                        "part": {"type": "output_text", "text": full_text, "annotations": []},
                    })
                    yield sse("response.output_item.done", {
                        "output_index": output_index,
                        "item": {
                            "type": "message", "id": message_item_id, "status": "completed",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": full_text, "annotations": []}],
                        },
                    })
                    text_item_open = False

                final_text = "".join(text_parts)
                final_tool_calls = [
                    {"id": t["id"], "name": t["name"], "arguments": t["arguments"]}
                    for t in tool_calls
                ]
                usage = normalize_usage(
                    event.get("usage"),
                    prompt_messages=[{"role": m.role, "content": m.content} for m in messages],
                    prompt_tools=tools,
                    completion_text=final_text,
                    completion_tool_calls=final_tool_calls,
                )
                final = _build_response_object(
                    response_id=response_id, model=model, created=created,
                    text=final_text,
                    tool_calls=final_tool_calls,
                    usage=usage,
                )
                yield sse("response.completed", {"response": final})
                break

            elif etype == "error":
                mapped = classify_event(event)
                failed = base_response("failed")
                failed["error"] = {"message": mapped.message, "type": mapped.openai_type}
                yield sse("response.failed", {"response": failed})
                break

    except Exception as exc:
        mapped = classify_exception(exc)
        logger.error(
            f"OpenAI responses stream error (status={mapped.status_code}): {exc}"
        )
        failed = base_response("failed")
        failed["error"] = {"message": mapped.message, "type": mapped.openai_type}
        yield sse("response.failed", {"response": failed})


# ===========================================================================
# OpenAI Embeddings API — POST /v1/embeddings
#
# kiro-cli (ACP) provides no embeddings model, and the gateway's compliance
# model forbids routing through any other provider. Rather than 404 (which
# clients read as a misconfigured base URL) or fabricate vectors (which would
# silently corrupt semantic search / RAG), the endpoint exists and returns a
# clear 501 Not Implemented.
# ===========================================================================

@router.post("/embeddings", dependencies=[Depends(verify_openai_key)])
async def create_embeddings():
    """Embeddings are not supported: kiro-cli/ACP exposes no embeddings model."""
    raise HTTPException(
        status_code=501,
        detail=(
            "Embeddings are not supported by this gateway. The compliant ACP "
            "path (kiro-cli) provides only text generation and exposes no "
            "embeddings model. Use a dedicated embeddings provider for vector "
            "generation."
        ),
    )
