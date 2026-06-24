# -*- coding: utf-8 -*-
"""
ShimService — shared orchestration for the OpenAI, Anthropic and ACP routes.

Responsibilities
----------------
1. Session lifecycle: create a fresh ACP session per request (via
   ``ACPClient.new_session``) so concurrent requests stay isolated.

2. Real-time streaming: ``stream_tokens`` yields the ACP client's normalised
   dict events (text / thinking / tool_call / done / error) as they arrive.
   The shim routes translate them to OpenAI or Anthropic SSE on the fly.

3. Non-streaming completion: ``complete`` aggregates the same pipeline into a
   single response dict.

Permission and tool execution are handled inside ``ACPClient`` (kiro-cli runs
its own built-in tools and asks the gateway only for permission), so this
layer no longer mediates capabilities directly.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from loguru import logger

from kiro.acp_client import ACPClient
from kiro.acp_models import (
    PromptParams, PromptMessage,
    ToolResult,
    FilesystemRoot, TerminalCapability, GatewayCapabilities,
)


def normalize_tool_definitions(tools: Optional[list[Any]]) -> list[dict]:
    """Normalise heterogeneous tool definitions to the ACP tool-definition shape.

    Callers reach the gateway through several APIs, each with its own tool
    encoding:

    * OpenAI chat completions — ``{"type": "function", "function": {"name",
      "description", "parameters"}}`` (nested, no top-level ``name``).
    * OpenAI Responses — ``{"type": "function", "name", "description",
      "parameters"}`` (flat).
    * Anthropic — ``{"name", "description", "input_schema"}``.
    * Native ACP — :class:`ACPToolDefinition` models / equivalent dicts.

    :class:`~kiro.acp_models.PromptParams` validates ``tools`` as
    :class:`~kiro.acp_models.ACPToolDefinition`, which requires a top-level
    ``name`` and uses ``input_schema``. Passing an OpenAI-nested tool dict
    straight through therefore raises a Pydantic ``ValidationError`` ("Field
    required: tools.N.name"). This helper flattens every supported shape into
    ``{"name", "description", "input_schema"}`` so all routes share one safe
    code path.

    Args:
        tools: Tool definitions as dicts or Pydantic models, in any of the
            supported encodings, or ``None``.

    Returns:
        A list of dicts with top-level ``name``/``description``/``input_schema``
        that satisfy :class:`ACPToolDefinition`. Entries without a resolvable
        name are skipped. Returns an empty list when ``tools`` is falsy.
    """
    if not tools:
        return []

    normalized: list[dict] = []
    for tool in tools:
        # Pydantic models (e.g. ACPToolDefinition, OAITool) → plain dict.
        if hasattr(tool, "model_dump"):
            tool = tool.model_dump()
        if not isinstance(tool, dict):
            logger.debug(f"Skipping non-dict tool definition: {type(tool)!r}")
            continue

        # OpenAI chat completions nests the definition under "function".
        nested = tool.get("function")
        source = nested if isinstance(nested, dict) else tool

        name = source.get("name") or tool.get("name") or ""
        if not name:
            logger.debug("Skipping tool definition without a name")
            continue

        description = source.get("description") or tool.get("description") or ""
        input_schema = (
            source.get("input_schema")
            or source.get("parameters")
            or tool.get("input_schema")
            or tool.get("parameters")
            or {}
        )

        normalized.append({
            "name": name,
            "description": description,
            "input_schema": input_schema,
        })

    return normalized


class ShimService:
    """Stateless orchestration layer shared by all route families."""

    def __init__(
        self,
        acp_client: ACPClient,
        filesystem_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
    ):
        self._acp = acp_client
        self._default_fs_roots = filesystem_roots or []
        self._default_terminal = terminal

    # ------------------------------------------------------------------
    # Non-streaming completion
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[PromptMessage],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        stop: Optional[list[str]] = None,
        tools: Optional[list[dict]] = None,
        filesystem_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
        surface_tool_calls: bool = True,
    ) -> dict[str, Any]:
        """
        Run a full non-streaming completion.

        Args:
            surface_tool_calls: When ``False``, kiro-cli's own built-in tool
                calls are not exposed in the result (``tool_calls`` is emptied).
                kiro-cli still runs those tools internally and the final text is
                unaffected — they are simply not presented as client-executable
                tool calls. Used by the OpenAI/Anthropic shims (default off via
                ``ACP_SURFACE_TOOL_CALLS``) so harnesses are not asked to execute
                tools they never declared. The ACP-native route leaves this
                ``True``.

        Returns:
            {"content": str, "tool_calls": list[dict],
             "finish_reason": str, "usage": dict}
        """
        session_id = await self._new_session(filesystem_roots, terminal, model)
        params = PromptParams(
            session_id=session_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            stop=stop,
            tools=normalize_tool_definitions(tools),
            stream=False,
        )
        result = await self._acp.prompt(params)
        normalized = self._normalize_result(result)
        if not surface_tool_calls:
            normalized["tool_calls"] = []
        return normalized

    # ------------------------------------------------------------------
    # Streaming completion
    # ------------------------------------------------------------------

    async def stream_tokens(
        self,
        messages: list[PromptMessage],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        stop: Optional[list[str]] = None,
        tools: Optional[list[dict]] = None,
        filesystem_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
        surface_tool_calls: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream normalised ACP events to the caller as they arrive.

        Each yielded item is a plain dict with a ``type`` of ``text``,
        ``thinking``, ``tool_call``, ``done`` or ``error``.

        Args:
            surface_tool_calls: When ``False``, ``tool_call`` events (kiro-cli's
                own built-in tool activity) are filtered out of the stream.
                kiro-cli still executes those tools internally and the streamed
                ``text``/``done`` events are unaffected. The OpenAI/Anthropic
                shims pass ``False`` by default (``ACP_SURFACE_TOOL_CALLS``) so a
                harness is never handed a tool call it cannot execute; the
                ACP-native route leaves this ``True``.
        """
        session_id = await self._new_session(filesystem_roots, terminal, model)
        params = PromptParams(
            session_id=session_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            stop=stop,
            tools=normalize_tool_definitions(tools),
            stream=True,
        )
        async for event in self._acp.prompt_stream(params):
            if not surface_tool_calls and event.get("type") == "tool_call":
                continue
            yield event

    # ------------------------------------------------------------------
    # Tool-result round-trip (non-streaming)
    # ------------------------------------------------------------------

    async def complete_with_tools(
        self,
        messages: list[PromptMessage],
        tool_results: list[ToolResult],
        session_id: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        stop: Optional[list[str]] = None,
        tools: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """Submit tool results to an existing session and get the follow-up."""
        params = PromptParams(
            session_id=session_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            stop=stop,
            tools=normalize_tool_definitions(tools),
            tool_results=tool_results,
            stream=False,
        )
        result = await self._acp.prompt(params)
        return self._normalize_result(result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _new_session(
        self,
        fs_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
        model: Optional[str] = None,
    ) -> str:
        caps = GatewayCapabilities(
            filesystem=fs_roots or self._default_fs_roots or [],
            terminal=terminal or self._default_terminal,
        )
        return await self._acp.new_session(caps, model=model)

    def available_models(self) -> list[dict]:
        """Return the live model catalogue discovered from kiro-cli sessions.

        Returns:
            A list of ``{"id", "name", "description"}`` dicts, or an empty list
            if no session has been created yet (callers fall back to the
            configured default model list in that case).
        """
        return self._acp.available_models

    @staticmethod
    def _normalize_result(result: Any) -> dict[str, Any]:
        """Coerce an ACP prompt result into the standard internal shape."""
        if isinstance(result, dict):
            return {
                "content": result.get("content", ""),
                "tool_calls": result.get("tool_calls", []),
                "finish_reason": result.get("finish_reason", "stop"),
                "usage": result.get("usage", {}),
            }
        return {"content": str(result), "tool_calls": [], "finish_reason": "stop", "usage": {}}
