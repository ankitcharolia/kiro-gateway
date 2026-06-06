"""Execute ACP capability round-trips (tool calls → results → resume)."""
from __future__ import annotations
import json
from typing import Any


class CapabilityError(Exception):
    """Raised when a capability request cannot be fulfilled."""

    def __init__(self, message: str, code: int = -32000) -> None:
        self.code = code
        super().__init__(message)


class CapabilityExecutor:
    """Handles multi-turn tool-call round-trips within a single ACP session."""

    def __init__(
        self,
        acp_client: Any = None,
        session_id: str = "",
        filesystem_roots: list[Any] | None = None,
        terminal: Any = None,
    ) -> None:
        self._client = acp_client
        self._session_id = session_id
        self._filesystem_roots = filesystem_roots or []
        self._terminal = terminal

    async def handle(self, method: str, params: Any) -> Any:
        """Dispatch a capability method to the appropriate handler."""
        handlers = {
            "readFile": self._read_file,
            "writeFile": self._write_file,
            "runCommand": self._run_command,
            "listDirectory": self._list_directory,
        }
        handler = handlers.get(method)
        if handler is None:
            raise CapabilityError(f"Unknown capability method: {method}", code=-32601)
        return await handler(params)

    async def execute_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_call_id: str,
    ) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": f"Result of {tool_name}",
        }

    async def run_tool_round_trip(
        self,
        tool_calls: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        tool_results: list[dict[str, Any]] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                inp = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                inp = {}
            result = await self.execute_tool_call(name, inp, tc.get("id", ""))
            tool_results.append(result)

        resume_messages = messages + [{"role": "user", "content": tool_results}]
        return await self._client.prompt(
            session_id=self._session_id,
            messages=resume_messages,
        )

    # ------------------------------------------------------------------
    # Capability handlers
    # ------------------------------------------------------------------

    async def _read_file(self, params: Any) -> Any:
        path = params.get("path", "") if isinstance(params, dict) else getattr(params, "path", "")
        raise CapabilityError(f"readFile not supported: {path}")

    async def _write_file(self, params: Any) -> Any:
        path = params.get("path", "") if isinstance(params, dict) else getattr(params, "path", "")
        raise CapabilityError(f"writeFile not supported: {path}")

    async def _run_command(self, params: Any) -> Any:
        raise CapabilityError("runCommand not supported")

    async def _list_directory(self, params: Any) -> Any:
        path = params.get("path", "") if isinstance(params, dict) else getattr(params, "path", "")
        raise CapabilityError(f"listDirectory not supported: {path}")
