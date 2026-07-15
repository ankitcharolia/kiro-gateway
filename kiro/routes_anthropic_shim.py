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
import re as _re
import time
import uuid
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from kiro.acp_models import PromptMessage, ToolResult, FilesystemRoot, TerminalCapability
from kiro.workspace import build_filesystem_roots, WORKSPACE_HEADER
from kiro.acp_client import format_plan_text
from kiro.auth import verify_anthropic_key
from kiro.config import DEFAULT_KIRO_MODELS, settings
from kiro.error_mapping import MappedError, classify_event, classify_exception
from kiro.model_validation import ModelNotAvailableError, resolve_alias, validate_model
from kiro.multimodal import anthropic_block_to_blocks, collapse_blocks
from kiro.shim_service import ShimService
from kiro.tokenizer import estimate_request_tokens, normalize_usage

router = APIRouter(tags=["Anthropic Shim"])

_INVALID_TOOL_NAME_CHARS = _re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize_tool_name(name: str) -> str:
    """Sanitize a tool name to be a valid Anthropic tool-use name.

    kiro-cli's built-in tools emit descriptive titles like "Running: ls -la /tmp"
    or "Reading listing tmp" as tool names. Anthropic requires names matching
    ``^[a-zA-Z0-9_-]+$``; invalid characters are replaced with ``_`` and
    consecutive underscores are collapsed.

    Args:
        name: Raw tool call title from kiro-cli.

    Returns:
        Sanitized, API-valid tool name (falls back to ``kiro_tool`` when the
        result is empty after cleaning).
    """
    if not name:
        return "kiro_tool"
    sanitized = _INVALID_TOOL_NAME_CHARS.sub("_", name)
    sanitized = _re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "kiro_tool"


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
    # Tool-selection control (issue #35): ``{"type": "auto"|"any"|"tool",
    # "name"?}``. The Anthropic Messages API has no ``response_format`` field
    # (structured output is expressed through tools), so only ``tool_choice`` is
    # accepted here. It is forwarded under the schema-safe ACP _meta extension
    # but is inert on kiro-cli today (no tool-choice capability over ACP), so a
    # request carrying it validates and succeeds; it takes effect automatically
    # if a future kiro-cli honors it.
    tool_choice: Optional[Any] = None
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

    Any ``cache_control`` markers are accepted but **not acted upon**: prompt
    caching is not part of the ACP path (kiro-cli advertises no caching
    capability), so the markers are a documented no-op rather than an error.
    Cache-token fields are still reported (as 0) in the ``usage`` object — see
    the "Prompt caching" docs.

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
    """Convert an Anthropic message list (+ ``system``) to ACP messages.

    Role provenance is preserved rather than flattened to anonymous user text:
    the ``system`` field becomes a distinct ``system`` role, and each message
    keeps its ``user``/``assistant`` role. Structured content blocks are
    rendered faithfully into the per-turn text so multi-turn, tool-heavy
    histories survive the serialisation (issue #43):

    * ``text`` blocks contribute their text.
    * ``image`` blocks with a base64 source → forwarded as ACP image blocks
      (kiro-cli supports images); ``url`` sources are surfaced as text.
    * ``document`` blocks → extracted to text when text/PDF, else placeholdered
      (kiro-cli has no embedded-document capability) — never silently dropped
      (issue #33, see :mod:`kiro.multimodal`).
    * ``tool_use`` blocks → ``[tool_use id=… name=…]`` + the call input JSON.
    * ``tool_result`` blocks → ``[tool_result id=…]`` + the result content.

    These markers match the OpenAI shim's, so the transcript ACP receives is
    consistent across both APIs. The blocks are role-less at the protocol level
    (see :func:`ACPClient._build_prompt_blocks`), so the labels/markers are the
    faithful maximum ACP allows.

    Args:
        messages: The Anthropic request messages.
        system: The raw ``system`` field (string, block list, or ``None``).

    Returns:
        A list of :class:`PromptMessage` preserving role and tool provenance.
    """
    result = []
    system_text = _system_to_text(system)
    if system_text:
        # Preserve the system prompt as a distinct system role. ACP has no
        # dedicated system channel, so the prompt serialiser renders it with a
        # ``System:`` label — faithful to its provenance, instead of the older
        # ad-hoc ``[system]`` prefix on a user turn.
        result.append(PromptMessage(role="system", content=system_text))

    for m in messages:
        role = "user" if m.role == "user" else "assistant"

        if isinstance(m.content, str):
            result.append(PromptMessage(role=role, content=m.content))
            continue

        if isinstance(m.content, list):
            # Normalise content blocks via the shared multimodal helper: text
            # and tool_use/tool_result render to the same markers as the OpenAI
            # shim; base64 ``image`` blocks are forwarded as ACP image blocks;
            # ``document`` blocks are extracted to text (or placeholdered) and
            # ``url`` sources surfaced as text — never silently dropped
            # (issue #33). Image-bearing content stays a block list for
            # ACPClient._build_prompt_blocks; otherwise it collapses to a string.
            blocks: list[dict] = []
            for part in m.content:
                blocks.extend(anthropic_block_to_blocks(part))
            result.append(PromptMessage(role=role, content=collapse_blocks(blocks)))

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


