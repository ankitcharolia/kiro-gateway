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
        tools: Optional[list[dict]] = None,
        filesystem_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
    ) -> dict[str, Any]:
        """
        Run a full non-streaming completion.

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
            tools=tools or [],
            stream=False,
        )
        result = await self._acp.prompt(params)
        return self._normalize_result(result)

    # ------------------------------------------------------------------
    # Streaming completion
    # ------------------------------------------------------------------

    async def stream_tokens(
        self,
        messages: list[PromptMessage],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[list[dict]] = None,
        filesystem_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream normalised ACP events to the caller as they arrive.

        Each yielded item is a plain dict with a ``type`` of ``text``,
        ``thinking``, ``tool_call``, ``done`` or ``error``.
        """
        session_id = await self._new_session(filesystem_roots, terminal, model)
        params = PromptParams(
            session_id=session_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools or [],
            stream=True,
        )
        async for event in self._acp.prompt_stream(params):
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
        tools: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """Submit tool results to an existing session and get the follow-up."""
        params = PromptParams(
            session_id=session_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools or [],
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
