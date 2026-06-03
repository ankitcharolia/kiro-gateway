# -*- coding: utf-8 -*-
"""
ShimService — shared orchestration for OpenAI and Anthropic shims.

Handles:
  1. Real-time streaming: ACP progress events are yielded token-by-token,
     not buffered. Shim routes call stream_tokens() and translate events
     to SSE on the fly.

  2. Tool-calling round-trips: tool_use events from kiro-cli are collected,
     translated to the caller's format (OpenAI function_call / Anthropic
     tool_use), and the caller's tool_result is injected back as a follow-up
     session/prompt so kiro-cli sees the result.

  3. Capability mediation: readFile, writeFile, runCommand, listDirectory
     requests from kiro-cli are handled by CapabilityExecutor when no native
     ACP client is present.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

from loguru import logger

from kiro.acp_client import ACPClient, ACPError
from kiro.acp_models import (
    PromptParams, PromptMessage, ProgressParams,
    ToolCall, ToolResult,
    FilesystemRoot, TerminalCapability, GatewayCapabilities,
)
from kiro.capability_executor import CapabilityExecutor, CapabilityError


class ShimService:
    """
    Stateless service layer shared by OpenAI and Anthropic shim routes.
    One instance lives on app.state and is used concurrently.
    """

    def __init__(
        self,
        acp_client: ACPClient,
        filesystem_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
    ):
        self._acp = acp_client
        self._capability_executor = CapabilityExecutor(
            filesystem_roots=filesystem_roots or [],
            terminal=terminal,
        )

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
        Run a full non-streaming completion including any tool-call round-trips.
        Returns a dict with: content, tool_calls, finish_reason, usage.
        """
        session_id = await self._new_session(filesystem_roots, terminal)

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
    ) -> AsyncIterator[ProgressParams]:
        """
        Stream ACP progress events directly to the caller.

        Events are yielded as they arrive from kiro-cli — no buffering.
        The caller (OpenAI/Anthropic shim route) translates each event
        to the appropriate SSE format on the fly.

        Capability requests that arrive during streaming are handled
        transparently by CapabilityExecutor. They never interrupt the
        token stream from the caller's perspective.
        """
        session_id = await self._new_session(filesystem_roots, terminal)

        params = PromptParams(
            session_id=session_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools or [],
            stream=True,
        )

        # Run capability handling concurrently with the main stream
        cap_task = asyncio.create_task(
            self._handle_capabilities_during_stream(session_id)
        )

        try:
            async for event in self._acp.prompt_stream(params):
                yield event
        finally:
            cap_task.cancel()
            try:
                await cap_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Tool-call round-trip (non-streaming)
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
        """
        Submit tool results back to an existing session and get the
        follow-up completion.
        """
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

    async def _new_session(self, fs_roots=None, terminal=None) -> str:
        caps = GatewayCapabilities(
            filesystem=fs_roots or [],
            terminal=terminal,
        )
        return await self._acp.new_session(caps)

    async def _handle_capabilities_during_stream(self, session_id: str) -> None:
        """
        Drain capability requests from kiro-cli and execute them via
        CapabilityExecutor during a streaming prompt.
        """
        try:
            async for method, req_id, params in self._acp.capability_requests(session_id):
                try:
                    result = await self._capability_executor.handle(method, params)
                    await self._acp.send_capability_result(req_id, result)
                except CapabilityError as e:
                    await self._acp.send_capability_error(req_id, e.code, str(e))
                except Exception as e:
                    await self._acp.send_capability_error(req_id, -32000, str(e))
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _normalize_result(result: Any) -> dict[str, Any]:
        """Normalize an ACP prompt result dict into a standard internal shape."""
        if isinstance(result, dict):
            return {
                "content": result.get("content", ""),
                "tool_calls": result.get("tool_calls", []),
                "finish_reason": result.get("finish_reason", "stop"),
                "usage": result.get("usage", {}),
            }
        # Fallback: result may be a string content directly
        return {"content": str(result), "tool_calls": [], "finish_reason": "stop", "usage": {}}
