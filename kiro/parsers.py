"""Protocol parsers for AWS event-stream and SSE data."""
from __future__ import annotations

import json
from typing import Any, Dict, Generator, Iterator, Optional


# ---------------------------------------------------------------------------
# AWS Event Stream parser
# ---------------------------------------------------------------------------

class AwsEventStreamParser:
    """Minimal parser for AWS event-stream framing.

    The kiro CLI communicates via a JSON-RPC + ACP protocol over stdio;
    this parser handles the lower-level framing layer used in some transport
    modes and in tests that replay captured payloads.
    """

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, data: bytes) -> Iterator[Dict[str, Any]]:
        """Feed raw bytes and yield fully-parsed event dicts."""
        self._buffer += data
        yield from self._drain()

    def _drain(self) -> Iterator[Dict[str, Any]]:
        """Attempt to parse as many complete events as possible."""
        while True:
            event = self._try_parse_one()
            if event is None:
                break
            yield event

    def _try_parse_one(self) -> Optional[Dict[str, Any]]:
        """Try to parse one newline-delimited JSON object from the buffer."""
        newline = self._buffer.find(b"\n")
        if newline == -1:
            return None
        line = self._buffer[:newline]
        self._buffer = self._buffer[newline + 1 :]
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def flush(self) -> Iterator[Dict[str, Any]]:
        """Yield any remaining partial event from the buffer."""
        if self._buffer.strip():
            try:
                yield json.loads(self._buffer)
            except json.JSONDecodeError:
                pass
        self._buffer = b""


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def parse_sse_chunk(raw: str) -> Optional[Dict[str, Any]]:
    """Parse a single SSE ``data:`` line into a dict, or return None."""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                return None
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return None
    return None
