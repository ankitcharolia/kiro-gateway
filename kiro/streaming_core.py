"""Core streaming primitives shared across shim layers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# A single ACP stream event represented as a plain dict.
KiroEvent = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_sse_line(line: str) -> Optional[KiroEvent]:
    """Parse a raw SSE ``data:`` line into a KiroEvent dict.

    Returns *None* for keep-alive lines and ``[DONE]`` sentinels.
    """
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
    """Yield parsed KiroEvent dicts from a multi-line SSE string."""
    for line in raw.splitlines():
        event = parse_sse_line(line)
        if event is not None:
            yield event


async def aiter_sse_events(stream: AsyncIterator[bytes]) -> AsyncIterator[KiroEvent]:
    """Async variant — yield KiroEvent dicts from a byte-stream."""
    async for chunk in stream:
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            event = parse_sse_line(line)
            if event is not None:
                yield event


# ---------------------------------------------------------------------------
# Backward-compat addition expected by tests
# ---------------------------------------------------------------------------

@dataclass
class StreamResult:
    """Aggregated result of consuming a complete ACP stream."""
    events: List[KiroEvent] = field(default_factory=list)
    text: str = ""
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