def _normalise_model_id(model_id: str) -> str:
    """Normalise a kiro-cli model ID for external API clients.

    Dotted minor versions are converted to hyphenated form
    (``claude-opus-4.8`` → ``claude-opus-4-8``) so Claude Code 2.x doesn't
    trigger its retirement check.  ``auto`` is returned unchanged.

    A separate ``claude-auto`` entry is injected by ``list_models`` alongside
    ``auto`` so Claude Code's ``^(claude|anthropic)`` discovery filter also
    picks it up in the ``/model`` picker.

    Args:
        model_id: Raw model ID from kiro-cli.

    Returns:
        Normalised model ID safe for external clients.
    """
    import re
    return re.sub(r'\.(\d+)$', r'-\1', model_id)


def _anthropic_error_response(mapped: MappedError) -> JSONResponse:
    """Build a native Anthropic error ``JSONResponse`` from a classified error.

    Args:
        mapped: The classified error carrying the status code, message, native
            ``type`` and optional ``Retry-After`` hint.

    Returns:
        A :class:`JSONResponse` with the Anthropic ``{"type": "error",
        "error": {...}}`` body, the mapped HTTP status code, and a
        ``Retry-After`` header when available.
    """
    return JSONResponse(
        status_code=mapped.status_code,
        content=mapped.to_anthropic_error(),
        headers=mapped.headers(),
    )


def _anthropic_model_not_found(exc: ModelNotAvailableError) -> JSONResponse:
    """Build a native Anthropic ``404 not_found_error`` response (issue #42)."""
    return JSONResponse(
        status_code=404,
        content={"type": "error", "error": {"type": "not_found_error", "message": str(exc)}},
    )


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
                "id": _normalise_model_id(m["id"]),
                "display_name": m.get("name") or m["id"],
            }
            for m in live
        ]
    else:
        data = [
            {"type": "model", "id": _normalise_model_id(model_id), "display_name": model_id}
            for model_id in DEFAULT_KIRO_MODELS
        ]
    # Claude Code's gateway discovery filter only accepts ^(claude|anthropic) ids.
    # Inject claude-auto alongside auto so it appears in Claude Code's /model picker
    # while other harnesses keep the plain auto entry.
    if any(m["id"] == "auto" for m in data):
        data.append({"type": "model", "id": "claude-auto", "display_name": "auto"})
    return {"data": data}


@router.get("/models/{model_id:path}")
async def retrieve_model(model_id: str, shim: ShimService = Depends(_get_shim)):
    """Retrieve a single model object (Anthropic ``GET /v1/models/{model}``).

    Permissive like the listing: the gateway forwards any model id to kiro-cli,
    so this returns a valid model object for the requested id, using the live
    catalogue's ``display_name`` when known. ``{model_id:path}`` accepts ids
    containing slashes.

    Args:
        model_id: The requested model id.
        shim: The shared ShimService (for the live catalogue).

    Returns:
        An Anthropic model object ``{"type": "model", "id", "display_name"}``.
    """
    display_name = model_id
    for entry in shim.available_models():
        if entry.get("id") == model_id:
            display_name = entry.get("name") or model_id
            break
    return {"type": "model", "id": model_id, "display_name": display_name}


# ---------------------------------------------------------------------------
# POST /v1/messages
# ---------------------------------------------------------------------------

