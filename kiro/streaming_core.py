"""Core streaming primitives shared across shim layers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FirstTokenTimeoutError(TimeoutError):
    """Raised when no token is received within the first-token timeout."""
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(f"No token received within {timeout_seconds}s first-token timeout.")


# ---------------------------------------------------------------------------
# KiroEvent dataclass
# ---------------------------------------------------------------------------

@dataclass
class KiroEvent:
    """A single event emitted by the Kiro streaming API."""
    type: str
    content: Optional[str] = None
    thinking_content: Optional[str] = None
    tool_use: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None
    context_usage_percentage: Optional[float] = None
    is_first_thinking_chunk: bool = False
    is_last_thinking_chunk: bool = False


# ---------------------------------------------------------------------------
# StreamResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class StreamResult:
    """Accumulated result of consuming a Kiro stream."""
    content: str = ""
    thinking_content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Optional[Dict[str, Any]] = None
    context_usage_percentage: Optional[float] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    text: str = ""
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def parse_sse_line(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line or line == "data: [DONE]":
        return None
    if line.startswith("data:"):
        payload = line[len("data:"):].strip()
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
    return None


def iter_sse_events(raw: str) -> Iterator[Dict[str, Any]]:
    for line in raw.splitlines():
        event = parse_sse_line(line)
        if event is not None:
            yield event


async def aiter_sse_events(stream: AsyncIterator[bytes]) -> AsyncIterator[Dict[str, Any]]:
    async for chunk in stream:
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            event = parse_sse_line(line)
            if event is not None:
                yield event
