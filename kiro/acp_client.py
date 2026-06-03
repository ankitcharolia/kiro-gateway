# -*- coding: utf-8 -*-
"""
ACP (Agent Client Protocol) client for kiro-cli.

This module implements a JSON-RPC 2.0 ACP client that communicates with
kiro-cli over stdio (subprocess). This is the OFFICIAL, approved way to
integrate with Kiro — kiro-cli is the authorized client, and ACP is the
open standard protocol it exposes.

Spec: https://agentclientprotocol.com
Kiro ACP docs: https://kiro.dev/docs/cli/acp/

Protocol flow:
    Client                          kiro-cli (ACP agent)
       |-- initialize          -->      |
       |<- InitializeResult    ---      |
       |-- session/new         -->      |
       |<- SessionNewResult    ---      |
       |-- session/prompt      -->      |
       |<- session/update (*)  ---      |  (streamed notifications)
       |<- PromptResult        ---      |
"""

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional, Any
from loguru import logger


ACP_PROTOCOL_VERSION = "0.1"
DEFAULT_KIRO_CLI_CMD = "kiro-cli"


# ---------------------------------------------------------------------------
# ACP Message Types (JSON-RPC 2.0 over stdio)
# ---------------------------------------------------------------------------

@dataclass
class JsonRpcRequest:
    method: str
    params: dict
    id: int

    def to_dict(self) -> dict:
        return {"jsonrpc": "2.0", "id": self.id, "method": self.method, "params": self.params}


@dataclass
class JsonRpcNotification:
    method: str
    params: dict

    def to_dict(self) -> dict:
        return {"jsonrpc": "2.0", "method": self.method, "params": self.params}


# ---------------------------------------------------------------------------
# ACP Session Update subtypes
# Ref: https://www.philschmid.de/acp-overview (Protocol Events table)
# ---------------------------------------------------------------------------

UPDATE_AGENT_MESSAGE_CHUNK = "agent_message_chunk"
UPDATE_THOUGHT_MESSAGE_CHUNK = "thought_message_chunk"
UPDATE_USER_MESSAGE_CHUNK = "user_message_chunk"
UPDATE_TOOL_CALL = "tool_call"
UPDATE_TOOL_CALL_UPDATE = "tool_call_update"
UPDATE_PLAN = "plan"
UPDATE_MODE_CHANGE = "mode_change"
UPDATE_AVAILABLE_COMMANDS = "available_commands"


@dataclass
class SessionUpdate:
    """Parsed session/update notification from the ACP agent."""
    session_id: str
    update_type: str
    data: dict


@dataclass
class PromptResult:
    """Final result of a session/prompt call."""
    session_id: str
    stop_reason: str  # e.g. "end_turn", "cancelled", "error"
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# KiroCLIProcess — manages a single kiro-cli subprocess
# ---------------------------------------------------------------------------

