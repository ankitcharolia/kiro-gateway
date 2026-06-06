"""Core streaming primitives shared across shim layers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

KiroEvent = Dict[str, Any]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FirstTokenTimeoutError(TimeoutError):
    """Raised when no token is received within the first-token timeout window."""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"No token received within {timeout_seconds}s first-token timeout."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_sse_line(line: str) -> Optional[KiroEvent]:
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


def iter_sse_events(raw: str) -> Iterator[KiroEvent]:
    for line in raw.splitlines():
        event = parse_sse_line(line)
        if event is not None:
            yield event


async def aiter_sse_events(stream: AsyncIterator[bytes]) -> AsyncIterator[KiroEvent]:
    async for chunk in stream:
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            event = parse_sse_line(line)
            if event is not None:
                yield event


@dataclass
class StreamResult:
    events: List[KiroEvent] = field(default_factory=list)
    text: str = ""
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
