# -*- coding: utf-8 -*-
"""
ACP client — manages a kiro-cli subprocess via the Agent Client Protocol
(ACP, the Zed JSON-RPC 2.0 protocol) over stdio.

Wire protocol (as implemented by `kiro-cli acp`, agent version 2.x):

  1. ``initialize`` (request, once per process)
       params:  {"protocolVersion": 1, "clientCapabilities": {...}}
       result:  {"protocolVersion", "agentCapabilities", "authMethods", ...}

  2. ``session/new`` (request, once per conversation)
       params:  {"cwd": "<abs path>", "mcpServers": []}
       result:  {"sessionId": "<uuid>", "modes": {...}}

  3. ``session/prompt`` (request, per user turn)
       params:  {"sessionId", "prompt": [{"type": "text", "text": "..."}]}
       result:  {"stopReason": "end_turn" | "max_tokens" | ...}

     While a prompt is in flight the agent emits ``session/update``
     notifications (no id) and may send ``session/request_permission``
     requests (with id) back to the gateway.

  4. ``session/cancel`` (notification, no id)
       params:  {"sessionId": "<uuid>"}
     Sent when the client abandons a turn (disconnect / cancelled request).
     The agent stops the current turn and returns the pending
     ``session/prompt`` result with ``stopReason: "cancelled"``. This frees
     the shared subprocess so a subsequent request is not head-of-line
     blocked by the abandoned turn.

``session/update`` payloads carry an ``update.sessionUpdate`` discriminator:
  - ``agent_message_chunk``   → assistant text delta
  - ``agent_thought_chunk``   → reasoning/thinking delta
  - ``tool_call``             → a tool invocation the agent is starting
  - ``tool_call_update``      → status change for a running tool call

The gateway translates these into a normalised internal event contract
(plain dicts) consumed by ShimService and the shim routes:
  - {"type": "text",      "content": str}
  - {"type": "thinking",  "content": str}
  - {"type": "tool_call", "id": str, "name": str, "arguments": dict}
  - {"type": "done",      "finish_reason": str, "usage": dict}
  - {"type": "error",     "message": str}
"""
from __future__ import annotations

import asyncio
import json
import os
import re as _re
import uuid
from asyncio import Queue
from typing import Any, AsyncIterator, Optional

from loguru import logger

from kiro.acp_models import (
    JsonRpcRequest, JsonRpcResponse,
    SessionInitResult,
    PromptParams,
    GatewayCapabilities,
)
from kiro.config import ACP_STDIO_MAX_BYTES
from kiro.output_limits import StreamLimiter


# Map ACP stopReason values to the gateway's normalised finish_reason.
_STOP_REASON_MAP: dict[str, str] = {
    "end_turn": "stop",
    "max_tokens": "length",
    "max_turn_requests": "length",
    "tool_use": "tool_calls",
    "refusal": "stop",
    "cancelled": "stop",
}


def format_plan_text(entries: list, description: str = "") -> str:
    """Render normalised plan entries into a human-readable checklist.

    Used to fold a task list into the reasoning channel for the OpenAI/Anthropic
    shims (the native ACP route surfaces the structured ``plan`` event instead).

    Args:
        entries: A list of ``{"content", "status"}`` dicts.
        description: Optional task-list title.

    Returns:
        A markdown checklist string, or ``""`` when there are no entries.
    """
    if not entries:
        return ""
    header = f"Plan — {description}" if description else "Plan"
    lines = [header]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        box = {"completed": "[x]", "in_progress": "[~]"}.get(entry.get("status"), "[ ]")
        lines.append(f"- {box} {entry.get('content', '')}")
    return "\n".join(lines)


def _render_diff(content: list) -> str:
    """Render ACP ``diff`` content blocks as a unified +/- diff body.

    Each diff block is ``{"type": "diff", "path", "oldText", "newText"}``.
    Removed lines are prefixed ``-``, added lines ``+`` — suitable for a
    fenced ```diff block so harness markdown renderers colour them red/green.

    Args:
        content: The ``content`` list from a tool call/update.

    Returns:
        The diff body (no fences), or ``""`` when there is no diff.
    """
    blocks: list[str] = []
    for block in content or []:
        if not isinstance(block, dict) or block.get("type") != "diff":
            continue
        old_text = block.get("oldText")
        new_text = block.get("newText")
        lines: list[str] = []
        if old_text:
            lines += [f"-{ln}" for ln in str(old_text).splitlines()]
        if new_text:
            lines += [f"+{ln}" for ln in str(new_text).splitlines()]
        if lines:
            blocks.append("\n".join(lines))
    return "\n".join(blocks)


_MAX_TOOL_OUTPUT = 4000

# rawInput keys worth showing as structured activity args (in order), skipping
# internal/huge fields (e.g. __tool_use_purpose, write `content`, todo `tasks`).
_ARG_KEYS = (
    "command", "pattern", "path", "include", "query", "url",
    "label", "operation_name", "service_name", "region", "profile_name",
)
# Values for these keys (or any path-like value) are wrapped in inline code so
# harness markdown renders them in a distinct colour from prose and output.
_CODE_KEYS = {"command", "pattern", "path", "include", "url"}


def _truncate(text: str, limit: int = _MAX_TOOL_OUTPUT) -> str:
    """Truncate long tool output for the reasoning channel."""
    text = text.rstrip()
    if len(text) > limit:
        return text[:limit] + "\n… (truncated)"
    return text


def _format_tool_args(arguments: dict) -> str:
    """Render a tool call's ``rawInput`` as indented activity sub-lines.

    Shows a curated set of meaningful keys; path/command/pattern values are
    wrapped in inline code so a harness highlights them distinctly from output.

    Args:
        arguments: The tool ``rawInput`` dict.

    Returns:
        Newline-joined ``  key=value`` lines, or ``""`` when nothing useful.
    """
    if not isinstance(arguments, dict):
        return ""
    lines: list[str] = []
    for key in _ARG_KEYS:
        value = arguments.get(key)
        if value in (None, "", {}, []):
            continue
        text = str(value)
        if key in _CODE_KEYS or "/" in text:
            text = f"`{text}`"
        lines.append(f"  {key}={text}")
    # File read/edit tools carry path(s) under `operations` rather than `path`.
    operations = arguments.get("operations")
    if isinstance(operations, list):
        for op in operations:
            if isinstance(op, dict) and op.get("path"):
                lines.append(f"  path=`{op['path']}`")
    return "\n".join(lines)


def _summarize_json_output(payload: Any) -> str:
    """Summarise a structured tool result into activity text.

    Handles the ``Json`` result shapes kiro-cli emits on a ``tool_call_update``:

    * **grep** — ``{"numMatches", "numFiles", …}`` → a one-line match summary.
    * **glob** — ``{"filePaths"|"totalFiles", …}`` → a one-line file-count summary.
    * **web_search** — ``{"results": [{"title", "url", "snippet"}, …]}`` → a short
      list of the top result titles/URLs. Verified against a live kiro-cli 2.12.0
      probe: web_search runs as a ``search``-kind tool whose result is this
      ``Json`` shape — without this branch the results are dropped from the
      activity view (inconsistent with grep/glob, which are summarised).
    * **execute (shell)** — ``{"exit_status", "stdout", "stderr"}`` → the command's
      stdout/stderr text, with a ``[exit: …]`` marker appended when the command
      failed (non-zero exit) so a failing command is visible even with no output.
      Verified against a live kiro-cli 2.12.0 probe: shell output (and ``use_aws``,
      which also runs as an ``execute``-kind tool) arrives as this ``Json`` shape,
      **not** as a ``Text`` item — so without this branch the output (and any
      failure) is silently dropped from the activity view.

    Args:
        payload: The ``Json`` value from a tool ``rawOutput`` item.

    Returns:
        The summary/output text, or ``""`` for shapes we don't render (avoids
        dumping arbitrary JSON into the reasoning stream).
    """
    if not isinstance(payload, dict):
        return ""
    if "numMatches" in payload:  # grep
        summary = (
            f"{payload.get('numMatches', 0)} match(es) in "
            f"{payload.get('numFiles', 0)} file(s)"
        )
        if payload.get("truncated"):
            summary += " (truncated)"
        return summary
    if "filePaths" in payload or "totalFiles" in payload:  # glob
        if payload.get("message"):
            return str(payload["message"])
        count = payload.get("totalFiles")
        if count is None:
            count = len(payload.get("filePaths") or [])
        return f"{count} file(s) found"
    # web_search: {"results": [{"title", "url", "snippet"}, ...]}. Checked after
    # grep (whose result items are file/matches, not title/url, and which is
    # caught by numMatches above) so the two never collide.
    results = payload.get("results")
    if (
        isinstance(results, list) and results
        and isinstance(results[0], dict)
        and ("title" in results[0] or "url" in results[0])
    ):
        lines = [f"{len(results)} result(s):"]
        for entry in results[:5]:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "").strip()
            url = str(entry.get("url") or "").strip()
            if title and url:
                lines.append(f"- {title} ({url})")
            elif title or url:
                lines.append(f"- {title or url}")
        return "\n".join(lines)
    # execute (shell): {"exit_status": "exit status: N", "stdout": ..., "stderr": ...}
    if "exit_status" in payload or "stdout" in payload or "stderr" in payload:
        stdout = str(payload.get("stdout") or "").rstrip()
        stderr = str(payload.get("stderr") or "").rstrip()
        segments = [seg for seg in (stdout, stderr) if seg]
        body = "\n".join(segments)
        exit_status = str(payload.get("exit_status") or "").strip()
        match = _re.search(r"-?\d+", exit_status)
        exit_code = int(match.group()) if match else 0
        if exit_code != 0:
            marker = f"[exit: {exit_code}]"
            body = f"{body}\n{marker}" if body else marker
        return body
    return ""