class KiroCLIProcess:
    """
    Manages a single kiro-cli ACP subprocess.

    kiro-cli is spawned with `kiro-cli acp` which starts it in ACP mode,
    communicating over stdin/stdout using JSON-RPC 2.0 with newline-delimited
    messages (one JSON object per line).
    """

    def __init__(self, kiro_cli_cmd: str = DEFAULT_KIRO_CLI_CMD, cwd: Optional[str] = None):
        self.kiro_cli_cmd = kiro_cli_cmd
        self.cwd = cwd or os.getcwd()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._update_callbacks: list[Callable[[SessionUpdate], None]] = []
        self._reader_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.returncode is None

    def on_update(self, callback: Callable[[SessionUpdate], None]) -> None:
        """Register a callback for session/update notifications."""
        self._update_callbacks.append(callback)

    def remove_update_callback(self, callback: Callable[[SessionUpdate], None]) -> None:
        self._update_callbacks = [c for c in self._update_callbacks if c is not callback]

    async def start(self) -> None:
        """Start the kiro-cli subprocess in ACP mode."""
        cmd = self.kiro_cli_cmd
        if not shutil.which(cmd):
            raise FileNotFoundError(
                f"kiro-cli not found: '{cmd}'.\n"
                "Install it from https://kiro.dev/docs/cli/ and ensure it's in PATH.\n"
                "Then log in with: kiro-cli auth login"
            )

        logger.info(f"Starting kiro-cli ACP subprocess: {cmd} acp")
        self._process = await asyncio.create_subprocess_exec(
            cmd, "acp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info(f"kiro-cli ACP process started (pid={self._process.pid})")

    async def stop(self) -> None:
        """Gracefully terminate the kiro-cli subprocess."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            except Exception as e:
                logger.warning(f"Error stopping kiro-cli process: {e}")

        self._process = None
        self._initialized = False
        logger.info("kiro-cli ACP process stopped")

    # ------------------------------------------------------------------
    # ACP Protocol Methods
    # ------------------------------------------------------------------

    async def initialize(self) -> dict:
        """
        Send ACP `initialize` handshake.

        Required first message. Negotiates protocol version and capabilities.
        Spec: https://agentclientprotocol.com/protocol/v1/overview
        """
        result = await self._call("initialize", {
            "protocolVersion": ACP_PROTOCOL_VERSION,
            "client": {
                "name": "kiro-gateway",
                "version": "1.0.0",
            },
            "capabilities": {
                "sessions": True,
            }
        })
        self._initialized = True
        logger.info(f"ACP initialized: {result}")
        return result

    async def session_new(self, cwd: Optional[str] = None) -> str:
        """
        Create a new ACP session.

        Returns session_id (str).
        """
        self._ensure_initialized()
        result = await self._call("session/new", {
            "cwd": cwd or self.cwd,
        })
        session_id = result.get("sessionId") or result.get("session_id") or result.get("id")
        if not session_id:
            raise RuntimeError(f"session/new returned no session ID: {result}")
        logger.debug(f"ACP session created: {session_id}")
        return session_id

    async def session_prompt(
        self,
        session_id: str,
        text: str,
        mcp_servers: Optional[list] = None,
        images: Optional[list] = None,
    ) -> AsyncIterator[SessionUpdate]:
        """
        Send a prompt to an ACP session and stream session/update notifications.

        Yields SessionUpdate objects as they arrive (streaming via notifications).
        The final item before StopAsyncIteration is a PromptResult embedded
        as a SessionUpdate with update_type='done'.

        Spec method: session/prompt
        Streaming: session/update notifications (JSON-RPC notifications, no id)
        """
        self._ensure_initialized()

        update_queue: asyncio.Queue[Optional[SessionUpdate]] = asyncio.Queue()

        def _on_update(update: SessionUpdate) -> None:
            if update.session_id == session_id:
                update_queue.put_nowait(update)

        self.on_update(_on_update)

        params: dict[str, Any] = {
            "sessionId": session_id,
            "prompt": {
                "content": [{"type": "text", "text": text}],
            },
        }
        if mcp_servers:
            params["mcpServers"] = mcp_servers

        try:
            # Send the prompt request (response comes as the final RPC result)
            prompt_future = asyncio.get_event_loop().create_future()
            req_id = self._next_id()
            self._pending[req_id] = prompt_future

            msg = JsonRpcRequest(method="session/prompt", params=params, id=req_id)
            await self._send(msg.to_dict())

            # Stream updates until the prompt call completes
            while True:
                try:
                    # Check if prompt completed
                    if prompt_future.done():
                        # Drain remaining queued updates
                        while not update_queue.empty():
                            upd = update_queue.get_nowait()
                            if upd is not None:
                                yield upd
                        break

                    # Wait for next update (with timeout to check future)
                    try:
                        update = await asyncio.wait_for(
                            asyncio.shield(update_queue.get()),
                            timeout=0.1
                        )
                        if update is not None:
                            yield update
                    except asyncio.TimeoutError:
                        continue

                except Exception as e:
                    logger.error(f"Error streaming ACP updates: {e}")
                    break

            # Yield a final 'done' update with the prompt result
            try:
                result = await asyncio.wait_for(prompt_future, timeout=5.0)
                stop_reason = result.get("stopReason") or result.get("stop_reason", "end_turn")
                yield SessionUpdate(
                    session_id=session_id,
                    update_type="done",
                    data={"stop_reason": stop_reason, "result": result},
                )
            except asyncio.TimeoutError:
                yield SessionUpdate(
                    session_id=session_id,
                    update_type="done",
                    data={"stop_reason": "end_turn"},
                )

        finally:
            self.remove_update_callback(_on_update)

    async def session_cancel(self, session_id: str) -> None:
        """Cancel an in-progress prompt on a session."""
        if not self._initialized:
            return
        await self._send({"jsonrpc": "2.0", "method": "session/cancel",
                          "params": {"sessionId": session_id}})

    # ------------------------------------------------------------------
    # Internal: JSON-RPC transport over stdio
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("ACP client not initialized. Call initialize() first.")
        if not self.is_alive:
            raise RuntimeError("kiro-cli process is not running.")

    async def _send(self, data: dict) -> None:
        """Write a JSON-RPC message to kiro-cli stdin (newline-delimited)."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("kiro-cli process stdin is not available")
        line = json.dumps(data, separators=(",", ":")) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    async def _call(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request and await its response."""
        req_id = self._next_id()
        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        msg = JsonRpcRequest(method=method, params=params, id=req_id)
        await self._send(msg.to_dict())

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"ACP call '{method}' timed out after 30s")

    async def _read_loop(self) -> None:
        """Continuously read newline-delimited JSON from kiro-cli stdout."""
        if not self._process or not self._process.stdout:
            return

        try:
            while self.is_alive:
                try:
                    line = await asyncio.wait_for(
                        self._process.stdout.readline(), timeout=60.0
                    )
                except asyncio.TimeoutError:
                    continue

                if not line:
                    logger.warning("kiro-cli stdout EOF — process likely exited")
                    break

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"ACP: invalid JSON from kiro-cli: {e} | line={line_str[:200]}")
                    continue

                await self._dispatch(msg)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"ACP read loop error: {e}")

    async def _dispatch(self, msg: dict) -> None:
        """Route an incoming JSON-RPC message to the correct handler."""
        msg_id = msg.get("id")
        method = msg.get("method")
        error = msg.get("error")
        result = msg.get("result")

        # JSON-RPC Response (has id, no method)
        if msg_id is not None and method is None:
            future = self._pending.pop(msg_id, None)
            if future and not future.done():
                if error:
                    future.set_exception(RuntimeError(
                        f"ACP error {error.get('code')}: {error.get('message')}"
                    ))
                else:
                    future.set_result(result or {})
            return

        # JSON-RPC Notification (no id, has method)
        if method == "session/update" and msg.get("params"):
            params = msg["params"]
            session_id = params.get("sessionId") or params.get("session_id", "")
            update_data = params.get("update", {})
            update_type = update_data.get("type", "unknown")
            update = SessionUpdate(
                session_id=session_id,
                update_type=update_type,
                data=update_data,
            )
            for cb in list(self._update_callbacks):
                try:
                    cb(update)
                except Exception as e:
                    logger.warning(f"ACP update callback error: {e}")
