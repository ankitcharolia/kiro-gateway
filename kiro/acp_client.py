# -*- coding: utf-8 -*-
"""
ACP client — manages a kiro-cli subprocess via JSON-RPC 2.0 over stdio.

Protocol:
  Gateway writes one JSON-RPC request per line to kiro-cli stdin.
  kiro-cli writes one JSON-RPC message per line to stdout.
  Progress events arrive as notifications (method="session/progress").
  Capability requests arrive as notifications (method="capability/*").
"""
from __future__ import annotations

import asyncio
import json
import uuid
from asyncio import Queue
from typing import Any, AsyncIterator, Optional

from loguru import logger

from kiro.acp_models import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcNotification,
    SessionInitParams, SessionInitResult,
    PromptParams, ProgressParams,
    ReadFileParams, WriteFileParams, RunCommandParams, ListDirectoryParams,
    GatewayCapabilities,
)


class ACPError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class ACPClient:
    """
    Manages a single kiro-cli ACP subprocess.

    Lifetime: created once per gateway process, shared across requests.
    Thread-safety: all methods are coroutine-safe via asyncio locks.
    """

    def __init__(self, command: str = "kiro"):
        self._command = command
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._pending: dict[str, asyncio.Future] = {}
        # Per-session queues for progress notifications
        self._progress_queues: dict[str, Queue] = {}
        # Per-session queues for capability requests
        self._capability_queues: dict[str, Queue] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._write_lock = asyncio.Lock()
        self._session_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn kiro-cli in ACP mode."""
        logger.info(f"Spawning ACP subprocess: {self._command} acp")
        self._proc = await asyncio.create_subprocess_exec(
            self._command, "acp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info(f"kiro-cli ACP subprocess started (pid={self._proc.pid})")

    async def stop(self) -> None:
        """Gracefully stop kiro-cli."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                self._proc.kill()
        logger.info("kiro-cli ACP subprocess stopped")

    async def initialize(self, capabilities: Optional[GatewayCapabilities] = None) -> SessionInitResult:
        """Send session/initialize and store the session ID."""
        params = SessionInitParams(
            capabilities=capabilities or GatewayCapabilities()
        )
        result = await self._call("session/initialize", params.model_dump(exclude_none=True))
        init_result = SessionInitResult(**result)
        self._session_id = init_result.session_id
        logger.info(f"ACP session initialized: {self._session_id}")
        return init_result

    # ------------------------------------------------------------------
    # Prompt (non-streaming)
    # ------------------------------------------------------------------

    async def prompt(self, params: PromptParams) -> dict[str, Any]:
        """Send session/prompt and wait for the full result."""
        return await self._call("session/prompt", params.model_dump(exclude_none=True))

    # ------------------------------------------------------------------
    # Streaming prompt
    # ------------------------------------------------------------------

    async def prompt_stream(self, params: PromptParams) -> AsyncIterator[ProgressParams]:
        """
        Send session/prompt with stream=True and yield ProgressParams events
        as they arrive from kiro-cli.

        Each yielded event is a real-time ACP progress notification —
        the gateway does NOT buffer or re-aggregate them.
        """
        session_id = params.session_id
        queue: Queue = Queue()
        self._progress_queues[session_id] = queue

        try:
            p = params.model_copy(update={"stream": True})
            # Fire-and-forget the request; responses arrive as notifications
            asyncio.create_task(
                self._send(JsonRpcRequest(method="session/prompt",
                                         params=p.model_dump(exclude_none=True)))
            )

            while True:
                event: ProgressParams = await queue.get()
                yield event
                if event.type in ("done", "error"):
                    break
        finally:
            self._progress_queues.pop(session_id, None)

    # ------------------------------------------------------------------
    # Capability request handling (kiro-cli → gateway)
    # ------------------------------------------------------------------

    async def capability_requests(self, session_id: str) -> AsyncIterator[tuple[str, dict]]:
        """
        Yield (method, params) capability requests that kiro-cli sends
        to the gateway during a session (readFile, writeFile, etc.).
        """
        queue: Queue = Queue()
        self._capability_queues[session_id] = queue
        try:
            while True:
                item = await queue.get()
                if item is None:  # sentinel
                    break
                yield item
        finally:
            self._capability_queues.pop(session_id, None)

    async def send_capability_result(self, request_id: str, result: Any) -> None:
        """Send a capability result back to kiro-cli."""
        response = JsonRpcResponse(id=request_id, result=result)
        await self._write_line(response.model_dump_json())

    async def send_capability_error(self, request_id: str, code: int, message: str) -> None:
        """Send a capability error back to kiro-cli."""
        from kiro.acp_models import JsonRpcError
        response = JsonRpcResponse(
            id=request_id,
            error=JsonRpcError(code=code, message=message)
        )
        await self._write_line(response.model_dump_json())

    # ------------------------------------------------------------------
    # New session (for concurrent requests)
    # ------------------------------------------------------------------

    async def new_session(self, capabilities: Optional[GatewayCapabilities] = None) -> str:
        """Initialize a fresh session and return its ID."""
        result = await self.initialize(capabilities)
        return result.session_id

    # ------------------------------------------------------------------
    # Internal: JSON-RPC plumbing
    # ------------------------------------------------------------------

    async def _call(self, method: str, params: dict) -> Any:
        """Send a request and await its response."""
        req_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        req = JsonRpcRequest(id=req_id, method=method, params=params)
        await self._send(req)
        response: JsonRpcResponse = await asyncio.wait_for(future, timeout=120.0)
        if response.error:
            raise ACPError(response.error.code, response.error.message, response.error.data)
        return response.result

    async def _send(self, req: JsonRpcRequest) -> None:
        await self._write_line(req.model_dump_json())

    async def _write_line(self, line: str) -> None:
        async with self._write_lock:
            if self._proc and self._proc.stdin:
                self._proc.stdin.write((line + "\n").encode())
                await self._proc.stdin.drain()

    async def _read_loop(self) -> None:
        """Read lines from kiro-cli stdout and dispatch to waiters or queues."""
        assert self._proc and self._proc.stdout
        while True:
            try:
                raw = await self._proc.stdout.readline()
                if not raw:
                    logger.warning("kiro-cli stdout closed")
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                self._dispatch(line)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"ACP read_loop error: {exc}")

    def _dispatch(self, line: str) -> None:
        """Parse a JSON-RPC line and route it to the correct handler."""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(f"ACP: unparseable line: {line[:200]}")
            return

        # Notification (no id field or id is null)
        if "method" in msg and not msg.get("id"):
            self._handle_notification(msg)
            return

        # Response
        msg_id = str(msg.get("id", ""))
        future = self._pending.pop(msg_id, None)
        if future and not future.done():
            future.set_result(JsonRpcResponse(**msg))

    def _handle_notification(self, msg: dict) -> None:
        method = msg.get("method", "")
        params = msg.get("params", {})
        session_id = params.get("session_id", self._session_id or "")

        if method == "session/progress":
            queue = self._progress_queues.get(session_id)
            if queue:
                queue.put_nowait(ProgressParams(**params))
            return

        if method.startswith("capability/"):
            cap_queue = self._capability_queues.get(session_id)
            req_id = str(msg.get("id", ""))
            if cap_queue:
                cap_queue.put_nowait((method, req_id, params))
            else:
                # No capability handler registered — send not-supported error
                asyncio.create_task(
                    self.send_capability_error(req_id, -32601, f"{method} not supported")
                )
            return

        logger.debug(f"ACP unhandled notification: {method}")
