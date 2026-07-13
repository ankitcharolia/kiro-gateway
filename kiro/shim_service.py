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

from kiro.acp_client import ACPClient, render_tool_activity, render_tool_call_summary
from kiro.config import settings
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

        # Preserve an OpenAI "strict" tool-schema flag when present (structured
        # tool outputs, issue #35). It is inert on kiro-cli today (client tools
        # are not honored over ACP) but is forwarded under _meta.tools so the
        # wire request carries the caller's intent and a future kiro-cli can act
        # on it.
        strict = source.get("strict")
        if strict is None:
            strict = tool.get("strict")
        if strict is not None:
            normalized[-1]["strict"] = strict

    return normalized


# Canonical tool-name candidates keyed by the ACP tool ``kind``. Ordered by
# preference; the first is used as the surfaced name when the caller declared no
# matching tool. Verified against a live kiro-cli 2.12.1 probe: kiro surfaces
# its built-in tools with a prose ``title`` ("Running: echo …", "Reading
# README.md:1-5") — useless as an OpenAI/Anthropic function name — and a stable
# ``kind`` (``execute``/``read``/``edit``/``search``/``fetch``/…). ``kind`` is
# therefore the reliable signal for mapping onto a recognisable tool name.
_KIND_TO_CANONICAL: dict[str, tuple[str, ...]] = {
    "read": ("read",),
    "edit": ("edit", "write", "apply_patch"),
    "delete": ("delete", "remove"),
    "move": ("move", "rename"),
    "execute": ("bash", "shell", "execute_command", "run_command"),
    "search": ("grep", "search", "glob"),
    "fetch": ("web_fetch", "web_search", "fetch"),
    "think": ("think",),
}


def _norm_ident(name: str) -> str:
    """Reduce a tool name to lowercase alphanumerics for fuzzy comparison.

    ``WebFetch`` / ``web_fetch`` / ``web-fetch`` all normalise to ``webfetch``
    so a caller's tool name matches a canonical candidate regardless of case or
    separator style.

    Args:
        name: A tool name.

    Returns:
        The lowercase alphanumeric-only form.
    """
    import re as _re
    return _re.sub(r"[^a-z0-9]", "", name.lower())