# Markdown inline-formatting characters that must be escaped inside a bold label.
# kiro-cli tool titles are prose that can embed glob patterns / paths (e.g.
# "Finding **/* in linkedin-agent"); interpolating them raw into ``**…**`` makes
# the embedded ``*``/`` ` ``/``~`` collide with the bold markers and leak stray
# literal asterisks into the reasoning channel. ``_`` is deliberately NOT escaped
# — it is not intraword emphasis in CommonMark and escaping it would mangle the
# many identifier-style titles/paths (``use_aws``, ``operation_name``).
_MD_ESCAPE = str.maketrans({c: f"\\{c}" for c in ("\\", "*", "`", "~")})


def _escape_md(text: str) -> str:
    """Escape markdown inline-formatting characters in a label.

    Backslash-escapes ``* ` ~`` (and the backslash itself) so a tool title
    containing glob/markdown characters cannot break the surrounding ``**…**``
    bold wrapping when rendered by a harness's markdown renderer. ``_`` is left
    as-is to avoid mangling identifier-style titles (``use_aws``).

    Args:
        text: The raw label text (a kiro-cli tool title).

    Returns:
        The text with markdown-special characters backslash-escaped.
    """
    return text.translate(_MD_ESCAPE)


def render_tool_activity(event: dict) -> str:
    """Render a streamed tool_call / tool_call_update event as reasoning text.

    Produces kiro-cli-style activity for the OpenAI/Anthropic reasoning channel:
    a bold ``⚙ <title>`` label, structured argument sub-lines (with paths/commands
    in inline code), a fenced ```diff block for file edits (added/removed lines),
    a result summary for searches (grep/glob), and a fenced output block for
    shell/command execution. File-read contents are not dumped.

    Args:
        event: A normalised ``tool_call`` or ``tool_call_update`` event.

    Returns:
        Reasoning text (with surrounding newlines), or ``""`` when nothing to show.
    """
    etype = event.get("type")
    kind = event.get("kind") or ""
    if etype == "tool_call":
        parts: list[str] = []
        name = (event.get("name") or "").strip()
        if name:
            parts.append(f"**⚙ {_escape_md(name)}**")
        args = _format_tool_args(event.get("arguments") or {})
        if args:
            parts.append(args)
        diff = _render_diff(event.get("content") or [])
        if diff:
            parts.append("```diff\n" + diff + "\n```")
        return ("\n" + "\n".join(parts) + "\n") if parts else ""
    if etype == "tool_call_update":
        output = (event.get("output") or "").strip()
        if not output:
            return ""
        if kind == "execute":  # shell command output → fenced block
            return "\n```\n" + _truncate(output) + "\n```\n"
        if kind == "search":   # grep/glob result summary → inline sub-line
            return f"\n  ↳ {_truncate(output, 500)}\n"
        return ""
    return ""


def render_tool_call_summary(tool_call: dict) -> str:
    """Render an aggregated (non-streaming) tool call as reasoning text.

    Non-streaming equivalent of :func:`render_tool_activity`: label + args +
    file-edit diff + (shell output / search summary).

    Args:
        tool_call: An aggregated tool call with ``name``/``kind``/``arguments``/
            ``content``/``output``.

    Returns:
        Reasoning text (with surrounding newlines), or ``""`` when empty.
    """
    parts: list[str] = []
    name = (tool_call.get("name") or "").strip()
    if name:
        parts.append(f"**⚙ {_escape_md(name)}**")
    args = _format_tool_args(tool_call.get("arguments") or {})
    if args:
        parts.append(args)
    diff = _render_diff(tool_call.get("content") or [])
    if diff:
        parts.append("```diff\n" + diff + "\n```")
    output = (tool_call.get("output") or "").strip()
    if output:
        if tool_call.get("kind") == "execute":
            parts.append("```\n" + _truncate(output) + "\n```")
        elif tool_call.get("kind") == "search":
            parts.append(f"  ↳ {_truncate(output, 500)}")
    return ("\n" + "\n".join(parts) + "\n") if parts else ""


