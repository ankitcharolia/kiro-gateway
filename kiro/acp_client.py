# -*- coding: utf-8 -*-
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from kiro.acp_models import JsonRpcRequest


class ACPSubprocessError(RuntimeError):
    pass


class ACPClient:
    """Minimal JSON-RPC bridge to an official `kiro` CLI ACP subprocess.

    This implementation intentionally keeps Kiro authentication and execution
    in the official CLI. The gateway only forwards protocol messages.
    """

    def __init__(self, command: str = "kiro"):
        self.command = command
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._notifications: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self.process is not None:
            return
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            "acp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("Started kiro ACP subprocess")

    async def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        await self.process.wait()
        self.process = None
        if self._reader_task:
            self._reader_task.cancel()
        logger.info("Stopped kiro ACP subprocess")

    async def _read_loop(self) -> None:
        assert self.process and self.process.stdout
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
            raw = line.decode("utf-8").strip()
            if not raw:
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"Non-JSON ACP output: {raw}")
                continue
            if "id" in message and (message.get("result") is not None or message.get("error") is not None):
                future = self._pending.pop(str(message["id"]), None)
                if future and not future.done():
                    future.set_result(message)
            else:
                await self._notifications.put(message)

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await self.start()
        async with self._lock:
            request_id = str(uuid.uuid4())
            req = JsonRpcRequest(id=request_id, method=method, params=params or {})
            payload = req.model_dump_json() + "\n"
            assert self.process and self.process.stdin
            future = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future
            self.process.stdin.write(payload.encode("utf-8"))
            await self.process.stdin.drain()
        response = await future
        if response.get("error"):
            raise ACPSubprocessError(response["error"].get("message", "ACP error"))
        return response.get("result", {})

    async def initialize(self) -> dict[str, Any]:
        return await self.request(
            "initialize",
            {
                "protocolVersion": "0.5",
                "clientInfo": {"name": "kiro-gateway", "version": "2.0.0"},
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
            },
        )

    async def new_session(self, cwd: str | None = None, mode: str | None = None) -> dict[str, Any]:
        return await self.request(
            "session/new",
            {"cwd": cwd or str(Path.cwd()), "mode": mode},
        )

    async def prompt(self, session_id: str, prompt: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        response_task = asyncio.create_task(
            self.request("session/prompt", {"sessionId": session_id, "prompt": prompt})
        )
        updates: list[dict[str, Any]] = []
        while not response_task.done():
            try:
                update = await asyncio.wait_for(self._notifications.get(), timeout=0.15)
                updates.append(update)
            except asyncio.TimeoutError:
                continue
        response = await response_task
        return response, updates