@router.post("/messages", dependencies=[Depends(verify_anthropic_key)])
async def create_message(
    body: AnthropicRequest,
    request: Request,
    shim: ShimService = Depends(_get_shim),
):
    # Resolve any configured model alias, then validate up front (issues #42,
    # #32): clean 404 for both streaming and non-streaming.
    body.model = resolve_alias(body.model, settings.MODEL_ALIASES) or body.model
    try:
        validate_model(body.model, shim.available_models(), settings.MODEL_VALIDATION)
    except ModelNotAvailableError as exc:
        return _anthropic_model_not_found(exc)
    messages = _anthropic_messages_to_acp(body.messages, body.system)
    tools = _anthropic_tools_to_acp(body.tools or [])
    fs_roots = build_filesystem_roots(
        request.headers.get(WORKSPACE_HEADER), body.filesystem_roots, messages
    )
    terminal = TerminalCapability(**body.terminal) if body.terminal else None
    stop = body.stop_sequences or None

    if body.stream:
        return StreamingResponse(
            _stream_response(shim, messages, body.model, body.max_tokens,
                             body.temperature, body.top_p, body.top_k, stop,
                             tools, fs_roots, terminal, body.tool_choice),
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
            tool_choice=body.tool_choice,
            filesystem_roots=fs_roots,
            terminal=terminal,
            surface_tool_calls=settings.ACP_SURFACE_TOOL_CALLS,
            surface_thinking=settings.ACP_SURFACE_THINKING,
        )
    except Exception as exc:
        mapped = classify_exception(exc)
        logger.error(
            f"Anthropic shim complete error (status={mapped.status_code}): {exc}"
        )
        return _anthropic_error_response(mapped)

    content_blocks: list[dict] = []
    reasoning = result.get("reasoning") or ""
    if settings.ACP_SURFACE_THINKING and reasoning:
        # Anthropic extended-thinking block, emitted before the text block.
        content_blocks.append({"type": "thinking", "thinking": reasoning})
    if result["content"]:
        content_blocks.append({"type": "text", "text": result["content"]})
    for tc in result.get("tool_calls", []):
        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", str(uuid.uuid4())),
            "name": _sanitize_tool_name(tc.get("name", "")),
            "input": tc.get("arguments", {}),
        })

    if result.get("tool_calls") and not result["content"]:
        # Only use stop_reason=tool_use when tool calls are present AND no text
        # content was produced. When kiro-cli runs its own built-in tools and
        # then streams a text answer, both are present — in that case the turn
        # is complete and the harness must not loop waiting for tool results.
        stop_reason = "tool_use"
    else:
        # Map the internal finish_reason to Anthropic vocabulary so gateway-side
        # max_tokens/stop enforcement (issue #32) is reported faithfully.
        _fr = result.get("finish_reason") or "end_turn"
        stop_reason = {"length": "max_tokens", "stop": "end_turn"}.get(_fr, "end_turn")

    usage = normalize_usage(
        result.get("usage"),
        prompt_messages=[{"role": m.role, "content": m.content} for m in body.messages],
        prompt_tools=tools,
        prompt_system=body.system,
        completion_text=result.get("content") or "",
        completion_tool_calls=result.get("tool_calls"),
    )

    usage_obj: dict[str, Any] = {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        # Prompt caching is a no-op over ACP (kiro-cli exposes no caching
        # mechanism), so these are 0 today. They are reported — rather than
        # omitted — to keep the usage object faithful to the native
        # Anthropic shape, and surface real counts if a future kiro-cli
        # reports them. See the "Prompt caching" docs.
        "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
        "cache_read_input_tokens": usage["cache_read_input_tokens"],
    }
    # Additive: real usage/cost/context metadata kiro-cli reported (credits,
    # context %, turn duration, v3 token breakdown). Present only when non-empty
    # so the native usage shape is unchanged when kiro-cli reports nothing.
    kiro_metadata = result.get("metadata") or {}
    if kiro_metadata:
        usage_obj["kiro_metadata"] = kiro_metadata

    return {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": body.model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage_obj,
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
    tool_choice: Optional[Any] = None,
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
    # Estimate input tokens up front so message_start carries a real count
    # (kiro-cli does not report usage on the prompt result today). Output
    # tokens are estimated from the accumulated text/tool calls at the end.
    input_tokens = estimate_request_tokens(
        [{"role": m.role, "content": m.content} for m in messages],
        tools=tools or None,
    )
    block_idx = 0
    in_text_block = False
    in_thinking_block = False
    active_tool_blocks: dict[str, int] = {}  # tool_call_id -> block_index
    # Accumulators for the output-token estimate emitted at message_delta.
    text_acc: list[str] = []
    collected_tool_calls: dict[str, dict] = {}  # tool_call_id -> {name, arguments}

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
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 0,
                # Prompt caching is a no-op over ACP, so cache tokens are 0;
                # reported for shape-parity with the native Anthropic API
                # (see the "Prompt caching" docs).
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
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
            tool_choice=tool_choice,
            filesystem_roots=fs_roots,
            terminal=terminal,
            surface_tool_calls=settings.ACP_SURFACE_TOOL_CALLS,
            surface_thinking=settings.ACP_SURFACE_THINKING,
        ):
            etype = event.get("type")
            if etype == "plan":
                event = {"type": "thinking",
                         "content": format_plan_text(event.get("entries", []),
                                                     event.get("description", ""))}
                etype = "thinking"

            if etype == "text":
                delta = event.get("content", "")
                if not delta:
                    continue
                if in_thinking_block:
                    # Close the thinking block before the text block opens.
                    yield sse("content_block_stop", {"type": "content_block_stop", "index": block_idx})
                    block_idx += 1
                    in_thinking_block = False
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
                text_acc.append(delta)

            elif etype == "thinking":
                # Surface reasoning as an Anthropic extended-thinking block
                # (content_block_start[thinking] + thinking_delta), when enabled.
                if settings.ACP_SURFACE_THINKING:
                    delta = event.get("content", "")
                    if delta:
                        if not in_thinking_block:
                            yield sse("content_block_start", {
                                "type": "content_block_start",
                                "index": block_idx,
                                "content_block": {"type": "thinking", "thinking": ""},
                            })
                            in_thinking_block = True
                        yield sse("content_block_delta", {
                            "type": "content_block_delta",
                            "index": block_idx,
                            "delta": {"type": "thinking_delta", "thinking": delta},
                        })
                continue

            elif etype == "tool_call":
                tc_id = event.get("id", str(uuid.uuid4()))
                name = _sanitize_tool_name(event.get("name", ""))
                arguments = event.get("arguments", {})
                collected_tool_calls[tc_id] = {"name": name, "arguments": arguments}

                if tc_id not in active_tool_blocks:
                    # Close the thinking block if open
                    if in_thinking_block:
                        yield sse("content_block_stop", {"type": "content_block_stop", "index": block_idx})
                        block_idx += 1
                        in_thinking_block = False
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
                # Close open thinking or text block.
                if in_thinking_block:
                    yield sse("content_block_stop", {"type": "content_block_stop", "index": block_idx})
                if in_text_block:
                    yield sse("content_block_stop", {"type": "content_block_stop", "index": block_idx})

                usage = event.get("usage", {}) or {}
                # Only use stop_reason=tool_use when tool blocks were emitted AND
                # no text content was streamed. When kiro-cli runs its own built-in
                # tools and then produces a text answer, active_tool_blocks is
                # non-empty but the turn is complete — returning tool_use would
                # cause Claude Code / Kilo Code to loop waiting for tool results
                # that kiro-cli already resolved internally.
                stop_reason = "tool_use" if active_tool_blocks and not text_acc else (
                    event.get("finish_reason") or "end_turn"
                )
                # Normalise OpenAI-style finish reasons to Anthropic vocabulary.
                if stop_reason == "stop":
                    stop_reason = "end_turn"
                elif stop_reason == "length":
                    stop_reason = "max_tokens"

                # Prefer a count reported by kiro-cli; otherwise estimate from
                # the accumulated output text and tool calls (consistent with
                # the input estimate emitted in message_start).
                output_usage = normalize_usage(
                    usage,
                    completion_text="".join(text_acc),
                    completion_tool_calls=list(collected_tool_calls.values()),
                )
                yield sse("message_delta", {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": stop_reason,
                        "stop_sequence": None,
                    },
                    "usage": {
                        "output_tokens": output_usage["output_tokens"],
                        # Additive: real usage/cost/context metadata kiro-cli
                        # reported. Omitted when empty (native shape unchanged).
                        **({"kiro_metadata": event["metadata"]} if event.get("metadata") else {}),
                    },
                })
                yield sse("message_stop", {"type": "message_stop"})
                break

            elif etype == "error":
                mapped = classify_event(event)
                yield sse("error", {
                    "type": "error",
                    "error": {
                        "type": mapped.anthropic_type,
                        "message": mapped.message,
                    },
                })
                break

    except Exception as exc:
        mapped = classify_exception(exc)
        logger.error(f"Anthropic stream error (status={mapped.status_code}): {exc}")
        yield sse("error", {
            "type": "error",
            "error": {"type": mapped.anthropic_type, "message": mapped.message},
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