class ACPError(Exception):
    """Raised when the agent returns a JSON-RPC error response."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class ACPClient:
    """
    Manages a single ``kiro-cli acp`` subprocess.

    Lifetime: created once per gateway process, shared across requests.
    Concurrency: coroutine-safe. ``initialize`` runs once at startup;
    ``new_session`` is called per request to obtain an isolated sessionId,
    so concurrent prompts never interfere.

    The ``command`` parameter maps directly to the ``KIRO_CLI_PATH`` env var.
    """

    def __init__(
        self,
        command: str = "kiro-cli",
        trust_tools: bool = True,
        stdio_limit: int = ACP_STDIO_MAX_BYTES,
        mode: Optional[str] = None,
        agent: Optional[str] = None,
        initial_model: Optional[str] = None,
        effort: Optional[str] = None,
        engine: str = "v2",
        extra_args: Optional[list[str]] = None,
        mcp_servers: Optional[list[dict]] = None,
        mcp_init_timeout: int = 30,
    ):
        self._command = command
        self._trust_tools = trust_tools
        # Optional ACP session "mode" (agent persona) selected on every session
        # via session/set_mode. Empty/None leaves the session on kiro-cli's
        # default mode (behaviour unchanged).
        self._mode = (mode or "").strip() or None
        # ``kiro-cli acp`` spawn arguments (issue #53). Each is optional; the
        # engine is always pinned explicitly (default "v2") so a future change
        # to kiro-cli's default engine cannot silently alter behaviour.
        self._agent = (agent or "").strip() or None
        self._initial_model = (initial_model or "").strip() or None
        self._effort = (effort or "").strip() or None
        self._engine = (engine or "v2").strip() or "v2"
        self._extra_args = list(extra_args or [])
        # Default MCP servers registered on every session/new (issue: MCP never
        # registered). kiro-cli executes these itself (mcpCapabilities.http) —
        # the only external-tool channel over ACP. Empty leaves the historical
        # behaviour (``mcpServers: []``) unchanged; a per-call override is still
        # accepted by :meth:`new_session` (used by the warm-up session, which
        # skips MCP setup so it can never block startup).
        self._mcp_servers = [dict(s) for s in (mcp_servers or []) if isinstance(s, dict)]
        # Bounded timeout for session/new when MCP servers are registered, so a
        # malformed/unreachable server fails fast instead of stalling every
        # request for the full ACP_TIMEOUT (see config.MCP_INIT_TIMEOUT).
        self._mcp_init_timeout = mcp_init_timeout
        # Max bytes per JSON-RPC line read from kiro-cli stdout (see config).
        self._stdio_limit = stdio_limit
        self._proc: Optional[asyncio.subprocess.Process] = None
        # Pending request id -> Future (for initialize / session/new).
        self._pending: dict[str, asyncio.Future] = {}
        # Per-session event queues for streaming prompts.
        self._event_queues: dict[str, Queue] = {}
        # Prompt request id -> sessionId, so the final result can be routed
        # to the correct session queue as a terminal "done" event.
        self._prompt_sessions: dict[str, str] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        # Fire-and-forget session/cancel notification tasks, tracked so they
        # survive the teardown of a disconnected streaming generator and can
        # be cleaned up on stop().
        self._cancel_tasks: set[asyncio.Task] = set()
        self._write_lock = asyncio.Lock()
        self._initialized = False
        # Kept for backward-compatibility with older tests/callers.
        self._session_id: Optional[str] = None
        # Live model catalogue captured from session/new (normalised dicts:
        # {"id", "name", "description"}), and kiro-cli's current default model.
        self._available_models: list[dict] = []
        self._current_model_id: Optional[str] = None
        # Live mode ("agent") catalogue captured from session/new (same
        # normalised {"id", "name", "description"} shape) and the session's
        # current default mode id. kiro-cli reports these under a ``modes``
        # block; they let the gateway advertise/select the agent persona.
        self._available_modes: list[dict] = []
        self._current_mode_id: Optional[str] = None
        # Per-session token usage captured from session/update notifications,
        # merged into the terminal "done" event. kiro-cli 2.x does not report
        # usage over ACP today (its /usage view is an interactive REPL command),
        # so this is usually empty and the shims fall back to a tokenizer
        # estimate; it is forward-compatible if a future kiro-cli emits counts.
        self._session_usage: dict[str, dict] = {}
        # Per-session kiro-cli usage/cost/context metadata captured from
        # _kiro.dev/metadata (v2: credits, context%, turn duration) and
        # session_info_update contextUsage (v3: per-category token breakdown).
        # Surfaced additively under usage["kiro_metadata"] — never mixed into
        # the native token counts. Empty when kiro-cli reports nothing.
        self._session_metadata: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _build_argv(self) -> list[str]:
        """Assemble the ``kiro-cli acp`` argv from the configured spawn options.

        Deterministic order: base command, an explicit ``--agent-engine`` pin,
        then the optional ``--agent`` / ``--model`` / ``--effort`` flags (only
        when set), then any raw ``extra_args`` appended verbatim. With nothing
        configured this yields ``[command, "acp", "--agent-engine", "v2"]`` — the
        same process as before plus an explicit engine pin (issue #53).

        Returns:
            The argv list to spawn.
        """
        argv = [self._command, "acp", "--agent-engine", self._engine]
        if self._agent:
            argv += ["--agent", self._agent]
        if self._initial_model:
            argv += ["--model", self._initial_model]
        if self._effort:
            argv += ["--effort", self._effort]
        argv += self._extra_args
        return argv

    async def start(self) -> None:
        """Spawn ``kiro-cli acp`` and begin reading its stdio."""
        argv = self._build_argv()
        logger.info(f"Spawning ACP subprocess: {' '.join(argv)}")
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self._stdio_limit,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())
        logger.info(f"kiro-cli ACP subprocess started (pid={self._proc.pid})")

    async def stop(self) -> None:
        """Gracefully stop the subprocess and cancel reader tasks."""
        for task in (self._reader_task, self._stderr_task, *self._cancel_tasks):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._cancel_tasks.clear()
        if self._proc and self._proc.returncode is None:
            try:
                if self._proc.stdin and not self._proc.stdin.is_closing():
                    self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError, OSError):
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass
        logger.info("kiro-cli ACP subprocess stopped")

    async def initialize(
        self, capabilities: Optional[GatewayCapabilities] = None
    ) -> SessionInitResult:
        """
        Perform the one-time ACP ``initialize`` handshake.

        The gateway advertises *no* client-side filesystem or terminal
        capabilities: kiro-cli runs its own built-in tools and only asks
        the gateway for permission (``session/request_permission``).

        Args:
            capabilities: Reserved for forward-compatibility (currently unused
                by the wire request, retained for API stability).

        Returns:
            SessionInitResult describing the negotiated protocol version.
        """
        params = {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
        }
        result = await self._call("initialize", params)
        proto = "1"
        if isinstance(result, dict):
            proto = str(result.get("protocolVersion", 1))
            agent = result.get("agentInfo", {})
            logger.info(
                f"ACP initialized: agent={agent.get('name', 'unknown')} "
                f"v{agent.get('version', '?')} protocol={proto}"
            )
        self._initialized = True
        return SessionInitResult(session_id="", protocol_version=proto)

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    async def new_session(
        self,
        capabilities: Optional[GatewayCapabilities] = None,
        cwd: Optional[str] = None,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        mcp_servers: Optional[list[dict]] = None,
    ) -> str:
        """
        Create a fresh ACP session and return its id.

        Args:
            capabilities: Optional gateway capabilities; the ``filesystem``
                roots are used to derive the working directory when ``cwd``
                is not given explicitly.
            cwd: Absolute working directory for the session. Defaults to the
                first filesystem root, else the gateway process cwd.
            model: Optional model id to select for this session (forwarded to
                kiro-cli via ``session/set_model``). When omitted, the session
                uses kiro-cli's current default model.
            mode: Optional mode ("agent") id to select for this session
                (forwarded via ``session/set_mode``). When omitted, the
                client's configured default mode (``KIRO_ACP_MODE``) is used,
                and when that is unset too the session keeps kiro-cli's default.
            mcp_servers: Optional list of MCP server configs to register for
                this session (``session/new``'s ``mcpServers``). ``None`` uses
                the client's configured default (``KIRO_MCP_SERVERS`` /
                ``KIRO_MCP_CONFIG``); pass an explicit ``[]`` to register none
                regardless of config (used by the warm-up session so a
                misconfigured/unreachable server cannot block startup). kiro-cli
                executes these tools itself (``mcpCapabilities.http``).

        Returns:
            The agent-assigned ``sessionId``.
        """
        workdir = cwd or self._derive_cwd(capabilities)
        servers = self._mcp_servers if mcp_servers is None else mcp_servers
        params = {"cwd": workdir, "mcpServers": servers}
        if servers:
            logger.info(
                f"session/new registering {len(servers)} MCP server(s): "
                f"{[s.get('name') for s in servers if isinstance(s, dict)]}"
            )
            # A malformed/unreachable MCP server makes kiro-cli's session/new
            # block with no error; cap it so the request fails fast instead of
            # stalling for the full ACP_TIMEOUT.
            result = await self._call(
                "session/new", params, timeout=self._mcp_init_timeout
            )
        else:
            result = await self._call("session/new", params)
        if not isinstance(result, dict) or "sessionId" not in result:
            raise ACPError(-32603, f"session/new returned no sessionId: {result!r}")
        session_id = str(result["sessionId"])
        self._session_id = session_id
        self._capture_available_models(result)
        self._capture_available_modes(result)
        logger.debug(f"ACP session created: {session_id} (cwd={workdir})")
        # Only issue the extra session/set_model round-trip when the requested
        # model differs from the session's current default. This avoids a
        # redundant RTT on every request for agents that use the default model.
        if model and model != self._current_model_id:
            await self.set_model(session_id, model)
        # Likewise select the mode ("agent") only when one is requested (per
        # call or via the configured default) and it differs from the session's
        # current mode, so the common default-mode path adds no round-trip.
        desired_mode = mode or self._mode
        if desired_mode and desired_mode != self._current_mode_id:
            await self.set_mode(session_id, desired_mode)
        return session_id

    def _capture_available_models(self, session_result: dict) -> None:
        """
        Cache the model catalogue reported by ``session/new``.

        kiro-cli returns a ``models`` object on every ``session/new``::

            {"models": {"currentModelId": "...",
                        "availableModels": [{"modelId", "name", "description"}, ...]}}

        The list is normalised to ``{"id", "name", "description"}`` dicts and
        cached so ``GET /v1/models`` can advertise the live catalogue instead of
        a static fallback.

        Args:
            session_result: The raw ``session/new`` result dict.
        """
        models_info = session_result.get("models")
        if not isinstance(models_info, dict):
            return
        current = models_info.get("currentModelId")
        if isinstance(current, str) and current:
            self._current_model_id = current
        available = models_info.get("availableModels")
        if not isinstance(available, list):
            return
        normalised: list[dict] = []
        for entry in available:
            if not isinstance(entry, dict):
                continue
            model_id = entry.get("modelId")
            if not model_id:
                continue
            normalised.append({
                "id": str(model_id),
                "name": str(entry.get("name") or model_id),
                "description": str(entry.get("description") or ""),
            })
        if normalised:
            self._available_models = normalised

    async def set_model(self, session_id: str, model_id: str) -> None:
        """
        Select the model for an existing session via ``session/set_model``.

        kiro-cli accepts this request silently (it does not validate the id),
        so an unknown model simply leaves the session on its default model.
        Failures are logged and swallowed so a model-selection problem never
        breaks the completion itself.

        Args:
            session_id: The ACP session to configure.
            model_id: The model id requested by the caller (e.g.
                ``claude-sonnet-4.6``).
        """
        try:
            await self._call(
                "session/set_model",
                {"sessionId": session_id, "modelId": model_id},
            )
            logger.info(f"ACP session {session_id} model set to '{model_id}'")
        except ACPError as exc:
            logger.warning(
                f"session/set_model failed for '{model_id}': {exc}; "
                "session will use its default model"
            )

    @property
    def available_models(self) -> list[dict]:
        """Return the cached live model catalogue (``{"id","name","description"}``)."""
        return list(self._available_models)

    def _capture_available_modes(self, session_result: dict) -> None:
        """
        Cache the mode ("agent") catalogue reported by ``session/new``.

        kiro-cli returns a ``modes`` object on ``session/new``::

            {"modes": {"currentModeId": "kiro_default",
                       "availableModes": [{"id", "name", "description"}, ...]}}

        Each mode is an agent persona (``kiro_default``, ``code``,
        ``kiro_planner``, ``kiro_guide``, …). The list is normalised to
        ``{"id", "name", "description"}`` dicts and cached alongside the current
        mode id so the gateway can advertise/select the active agent.

        Args:
            session_result: The raw ``session/new`` result dict.
        """
        modes_info = session_result.get("modes")
        if not isinstance(modes_info, dict):
            return
        current = modes_info.get("currentModeId")
        if isinstance(current, str) and current:
            self._current_mode_id = current
        available = modes_info.get("availableModes")
        if not isinstance(available, list):
            return
        normalised: list[dict] = []
        for entry in available:
            if not isinstance(entry, dict):
                continue
            mode_id = entry.get("id")
            if not mode_id:
                continue
            normalised.append({
                "id": str(mode_id),
                "name": str(entry.get("name") or mode_id),
                "description": str(entry.get("description") or ""),
            })
        if normalised:
            self._available_modes = normalised

    async def set_mode(self, session_id: str, mode_id: str) -> None:
        """
        Select the mode ("agent") for a session via ``session/set_mode``.

        Mirrors :meth:`set_model`: kiro-cli accepts the request silently and
        does not validate the id (an unknown mode leaves the session on its
        default), so failures are logged and swallowed — a mode-selection
        problem never breaks the completion itself. Verified against a live
        kiro-cli 2.12.0 probe: ``{"sessionId", "modeId"}`` → ``{}``.

        Args:
            session_id: The ACP session to configure.
            mode_id: The mode/agent id requested (e.g. ``kiro_planner``).
        """
        try:
            await self._call(
                "session/set_mode",
                {"sessionId": session_id, "modeId": mode_id},
            )
            self._current_mode_id = mode_id
            logger.info(f"ACP session {session_id} mode set to '{mode_id}'")
        except ACPError as exc:
            logger.warning(
                f"session/set_mode failed for '{mode_id}': {exc}; "
                "session will use its default mode"
            )

    @property
    def available_modes(self) -> list[dict]:
        """Return the cached live mode catalogue (``{"id","name","description"}``)."""
        return list(self._available_modes)

    @staticmethod
    def _derive_cwd(capabilities: Optional[GatewayCapabilities]) -> str:
        """Pick a working directory from filesystem roots or fall back to cwd."""
        if capabilities and capabilities.filesystem:
            first = capabilities.filesystem[0]
            path = None
            if isinstance(first, dict):
                path = first.get("path") or first.get("uri")
            else:
                path = getattr(first, "path", None) or getattr(first, "uri", None)
            if path:
                if path.startswith("file://"):
                    path = path[len("file://"):]
                if os.path.isdir(path):
                    return path
        return os.getcwd()

    # ------------------------------------------------------------------
    # Prompting
    # ------------------------------------------------------------------

    async def prompt(self, params: PromptParams) -> dict[str, Any]:
        """
        Run a non-streaming prompt and return an aggregated result dict.

        Internally consumes the same streaming pipeline as ``prompt_stream``
        and accumulates text / tool calls into a single response.

        Returns:
            {"content": str, "reasoning": str, "tool_calls": list[dict],
             "finish_reason": str, "usage": dict}
        """
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[dict] = []
        tool_by_id: dict[str, dict] = {}
        finish_reason = "stop"
        usage: dict[str, Any] = {}
        metadata: dict[str, Any] = {}

        async for event in self.prompt_stream(params):
            etype = event.get("type")
            if etype == "text":
                content_parts.append(event.get("content", ""))
            elif etype == "thinking":
                thinking_parts.append(event.get("content", ""))
            elif etype == "plan":
                rendered = format_plan_text(
                    event.get("entries", []), event.get("description", "")
                )
                if rendered:
                    thinking_parts.append("\n" + rendered + "\n")
            elif etype == "tool_call":
                tool_call = {
                    "id": event.get("id", ""),
                    "name": event.get("name", ""),
                    "kind": event.get("kind", ""),
                    "arguments": event.get("arguments", {}),
                    "content": event.get("content") or [],
                }
                tool_calls.append(tool_call)
                if tool_call["id"]:
                    tool_by_id[tool_call["id"]] = tool_call
            elif etype == "tool_call_update":
                # Attach diff/output to the matching tool call (for the
                # non-streaming activity summary).
                target = tool_by_id.get(event.get("id", ""))
                if target is not None:
                    if event.get("output"):
                        target["output"] = event["output"]
                    if event.get("content") and not target.get("content"):
                        target["content"] = event["content"]
            elif etype == "done":
                finish_reason = event.get("finish_reason", "stop")
                usage = event.get("usage", {}) or {}
                metadata = event.get("metadata", {}) or {}
            elif etype == "error":
                raise ACPError(
                    event.get("code", -32000),
                    event.get("message", "ACP prompt failed"),
                    event.get("data"),
                )

        return {
            "content": "".join(content_parts),
            "reasoning": "".join(thinking_parts),
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "usage": usage,
            "metadata": metadata,
        }

    async def prompt_stream(self, params: PromptParams) -> AsyncIterator[dict[str, Any]]:
        """
        Stream normalised events for a ``session/prompt`` turn.

        Yields dict events (see module docstring) as they arrive, terminating
        after the ``done`` (or ``error``) event.
        """
        session_id = params.session_id
        if not session_id:
            raise ACPError(-32602, "prompt_stream requires a session_id")

        prompt_blocks = self._build_prompt_blocks(params.messages)
        queue: Queue = Queue()
        self._event_queues[session_id] = queue

        req_id = str(uuid.uuid4())
        self._prompt_sessions[req_id] = session_id

        prompt_sent = False
        completed = False
        try:
            prompt_params: dict[str, Any] = {
                "sessionId": session_id,
                "prompt": prompt_blocks,
            }
            # ACP reserves ``_meta`` for implementation-specific extension data,
            # so forwarding sampling hints and client tool definitions there is
            # schema-safe (a strict agent will not reject them).
            meta: dict[str, Any] = {}
            gen_meta = self._generation_meta(params)
            if gen_meta:
                # kiro-cli 2.8.0 accepts but does not act on these — see
                # _generation_meta.
                meta["generationConfig"] = gen_meta
            tool_meta = self._tool_meta(params)
            if tool_meta:
                # Client-declared tools. Verified against a live kiro-cli 2.8.0
                # ACP probe: the agent does NOT honor client tools passed on
                # session/prompt (it exposes only its own built-in tools and any
                # MCP-server tools), so these are currently inert. They are
                # forwarded under _meta so they reach kiro-cli and take effect
                # automatically if a future version ingests them — see
                # _tool_meta and the README "Tool execution" section.
                meta["tools"] = tool_meta
            structured_meta = self._structured_output_meta(params)
            if structured_meta:
                # Structured-output controls (response_format / tool_choice).
                # Verified inert on kiro-cli 2.8.0 (no structured-output or
                # tool-choice capability advertised); forwarded under _meta so
                # they reach kiro-cli and take effect automatically if a future
                # version honors them — see _structured_output_meta and the
                # README "Structured outputs" section (issue #35).
                meta["structuredOutput"] = structured_meta
            if meta:
                prompt_params["_meta"] = meta
            await self._send(JsonRpcRequest(
                id=req_id,
                method="session/prompt",
                params=prompt_params,
            ))
            prompt_sent = True
            # Gateway-side enforcement of stop sequences / max_tokens (kiro-cli
            # honors neither over ACP — issue #32). No-op unless active.
            limiter = StreamLimiter(
                params.stop, params.max_tokens, params.enforce_max_tokens
            )
            while True:
                event = await queue.get()
                etype = event.get("type")

                if limiter.active and etype == "text":
                    emit, finish_reason = limiter.feed(event.get("content", ""))
                    if emit:
                        yield {"type": "text", "content": emit}
                    if finish_reason:
                        # A stop sequence or the token cap was hit: end the turn
                        # ourselves and let the finally-block cancel kiro-cli so
                        # it stops generating.
                        usage = self._session_usage.pop(session_id, {})
                        yield {"type": "done",
                               "finish_reason": finish_reason, "usage": usage}
                        break
                    continue

                if etype in ("done", "error"):
                    # Release any text held back for stop-sequence matching
                    # before the terminal event.
                    if limiter.active and etype == "done":
                        tail = limiter.flush()
                        if tail:
                            yield {"type": "text", "content": tail}
                    yield event
                    completed = True
                    break

                yield event
        finally:
            # If the turn was started but the consumer stopped before a
            # terminal event — e.g. the client disconnected and the streaming
            # generator is being torn down (GeneratorExit / CancelledError) —
            # tell kiro-cli to abandon the turn. All requests multiplex over
            # one subprocess, so an abandoned long turn would otherwise block
            # every other request (head-of-line blocking). Fire-and-forget so
            # the notification is still dispatched even while this generator is
            # unwinding under cancellation.
            if prompt_sent and not completed:
                self._schedule_cancel(session_id)
            self._event_queues.pop(session_id, None)
            self._prompt_sessions.pop(req_id, None)
            self._session_usage.pop(session_id, None)

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    async def cancel(self, session_id: str) -> None:
        """Ask the agent to abandon the in-flight turn for a session.

        Sends the ACP ``session/cancel`` notification (client → agent, no id)
        with ``{"sessionId": ...}``. Verified against a live ``kiro-cli acp``
        probe: the agent stops the current turn and returns the pending
        ``session/prompt`` result with ``stopReason: "cancelled"``.

        This is best-effort and idempotent from the caller's perspective; a
        blank ``session_id`` is a no-op.

        Args:
            session_id: The ACP session whose current turn should be cancelled.
        """
        if not session_id:
            return
        await self._send_notification("session/cancel", {"sessionId": session_id})
        # DEBUG, not INFO: cancellation is an expected teardown step (the client
        # disconnected or the harness cancelled the turn before it finished), not
        # a business event — logging it at INFO is noisy for harnesses that
        # routinely abandon streams. See issue: log noise on session/cancel.
        logger.debug(f"ACP session/cancel sent for session {session_id}")

    async def _cancel_quietly(self, session_id: str) -> None:
        """Run :meth:`cancel`, swallowing transport errors.

        Cancellation happens during request teardown, where raising would be
        useless and could mask the original disconnect. Failures (closed stdin,
        no subprocess) are logged at WARNING and otherwise ignored.

        Args:
            session_id: The ACP session whose current turn should be cancelled.
        """
        try:
            await self.cancel(session_id)
        except (OSError, RuntimeError, ACPError) as exc:
            logger.warning(f"session/cancel failed for {session_id}: {exc}")

    def _schedule_cancel(self, session_id: str) -> None:
        """Fire-and-forget a ``session/cancel`` notification.

        Spawned as an independent, tracked task so the notification is written
        even when the calling streaming generator is being torn down by a
        client disconnect (the generator's ``finally`` cannot reliably ``await``
        under ``CancelledError``). The task keeps a reference in
        ``_cancel_tasks`` until it completes.

        Args:
            session_id: The ACP session whose current turn should be cancelled.
        """
        if not session_id:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (interpreter/loop teardown) — nothing to do.
            return
        task = loop.create_task(self._cancel_quietly(session_id))
        self._cancel_tasks.add(task)
        task.add_done_callback(self._cancel_tasks.discard)

    @staticmethod
    def _generation_meta(params: PromptParams) -> dict[str, Any]:
        """Translate sampling fields on ``PromptParams`` into an ACP ``_meta`` map.

        Only fields the caller actually set are included, using ACP-style
        camelCase keys.

        Note:
            Verified against a live ``kiro-cli`` 2.8.0 probe: the agent
            advertises no sampling capability and ignores these values
            (``maxTokens``, ``stopSequences``, ``temperature``, ``topP``,
            ``topK``) — output is identical with or without them. They are
            forwarded anyway so they reach kiro-cli and take effect with no
            gateway change if a future version honors them. The only
            per-request control kiro-cli currently honors is the model
            (``session/set_model``).

        Args:
            params: The prompt parameters carrying optional sampling settings.

        Returns:
            A dict of the set sampling params (camelCase keys), possibly empty.
        """
        candidates = {
            "temperature": params.temperature,
            "maxTokens": params.max_tokens,
            "topP": params.top_p,
            "topK": params.top_k,
            "stopSequences": params.stop,
        }
        return {key: value for key, value in candidates.items() if value is not None}

    @staticmethod
    def _tool_meta(params: PromptParams) -> list[dict]:
        """Translate client-declared tool definitions into an ACP ``_meta`` list.

        Each tool is rendered as ``{"name", "description", "inputSchema"}`` —
        the MCP/JSON-Schema tool shape — so the payload is ready for an agent
        that ingests client tools.

        Note:
            Verified against a live ``kiro-cli`` 2.8.0 ACP probe: the agent does
            **not** honor client-declared tools passed on ``session/prompt``
            (neither a top-level ``tools`` field nor ``_meta.tools``). It exposes
            only its own built-in tools plus any tools provided by **MCP servers**
            registered at ``session/new`` (``mcpServers``; the agent advertises
            ``mcpCapabilities.http: true``). In a probe the model replied that it
            had no client tool available. These definitions are forwarded under
            ``_meta`` anyway so they reach kiro-cli and take effect with no
            gateway change if a future version ingests them — and so the wire
            request faithfully carries the caller's intent. True client-side
            function calling requires the MCP-bridge path (see the README
            "Tool execution & permissions" section).

        Args:
            params: The prompt parameters carrying optional ``tools``.

        Returns:
            A list of tool dicts (``name``/``description``/``inputSchema``);
            empty when the caller declared no tools.
        """
        tools = getattr(params, "tools", None)
        if not tools:
            return []
        rendered: list[dict] = []
        for tool in tools:
            if hasattr(tool, "model_dump"):
                tool = tool.model_dump()
            if not isinstance(tool, dict):
                continue
            name = tool.get("name")
            if not name:
                continue
            rendered_tool = {
                "name": name,
                "description": tool.get("description") or "",
                "inputSchema": tool.get("input_schema") or tool.get("inputSchema") or {},
            }
            # Preserve OpenAI "strict" tool schemas (structured tool outputs).
            # Inert on kiro-cli today (client tools are not honored over ACP),
            # but forwarded so the wire request faithfully carries the caller's
            # intent and a future kiro-cli can act on it (issue #35).
            strict = tool.get("strict")
            if strict is not None:
                rendered_tool["strict"] = strict
            rendered.append(rendered_tool)
        return rendered

    @staticmethod
    def _structured_output_meta(params: PromptParams) -> dict[str, Any]:
        """Translate structured-output controls into an ACP ``_meta`` map.

        Collects the response-format / tool-choice controls a caller set into a
        single camelCase map suitable for the ``_meta.structuredOutput``
        extension. Only fields the caller actually set are included.

        Note:
            kiro-cli (ACP) does **not** honor structured-output controls today:
            it advertises no JSON-mode / json-schema / tool-choice capability,
            so ``response_format`` (OpenAI JSON mode or ``json_schema`` /
            Responses ``text.format``) and ``tool_choice``
            (``auto``/``none``/``required``/``any`` or a named-tool object) are
            inert. They are forwarded under the schema-safe ``_meta`` extension
            so they reach kiro-cli and take effect automatically if a future
            version honors them, and so the wire request faithfully carries the
            caller's intent. OpenAI strict tool schemas are carried per-tool by
            :meth:`_tool_meta` (the ``strict`` flag). See issue #35 and the
            README "Structured outputs" section.

        Args:
            params: The prompt parameters carrying optional ``response_format``
                / ``tool_choice``.

        Returns:
            A dict with ``responseFormat`` and/or ``toolChoice`` for the fields
            the caller set; empty when neither is present.
        """
        meta: dict[str, Any] = {}
        if params.response_format is not None:
            meta["responseFormat"] = params.response_format
        if params.tool_choice is not None:
            meta["toolChoice"] = params.tool_choice
        return meta

    @staticmethod
    def _build_prompt_blocks(messages: list) -> list[dict]:
        """
        Render a conversation into ACP ``session/prompt`` content blocks.

        **Why a labelled transcript (issue #43).** ACP's ``session/prompt.prompt``
        is a list of **role-less** content blocks (the protocol's ContentBlock
        has no per-message ``role`` field — only ``text``/``image``/… kinds), and
        ACP keeps multi-turn state *server-side* across successive prompts within
        one session. The gateway, however, is **stateless**: it opens a fresh
        session per request and must carry the entire conversation in a single
        ``session/prompt``. There is therefore no protocol channel for
        structured, role-tagged turns — so the faithful maximum is a single text
        block whose turns are delimited by stable ``Role:`` labels
        (``System:`` / ``Developer:`` / ``User:`` / ``Assistant:``), in order,
        separated by blank lines. Prior tool turns are preserved as
        ``[tool_use id=… name=…]`` / ``[tool_result id=…]`` markers emitted by the
        shims, so tool-heavy histories stay legible rather than being dropped.

        A lone user message is sent verbatim (no label) — the common single-turn
        case is unchanged. Multiple text blocks (one per turn) were considered
        but rejected: ACP attaches no role to a block, so splitting gains no
        structural fidelity while risking ambiguous boundaries if an agent
        concatenates blocks without a separator. The labelled, blank-line-
        delimited single block keeps boundaries explicit and stable.

        **Images (issue #33).** kiro-cli advertises ``promptCapabilities.image``
        (verified against a live 2.10.0 probe), so image attachments — carried
        as ``{"type": "image", …}`` entries inside a message's structured
        content — are emitted as their own ACP image content blocks **after** the
        text transcript, with an inline ``[image]`` marker left in the turn's
        text to mark where each appeared. The result is a mixed prompt array
        ``[{text transcript}, {image}, …]`` (documents/audio are already reduced
        to text by the shims; only images travel as binary blocks).
        """
        label = {
            "user": "User",
            "assistant": "Assistant",
            "system": "System",
            "developer": "Developer",
        }
        parts: list[tuple[str, str]] = []
        image_blocks: list[dict] = []
        for m in messages:
            role = getattr(m, "role", None) if not isinstance(m, dict) else m.get("role")
            content = getattr(m, "content", None) if not isinstance(m, dict) else m.get("content")
            text, images = ACPClient._split_content(content)
            # Leave an inline marker per image so the (role-less) transcript
            # still references where each attachment occurred, then carry the
            # image as a real ACP block appended after the text.
            for img in images:
                text = (text + "\n[image]") if text else "[image]"
                image_blocks.append(img)
            parts.append((role or "user", text))

        blocks: list[dict] = []
        if not parts:
            text_block_text = ""
        elif len(parts) == 1 and parts[0][0] == "user":
            text_block_text = parts[0][1]
        else:
            text_block_text = "\n\n".join(
                f"{label.get(r, 'User')}: {c}" for r, c in parts
            )

        if text_block_text or not image_blocks:
            blocks.append({"type": "text", "text": text_block_text})
        blocks.extend(image_blocks)
        return blocks or [{"type": "text", "text": ""}]

    @staticmethod
    def _split_content(content: Any) -> tuple[str, list[dict]]:
        """Split message content into (flattened text, image content blocks).

        Text and any non-image parts are flattened to a single string (as
        :meth:`_flatten_content`), while ``image`` parts are extracted as ACP
        image wire blocks (``{"type": "image", "mimeType", "data"}``) so the
        prompt builder can forward them. Plain-string content yields no images.

        Args:
            content: A message's content (``str`` or list of normalised blocks).

        Returns:
            A ``(text, images)`` tuple.
        """
        if content is None:
            return "", []
        if isinstance(content, str):
            return content, []
        if isinstance(content, list):
            chunks: list[str] = []
            images: list[dict] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "image" and part.get("data"):
                        images.append({
                            "type": "image",
                            "mimeType": part.get("mimeType") or part.get("mime_type") or "image/png",
                            "data": part["data"],
                        })
                    else:
                        chunks.append(str(part.get("text") or part.get("content") or ""))
                else:
                    chunks.append(str(part))
            return "\n".join(c for c in chunks if c), images
        return str(content), []

    @staticmethod
    def _flatten_content(content: Any) -> str:
        """Flatten str | list[content_part] into plain text (images dropped)."""
        text, _ = ACPClient._split_content(content)
        return text

    # ------------------------------------------------------------------
    # Internal: JSON-RPC plumbing
    # ------------------------------------------------------------------

    async def _call(self, method: str, params: dict, timeout: float = 120.0) -> Any:
        """Send a request and await its response (used for init / session/new)."""
        req_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        await self._send(JsonRpcRequest(id=req_id, method=method, params=params))
        try:
            response: JsonRpcResponse = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise ACPError(-32000, f"ACP {method} timed out after {timeout}s")
        if response.error:
            raise ACPError(response.error.code, response.error.message, response.error.data)
        return response.result

    async def _send(self, req: JsonRpcRequest) -> None:
        await self._write_line(req.model_dump_json())

    async def _send_notification(self, method: str, params: dict) -> None:
        """Write a JSON-RPC 2.0 notification (a request with no ``id``).

        Notifications expect no response, per the JSON-RPC spec, and are how
        ACP delivers ``session/cancel``.

        Args:
            method: The JSON-RPC method name (e.g. ``session/cancel``).
            params: The method parameters.
        """
        await self._write_line(json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }))

    async def _write_line(self, line: str) -> None:
        async with self._write_lock:
            if self._proc and self._proc.stdin:
                self._proc.stdin.write((line + "\n").encode())
                await self._proc.stdin.drain()

    async def _read_loop(self) -> None:
        """Read JSON-RPC messages from stdout and dispatch them."""
        assert self._proc and self._proc.stdout
        while True:
            try:
                raw = await self._proc.stdout.readline()
                if not raw:
                    logger.warning("kiro-cli stdout closed")
                    self._fail_all("kiro-cli subprocess exited")
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                logger.debug(f"kiro-cli stdout: {line[:500]}")
                self._dispatch(line)
            except asyncio.CancelledError:
                break
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.error(f"ACP read_loop parse error: {exc}")

    async def _stderr_loop(self) -> None:
        """Drain stderr and log it at DEBUG level."""
        assert self._proc and self._proc.stderr
        while True:
            try:
                raw = await self._proc.stderr.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    logger.debug(f"kiro-cli stderr: {line}")
            except asyncio.CancelledError:
                break
            except (UnicodeDecodeError, ValueError) as exc:
                logger.error(f"ACP stderr_loop error: {exc}")

    def _fail_all(self, message: str) -> None:
        """Propagate a fatal error to every pending future and active queue."""
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ACPError(-32000, message))
        self._pending.clear()
        for queue in list(self._event_queues.values()):
            queue.put_nowait({"type": "error", "message": message, "code": -32000})

    def _dispatch(self, line: str) -> None:
        """Route a single JSON-RPC line to the right handler."""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(f"ACP: unparseable line: {line[:200]}")
            return

        method = msg.get("method")
        has_id = msg.get("id") is not None

        if method and has_id:
            # Agent -> gateway request (e.g. session/request_permission).
            asyncio.create_task(self._handle_agent_request(msg))
            return
        if method:
            # Notification (no id) such as session/update.
            self._handle_notification(msg)
            return

        # Response to one of our outstanding requests.
        msg_id = str(msg.get("id", ""))
        future = self._pending.pop(msg_id, None)
        if future and not future.done():
            future.set_result(JsonRpcResponse(**msg))
            return
        # Otherwise it may be the terminal result of a streaming prompt.
        self._finish_prompt(msg_id, msg)

    def _finish_prompt(self, req_id: str, msg: dict) -> None:
        """Translate a session/prompt response into a terminal queue event."""
        session_id = self._prompt_sessions.get(req_id)
        if not session_id:
            return
        queue = self._event_queues.get(session_id)
        if not queue:
            return
        if msg.get("error"):
            err = msg["error"]
            self._session_metadata.pop(session_id, None)
            queue.put_nowait({
                "type": "error",
                "message": err.get("message", "ACP prompt error"),
                "code": err.get("code"),
                "data": err.get("data"),
            })
            return
        result = msg.get("result") or {}
        stop_reason = result.get("stopReason", "end_turn") if isinstance(result, dict) else "end_turn"
        usage = self._find_usage(result)
        # Merge anything captured from session/update notifications (result
        # wins per key when both are present).
        captured = self._session_usage.pop(session_id, {})
        if captured:
            usage = {**captured, **usage}
        done_event: dict[str, Any] = {
            "type": "done",
            "finish_reason": _STOP_REASON_MAP.get(stop_reason, "stop"),
            "usage": usage,
        }
        # Attach any captured kiro-cli usage/cost/context metadata additively
        # (credits, context %, turn duration, v3 token breakdown). Empty on
        # builds that report none, so the event shape is unchanged then.
        metadata = self._session_metadata.pop(session_id, {})
        if metadata:
            done_event["metadata"] = metadata
        queue.put_nowait(done_event)

    @staticmethod
    def _normalize_usage_keys(usage: Any) -> dict:
        """Normalise a usage dict to ``{input,output,total}_tokens`` int keys.

        Accepts both ``snake_case`` and ``camelCase`` variants (and the OpenAI
        ``prompt``/``completion`` spellings) so usage reported in any common
        shape is surfaced verbatim. Cache-token counts
        (``cache_creation_input_tokens`` / ``cache_read_input_tokens``) are
        surfaced too when present — prompt caching is not part of the ACP path
        today, but this is forward-compatible if a future kiro-cli reports them.

        Args:
            usage: A candidate usage mapping (or anything; non-dicts yield ``{}``).

        Returns:
            A dict with any of ``input_tokens`` / ``output_tokens`` /
            ``total_tokens`` / ``cache_creation_input_tokens`` /
            ``cache_read_input_tokens`` that were present and parseable as ints.
        """
        if not isinstance(usage, dict):
            return {}

        def _pick(*keys: str) -> Optional[int]:
            for key in keys:
                value = usage.get(key)
                if value is not None:
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        return None
            return None

        normalised: dict[str, int] = {}
        input_tokens = _pick("input_tokens", "inputTokens", "promptTokens", "prompt_tokens")
        output_tokens = _pick("output_tokens", "outputTokens", "completionTokens", "completion_tokens")
        total_tokens = _pick("total_tokens", "totalTokens")
        cache_creation = _pick(
            "cache_creation_input_tokens", "cacheCreationInputTokens",
            "cache_creation_tokens", "cacheCreationTokens",
        )
        cache_read = _pick(
            "cache_read_input_tokens", "cacheReadInputTokens",
            "cache_read_tokens", "cacheReadTokens",
            "cached_tokens", "cachedTokens",
        )
        if input_tokens is not None:
            normalised["input_tokens"] = input_tokens
        if output_tokens is not None:
            normalised["output_tokens"] = output_tokens
        if total_tokens is not None:
            normalised["total_tokens"] = total_tokens
        if cache_creation is not None:
            normalised["cache_creation_input_tokens"] = cache_creation
        if cache_read is not None:
            normalised["cache_read_input_tokens"] = cache_read
        return normalised

    @staticmethod
    def _find_usage(obj: Any) -> dict:
        """Locate and normalise token usage in an ACP payload.

        Looks for a ``usage`` object at the top level and, failing that, under
        the ACP ``_meta`` extension field.

        Args:
            obj: An ACP result or notification-params object.

        Returns:
            The normalised usage dict, or empty when none is present.
        """
        if not isinstance(obj, dict):
            return {}
        norm = ACPClient._normalize_usage_keys(obj.get("usage"))
        if norm:
            return norm
        meta = obj.get("_meta")
        if isinstance(meta, dict):
            return ACPClient._normalize_usage_keys(meta.get("usage"))
        return {}

    @staticmethod
    def _extract_usage(result: Any) -> dict:
        """Normalise any token usage reported on a ``session/prompt`` result.

        kiro-cli 2.x returns only ``{stopReason}`` (no usage), so this usually
        yields an empty dict and the shims fall back to a tokenizer estimate.
        It is forward-compatible: if a future kiro-cli reports usage — at the
        top level or under ``_meta`` — the counts are surfaced verbatim.

        Args:
            result: The raw ``session/prompt`` result object.

        Returns:
            A dict with any reported ``input_tokens`` / ``output_tokens`` /
            ``total_tokens``; empty when none are present.
        """
        return ACPClient._find_usage(result)

    @staticmethod
    def _parse_kiro_metadata(obj: Any) -> dict:
        """Extract kiro-cli usage/cost/context metadata from a notification.

        Handles two shapes seen on a live kiro-cli 2.12.0 probe:

        * **v2** ``_kiro.dev/metadata`` params — ``contextUsagePercentage``
          (context-window fill %), ``meteringUsage`` (a list of
          ``{value, unit}`` cost entries; the credit-unit values are summed),
          and ``turnDurationMs`` (turn latency).
        * **v3** ``session_info_update`` — ``contextUsage`` (top level or under
          ``_meta.kiro``) carrying ``usagePercentage`` and a ``breakdown`` of
          per-category token counts.

        These are surfaced additively (never mixed into the native token
        counts): v2 ``meteringUsage`` is *credits*, not tokens, and the v3
        breakdown is cumulative context composition rather than per-turn
        input/output. Only keys actually present are returned; never raises.

        Args:
            obj: A notification ``params`` or ``update`` object.

        Returns:
            A normalised metadata dict (possibly empty).
        """
        if not isinstance(obj, dict):
            return {}
        meta: dict[str, Any] = {}

        # v2 — context-window fill percentage.
        pct = obj.get("contextUsagePercentage")
        if isinstance(pct, (int, float)) and not isinstance(pct, bool):
            meta["context_usage_percentage"] = float(pct)

        # v2 — turn latency.
        dur = obj.get("turnDurationMs")
        if isinstance(dur, (int, float)) and not isinstance(dur, bool):
            meta["turn_duration_ms"] = int(dur)

        # v2 — metering cost (sum credit-unit entries).
        metering = obj.get("meteringUsage")
        if isinstance(metering, list):
            credits = 0.0
            found = False
            for item in metering:
                if not isinstance(item, dict):
                    continue
                value = item.get("value")
                unit = str(item.get("unit") or "").lower()
                if isinstance(value, (int, float)) and not isinstance(value, bool) and unit == "credit":
                    credits += float(value)
                    found = True
            if found:
                meta["credits"] = credits

        # v3 — contextUsage (top level or under _meta.kiro).
        ctx = obj.get("contextUsage")
        if not isinstance(ctx, dict):
            outer_meta = obj.get("_meta")
            if isinstance(outer_meta, dict):
                kiro = outer_meta.get("kiro")
                if isinstance(kiro, dict):
                    ctx = kiro.get("contextUsage")
        if isinstance(ctx, dict):
            upct = ctx.get("usagePercentage")
            if (
                isinstance(upct, (int, float)) and not isinstance(upct, bool)
                and "context_usage_percentage" not in meta
            ):
                meta["context_usage_percentage"] = float(upct)
            breakdown = ctx.get("breakdown")
            if isinstance(breakdown, dict):
                categories: dict[str, int] = {}
                total = 0
                for name, entry in breakdown.items():
                    if not isinstance(entry, dict):
                        continue
                    tokens = entry.get("tokens")
                    if isinstance(tokens, (int, float)) and not isinstance(tokens, bool):
                        categories[str(name)] = int(tokens)
                        total += int(tokens)
                if categories:
                    meta["context_tokens"] = total
                    meta["context_breakdown"] = categories

        return meta

    def _handle_notification(self, msg: dict) -> None:
        """Translate ``session/update`` notifications into gateway events."""
        method = msg.get("method", "")
        params = msg.get("params", {})

        if method == "_kiro.dev/metadata":
            # v2 usage/cost/context metadata (credits, context %, turn latency).
            # Not part of the OpenAI/Anthropic surface as token counts — captured
            # separately and surfaced additively on the terminal "done" event.
            meta_sid = params.get("sessionId", "") if isinstance(params, dict) else ""
            if meta_sid:
                parsed = self._parse_kiro_metadata(params)
                if parsed:
                    self._session_metadata.setdefault(meta_sid, {}).update(parsed)
            return

        if method != "session/update":
            # Other _kiro.dev/* / _kiro/* notifications, commands, etc. are not
            # part of the OpenAI/Anthropic surface — ignore them.
            logger.debug(f"ACP notification ignored: {method}")
            return

        session_id = params.get("sessionId", "")
        queue = self._event_queues.get(session_id)
        if not queue:
            return

        update = params.get("update", {})
        kind = update.get("sessionUpdate")

        # kiro-cli may attach token usage to an update or its params/_meta
        # (this is the same data its interactive /usage view shows). Capture it
        # so the terminal "done" event can surface real counts instead of an
        # estimate. Usually absent on kiro-cli 2.x; harmless when so.
        captured = self._find_usage(update) or self._find_usage(params)
        if captured:
            self._session_usage.setdefault(session_id, {}).update(captured)

        # Capture usage/cost/context metadata carried on an update (v3
        # session_info_update contextUsage, or any _kiro metadata riding a
        # session/update). Additive; empty on kiro-cli builds that omit it.
        meta = self._parse_kiro_metadata(update) or self._parse_kiro_metadata(params)
        if meta:
            self._session_metadata.setdefault(session_id, {}).update(meta)

        if kind == "agent_message_chunk":
            text = self._extract_text(update.get("content"))
            if text:
                queue.put_nowait({"type": "text", "content": text})
        elif kind == "agent_thought_chunk":
            text = self._extract_text(update.get("content"))
            if text:
                queue.put_nowait({"type": "thinking", "content": text})
        elif kind == "tool_call":
            if self._is_plan_tool(update):
                # kiro-cli's task list arrives as its built-in todo tool. Surface
                # it as a dedicated `plan` event rather than a client-executable
                # tool call. A bookkeeping call with no entries (e.g. "complete")
                # is dropped.
                entries, description = self._plan_entries(update)
                if entries:
                    queue.put_nowait({
                        "type": "plan",
                        "entries": entries,
                        "description": description,
                    })
            else:
                queue.put_nowait({
                    "type": "tool_call",
                    "id": update.get("toolCallId", str(uuid.uuid4())),
                    "name": update.get("title") or update.get("kind") or "tool",
                    "kind": update.get("kind") or "",
                    "arguments": update.get("rawInput", {}) or {},
                    "content": update.get("content") or [],
                })
        elif kind == "tool_call_update":
            # Surface diffs (file edits) and command output (shell/execute) for
            # the activity view. Plan-tool updates are handled at tool_call time.
            if not self._is_plan_tool(update):
                queue.put_nowait({
                    "type": "tool_call_update",
                    "id": update.get("toolCallId", str(uuid.uuid4())),
                    "name": update.get("title") or update.get("kind") or "tool",
                    "kind": update.get("kind") or "",
                    "status": update.get("status") or "",
                    "output": self._extract_tool_output(update.get("rawOutput")),
                    "content": update.get("content") or [],
                })
        # available_commands_update and other kinds: not surfaced.

    @staticmethod
    def _extract_text(content: Any) -> str:
        """Extract text from a session/update content object."""
        if isinstance(content, dict):
            return content.get("text", "")
        if isinstance(content, str):
            return content
        return ""

    @staticmethod
    def _is_plan_tool(update: dict) -> bool:
        """Whether a tool_call update is kiro-cli's built-in task-list (todo) tool.

        kiro-cli has no standard ACP ``plan`` update; its task list comes through
        the ``todo_list`` tool, whose ``rawInput`` carries ``tasks`` /
        ``task_list_description`` (create/add) or ``completed_task_ids``
        (complete). These keys are todo-specific (the file-edit tool uses
        ``path``/``content``), so they are a safe discriminator.

        Args:
            update: The ``session/update`` ``update`` object for a tool call.

        Returns:
            ``True`` when the call is the task-list tool.
        """
        raw_in = update.get("rawInput")
        if isinstance(raw_in, dict) and any(
            key in raw_in for key in ("tasks", "task_list_description", "completed_task_ids")
        ):
            return True
        return "task list" in str(update.get("title") or "").lower()

    @staticmethod
    def _plan_entries(update: dict) -> tuple[list[dict], str]:
        """Extract normalised plan entries + description from a todo tool call.

        Args:
            update: The ``session/update`` ``update`` object for a plan tool call.

        Returns:
            ``(entries, description)`` where each entry is
            ``{"content": str, "status": "pending"|"in_progress"|"completed"}``.
            ``entries`` is empty for a bookkeeping call (e.g. "complete") that
            carries no task list.
        """
        raw_in = update.get("rawInput")
        entries: list[dict] = []
        description = ""
        if isinstance(raw_in, dict):
            description = str(raw_in.get("task_list_description") or "")
            tasks = raw_in.get("tasks")
            if isinstance(tasks, list):
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    content = task.get("task_description") or task.get("content") or ""
                    if not content:
                        continue
                    status = "completed" if task.get("completed") else "pending"
                    entries.append({"content": str(content), "status": status})
        return entries, description

    @staticmethod
    def _extract_tool_output(raw_output: Any) -> str:
        """Extract printable text from a tool call's ``rawOutput``.

        kiro-cli returns ``rawOutput`` as ``{"items": [{"Text": "..."}, {"Json": …}]}``.
        This concatenates the text items (and JSON-encodes structured items) into
        a plain string for the activity/reasoning view.

        Args:
            raw_output: The ``rawOutput`` object from a ``tool_call_update``.

        Returns:
            The concatenated output text, or ``""`` when there is none.
        """
        if not isinstance(raw_output, dict):
            return ""
        items = raw_output.get("items")
        if not isinstance(items, list):
            return ""
        parts: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("Text") is not None:
                parts.append(str(item["Text"]))
            elif "Json" in item:
                summary = _summarize_json_output(item["Json"])
                if summary:
                    parts.append(summary)
        return "\n".join(p for p in parts if p)[:8000]

    # ------------------------------------------------------------------
    # Agent -> gateway requests
    # ------------------------------------------------------------------

    async def _handle_agent_request(self, msg: dict) -> None:
        """Respond to a request the agent sends back to the gateway."""
        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params", {})

        if method == "session/request_permission":
            option_id = self._select_permission_option(params.get("options", []))
            await self._respond(req_id, {"outcome": {"outcome": "selected", "optionId": option_id}})
            return

        # We advertise no fs/terminal capabilities, so kiro-cli should never
        # ask us to perform them. If it does, decline cleanly.
        await self._respond_error(req_id, -32601, f"{method} not supported by gateway")

    def _select_permission_option(self, options: list[dict]) -> str:
        """
        Choose a permission option.

        When ``trust_tools`` is enabled the gateway auto-approves a single
        invocation (``allow_once``); otherwise it rejects (``reject_once``).
        Falls back to matching by ``kind`` then to the first option.
        """
        wanted_kinds = (
            ("allow_once", "allow_always", "allow")
            if self._trust_tools
            else ("reject_once", "reject_always", "reject")
        )
        for kind in wanted_kinds:
            for opt in options:
                if opt.get("kind") == kind or opt.get("optionId") == kind:
                    return opt.get("optionId", kind)
        # Fall back: any option whose kind/id contains the desired verb.
        verb = "allow" if self._trust_tools else "reject"
        for opt in options:
            if verb in str(opt.get("kind", "")) or verb in str(opt.get("optionId", "")):
                return opt.get("optionId", verb)
        return options[0].get("optionId", "allow_once") if options else "allow_once"

    async def _respond(self, req_id: Any, result: Any) -> None:
        await self._write_line(JsonRpcResponse(id=req_id, result=result).model_dump_json())

    async def _respond_error(self, req_id: Any, code: int, message: str) -> None:
        from kiro.acp_models import JsonRpcError
        await self._write_line(
            JsonRpcResponse(id=req_id, error=JsonRpcError(code=code, message=message)).model_dump_json()
        )

    # ------------------------------------------------------------------
    # Backward-compatible capability hooks (retained for shim_service/tests)
    # ------------------------------------------------------------------

    async def capability_requests(self, session_id: str) -> AsyncIterator[tuple[str, str, dict]]:
        """
        Deprecated: capability/permission handling now happens inside the
        read loop. Kept as an empty async generator for API compatibility.
        """
        if False:  # pragma: no cover - keeps this an async generator
            yield ("", "", {})
        return

    async def send_capability_result(self, request_id: str, result: Any) -> None:
        await self._respond(request_id, result)

    async def send_capability_error(self, request_id: str, code: int, message: str) -> None:
        await self._respond_error(request_id, code, message)
