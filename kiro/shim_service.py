# -*- coding: utf-8 -*-
from typing import Any

from loguru import logger

from kiro.acp_client import ACPClient


class ShimService:
    def __init__(self, acp_client: ACPClient):
        self.acp_client = acp_client
        self._default_session_id: str | None = None

    async def ensure_session(self) -> str:
        if self._default_session_id is None:
            await self.acp_client.initialize()
            session = await self.acp_client.new_session()
            self._default_session_id = session.get("sessionId") or session.get("id")
            logger.info(f"Created ACP session: {self._default_session_id}")
        return self._default_session_id

    async def run_prompt(self, text: str) -> dict[str, Any]:
        session_id = await self.ensure_session()
        stop, updates = await self.acp_client.prompt(
            session_id,
            [{"type": "text", "text": text}],
        )

        chunks: list[str] = []
        tool_events: list[dict[str, Any]] = []
        for msg in updates:
            params = msg.get("params", {})
            update = params.get("update", {})
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = update.get("content", {})
                if content.get("type") == "text" and content.get("text"):
                    chunks.append(content["text"])
            elif kind in {"tool_call", "tool_call_update", "plan"}:
                tool_events.append(update)

        return {
            "session_id": session_id,
            "stop": stop,
            "text": "".join(chunks).strip(),
            "updates": updates,
            "tool_events": tool_events,
        }
