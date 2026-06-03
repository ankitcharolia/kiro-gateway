"""Execute ACP capability round-trips (tool calls → results → resume)."""
from __future__ import annotations
import json
from typing import Any


class CapabilityExecutor:
    """Handles multi-turn tool-call round-trips within a single ACP session."""

    def __init__(self, acp_client: Any, session_id: str) -> None:
        self._client = acp_client
        self._session_id = session_id

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
