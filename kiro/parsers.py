"""Protocol parsers for AWS event-stream and SSE data."""
from __future__ import annotations

import json
from typing import Any, Dict, Generator, Iterator, List, Optional, Tuple


# ---------------------------------------------------------------------------
# AWS Event Stream parser
# ---------------------------------------------------------------------------

class AwsEventStreamParser:
    """Minimal parser for AWS event-stream framing."""

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, data: bytes) -> Iterator[Dict[str, Any]]:
        self._buffer += data
        yield from self._drain()

    def _drain(self) -> Iterator[Dict[str, Any]]:
        while True:
            event = self._try_parse_one()
            if event is None:
                break
            yield event

    def _try_parse_one(self) -> Optional[Dict[str, Any]]:
        newline = self._buffer.find(b"\n")
        if newline == -1:
            return None
        line = self._buffer[:newline]
        self._buffer = self._buffer[newline + 1:]
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def flush(self) -> Iterator[Dict[str, Any]]:
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


# ---------------------------------------------------------------------------
# Brace / bracket parsing helpers (expected by tests)
# ---------------------------------------------------------------------------

def find_matching_brace(text: str, start: int) -> int:
    """Return the index of the closing ``}`` that matches the ``{`` at *start*.

    Returns -1 if no matching brace is found.
    """
    if start >= len(text) or text[start] != "{":
        return -1

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_bracket_tool_calls(
    text: str,
) -> List[Dict[str, Any]]:
    """Extract all top-level JSON objects from *text*.

    Returns a list of parsed dicts; skips malformed objects.
    """
    results: List[Dict[str, Any]] = []
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        end = find_matching_brace(text, start)
        if end == -1:
            break
        fragment = text[start : end + 1]
        try:
            obj = json.loads(fragment)
            if isinstance(obj, dict):
                results.append(obj)
        except json.JSONDecodeError:
            pass
        i = end + 1
    return results


def deduplicate_tool_calls(
    tool_calls: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Remove duplicate tool calls, preserving order.

    Two calls are considered duplicates when they share the same ``name``
    and ``input`` (or ``arguments``) values.
    """
    seen: List[str] = []
    unique: List[Dict[str, Any]] = []
    for call in tool_calls:
        key = json.dumps(
            {"name": call.get("name"), "input": call.get("input", call.get("arguments"))},
            sort_keys=True,
        )
        if key not in seen:
            seen.append(key)
            unique.append(call)
    return unique