def map_kiro_tool_call(tool_call: dict, declared_tools: Optional[list[dict]]) -> dict:
    """Map a kiro-cli built-in tool call onto the caller's declared tool schema.

    kiro-cli runs its own built-in tools and surfaces each as a tool-call event
    whose ``name`` is a prose ``title`` (e.g. ``"Reading README.md:1-5"``) and
    whose ``kind`` is a stable verb (``read``/``edit``/``execute``/``search``/
    ``fetch``/…). When the shims surface tool activity as executable
    ``tool_calls``/``tool_use`` (``ACP_SURFACE_TOOL_CALLS=true``), that prose
    title is not a name a harness recognises. This maps the call onto a clean,
    recognisable tool name — preferring the caller's own declared tool when one
    matches the call's ``kind`` (so a harness that declared ``Read``/``Bash``
    sees those names), otherwise a canonical fallback (``read``/``bash``/…).

    The internal ``__tool_use_purpose`` argument kiro-cli adds is stripped so
    the surfaced ``arguments`` match a normal tool-call payload.

    Best-effort and non-authoritative: kiro's tool taxonomy does not line up
    1:1 with an arbitrary harness's, and these calls are already executed by
    kiro-cli within the turn (the turn still finishes with
    ``finish_reason=stop`` when text follows), so this is a display/naming
    normalisation, not a client-side function-calling round-trip (issue #31).
    When the call carries no usable ``kind`` (e.g. a bare update), the original
    name is left untouched for the route's own sanitiser to handle.

    Args:
        tool_call: A normalised ``tool_call``/``tool_call_update`` event (dict).
        declared_tools: The caller's declared tools in the ``{"name", …}`` shape
            produced by :func:`normalize_tool_definitions` (may be empty/None).

    Returns:
        A shallow copy of ``tool_call`` with ``name`` remapped (when a mapping
        applies) and the internal purpose key removed from ``arguments``.
    """
    mapped = dict(tool_call)

    # Strip kiro's internal purpose key from the surfaced arguments.
    args = mapped.get("arguments")
    if isinstance(args, dict) and "__tool_use_purpose" in args:
        mapped["arguments"] = {
            key: value for key, value in args.items() if key != "__tool_use_purpose"
        }

    kind = str(mapped.get("kind") or "").strip().lower()
    candidates = _KIND_TO_CANONICAL.get(kind)
    if not candidates:
        # No stable kind to map on — leave the name for the route sanitiser.
        return mapped

    declared_norm: dict[str, str] = {}
    for tool in declared_tools or []:
        raw_name = tool.get("name") if isinstance(tool, dict) else None
        if raw_name:
            declared_norm.setdefault(_norm_ident(str(raw_name)), str(raw_name))

    # 1. Prefer an exact (normalised) match against a declared tool name.
    for cand in candidates:
        hit = declared_norm.get(_norm_ident(cand))
        if hit:
            mapped["name"] = hit
            return mapped
    # 2. Then a guarded containment match (e.g. declared "read_file" ⊇ "read").
    for cand in candidates:
        cnorm = _norm_ident(cand)
        if len(cnorm) < 3:
            continue
        for dnorm, orig in declared_norm.items():
            if cnorm in dnorm or dnorm in cnorm:
                mapped["name"] = orig
                return mapped
    # 3. No declared match: surface the canonical fallback name.
    mapped["name"] = candidates[0]
    return mapped


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
        response_format: Optional[dict] = None,
        tool_choice: Optional[Any] = None,
        filesystem_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
        surface_tool_calls: bool = True,
        surface_thinking: bool = True,
    ) -> dict[str, Any]:
        """
        Run a full non-streaming completion.

        Args:
            response_format: Optional structured-output control (OpenAI JSON
                mode / json_schema; inert on kiro-cli today, forwarded under
                _meta — see issue #35).
            tool_choice: Optional tool-selection control (inert on kiro-cli
                today, forwarded under _meta — see issue #35).
            surface_tool_calls: When ``True``, kiro-cli's built-in tool calls are
                returned in ``tool_calls`` for the caller to present as
                executable calls. When ``False`` (the shim default) they are not
                returned as executable calls; instead, when ``surface_thinking``
                is set, each is folded into ``reasoning`` as a one-line activity
                label so the agent's tool activity is visible (like kiro-cli)
                without a call the harness cannot run. kiro-cli executes the
                tools internally regardless; the final ``content`` is unchanged.
            surface_thinking: Whether the reasoning channel (thinking + folded
                tool activity) is surfaced.

        Returns:
            {"content": str, "reasoning": str, "tool_calls": list[dict],
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
            enforce_max_tokens=settings.ENFORCE_MAX_TOKENS,
            tools=normalize_tool_definitions(tools),
            response_format=response_format,
            tool_choice=tool_choice,
            stream=False,
        )
        result = await self._acp.prompt(params)
        normalized = self._normalize_result(result)
        if not surface_tool_calls:
            tool_calls = normalized.get("tool_calls") or []
            if surface_thinking and tool_calls:
                labels = "".join(
                    render_tool_call_summary(tc) for tc in tool_calls
                )
                if labels:
                    normalized["reasoning"] = (normalized.get("reasoning") or "") + labels
            normalized["tool_calls"] = []
        else:
            # Surfacing on: map kiro-cli's built-in tool calls onto the caller's
            # declared tool schema (or a canonical name) so a harness sees a
            # recognisable name instead of kiro's prose title.
            declared = normalize_tool_definitions(tools)
            normalized["tool_calls"] = [
                map_kiro_tool_call(tc, declared)
                for tc in (normalized.get("tool_calls") or [])
            ]
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
        response_format: Optional[dict] = None,
        tool_choice: Optional[Any] = None,
        filesystem_roots: Optional[list[FilesystemRoot]] = None,
        terminal: Optional[TerminalCapability] = None,
        surface_tool_calls: bool = True,
        surface_thinking: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream normalised ACP events to the caller as they arrive.

        Each yielded item is a plain dict with a ``type`` of ``text``,
        ``thinking``, ``tool_call``, ``plan``, ``done`` or ``error``.

        Args:
            response_format: Optional structured-output control (OpenAI JSON
                mode / json_schema; inert on kiro-cli today, forwarded under
                _meta — see issue #35).
            tool_choice: Optional tool-selection control (inert on kiro-cli
                today, forwarded under _meta — see issue #35).
            surface_tool_calls: When ``True``, kiro-cli's built-in ``tool_call``
                events pass through so the caller can present them as
                executable ``tool_calls``/``tool_use`` (or, on the ACP route, a
                structured ``acp_tool_call``). When ``False`` (the shim default),
                they are **not** passed through as executable calls — instead,
                when ``surface_thinking`` is set, each is converted into an inline
                ``thinking`` event (a one-line activity label) so harnesses see
                the agent's tool activity interleaved with its reasoning, like
                kiro-cli, without a tool call they cannot execute. Dropped when
                both are ``False``.
            surface_thinking: Whether kiro-cli's reasoning channel (thinking +
                folded tool activity) is surfaced.
        """
        session_id = await self._new_session(filesystem_roots, terminal, model)
        declared_tools = normalize_tool_definitions(tools)
        params = PromptParams(
            session_id=session_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            stop=stop,
            enforce_max_tokens=settings.ENFORCE_MAX_TOKENS,
            tools=normalize_tool_definitions(tools),
            response_format=response_format,
            tool_choice=tool_choice,
            stream=True,
        )
        async for event in self._acp.prompt_stream(params):
            etype = event.get("type")
            if etype in ("tool_call", "tool_call_update") and not surface_tool_calls:
                if surface_thinking:
                    label = render_tool_activity(event)
                    if label:
                        yield {"type": "thinking", "content": label}
                continue
            if etype in ("tool_call", "tool_call_update") and surface_tool_calls:
                # Map kiro-cli's built-in tool call onto the caller's declared
                # tool schema (or a canonical name) before surfacing it.
                yield map_kiro_tool_call(event, declared_tools)
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
        response_format: Optional[dict] = None,
        tool_choice: Optional[Any] = None,
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
            enforce_max_tokens=settings.ENFORCE_MAX_TOKENS,
            tools=normalize_tool_definitions(tools),
            response_format=response_format,
            tool_choice=tool_choice,
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
                "reasoning": result.get("reasoning", ""),
                "tool_calls": result.get("tool_calls", []),
                "finish_reason": result.get("finish_reason", "stop"),
                "usage": result.get("usage", {}),
                "metadata": result.get("metadata", {}),
            }
        return {"content": str(result), "reasoning": "", "tool_calls": [], "finish_reason": "stop", "usage": {}, "metadata": {}}
