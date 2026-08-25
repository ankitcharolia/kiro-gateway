"""Core streaming primitives shared across shim layers."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, Iterator, List, Optional

from loguru import logger


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
# Keepalive
# ---------------------------------------------------------------------------

#: Sentinel yielded by :func:`iter_with_keepalive` when the wrapped iterator has
#: produced nothing for a whole interval. Compared by identity, so it can never
#: be confused with a real event (which is always a ``dict``).
KEEPALIVE = object()


async def iter_with_keepalive(
    source: AsyncIterator[Any],
    interval: float,
) -> AsyncIterator[Any]:
    """Yield from ``source``, injecting :data:`KEEPALIVE` while it is idle.

    kiro-cli emits no ACP notification for as long as one of its built-in tools
    is running, so a streaming turn can put nothing on the wire for minutes (a
    live probe measured 40.02s of silence for a 40s ``sleep``, scaling 1:1 with
    the tool's runtime). Harnesses abort a stream that stays silent — Claude
    Code's watchdog gives up after 300s with "API Error: The operation timed
    out." This wrapper turns "nothing arrived for ``interval`` seconds" into a
    sentinel the caller renders as its protocol's no-op frame, leaving real
    events untouched.

    Cancellation semantics are preserved: the in-flight pull is cancelled and
    ``source`` is closed on teardown, so ``prompt_stream``'s finally-block still
    runs and tells kiro-cli to abandon the turn when the client disconnects.

    Args:
        source: The async iterator to consume.
        interval: Seconds of silence before a keepalive is emitted. Values <= 0
            disable keepalives and stream ``source`` through unchanged.

    Yields:
        Every item produced by ``source``, interleaved with :data:`KEEPALIVE`
        sentinels for each whole ``interval`` that passed without an item.
    """
    if interval <= 0:
        async for item in source:
            yield item
        return

    iterator = source.__aiter__()
    pending: Optional[asyncio.Future] = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                # Still waiting on kiro-cli (typically a built-in tool run) —
                # prove to the client that the connection is alive. The same
                # pull stays in flight, so no event can be missed or reordered.
                yield KEEPALIVE
                continue
            task, pending = pending, None
            try:
                item = task.result()
            except StopAsyncIteration:
                return
            yield item
    finally:
        if pending is not None:
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
            except Exception as exc:  # noqa: BLE001 — teardown must not mask
                # The source failed while we were tearing down (e.g. client
                # disconnect racing an upstream error). The caller is already
                # unwinding, so log rather than replace its exception.
                logger.debug(f"Keepalive teardown: source raised {exc!r}")
        aclose = getattr(source, "aclose", None)
        if aclose is not None:
            await aclose()


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
    # Legacy fields kept for backward compat
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


# ---------------------------------------------------------------------------
# _process_chunk — convert a raw Kiro JSON event dict into a KiroEvent
# ---------------------------------------------------------------------------

def _process_chunk(chunk: Dict[str, Any]) -> Optional[KiroEvent]:
    """Convert a raw Kiro API event dict into a KiroEvent, or None to skip."""
    etype = chunk.get("type") or chunk.get("event", "")

    if etype in ("content_block_delta", "delta"):
        delta = chunk.get("delta", {})
        dtype = delta.get("type", "")
        if dtype == "text_delta":
            return KiroEvent(type="content", content=delta.get("text", ""))
        if dtype == "thinking_delta":
            return KiroEvent(type="thinking", thinking_content=delta.get("thinking", ""))
        if dtype == "input_json_delta":
            return KiroEvent(type="tool_use", tool_use=delta)
        return None

    if etype == "content_block_start":
        block = chunk.get("content_block", {})
        if block.get("type") == "thinking":
            return KiroEvent(type="thinking", thinking_content="", is_first_thinking_chunk=True)
        return None

    if etype == "content_block_stop":
        return KiroEvent(type="thinking", thinking_content="", is_last_thinking_chunk=True)

    if etype == "message_delta":
        usage = chunk.get("usage", {})
        return KiroEvent(type="usage", usage=usage)

    if etype == "message_stop":
        return KiroEvent(type="stop")

    if etype == "context_usage":
        pct = chunk.get("context_usage_percentage") or chunk.get("data", {}).get(
            "context_usage_percentage"
        )
        return KiroEvent(type="context_usage", context_usage_percentage=pct)

    return None


# ---------------------------------------------------------------------------
# parse_kiro_stream — async generator that yields KiroEvents
# ---------------------------------------------------------------------------

async def parse_kiro_stream(
    response_stream: AsyncIterator[bytes],
) -> AsyncIterator[KiroEvent]:
    """Yield KiroEvent objects from a raw Kiro HTTP response stream."""
    async for raw_event in aiter_sse_events(response_stream):
        evt = _process_chunk(raw_event)
        if evt is not None:
            yield evt


# ---------------------------------------------------------------------------
# collect_stream_to_result
# ---------------------------------------------------------------------------

async def collect_stream_to_result(
    event_stream: AsyncIterator[KiroEvent],
) -> StreamResult:
    """Consume *event_stream* and return a StreamResult."""
    result = StreamResult()
    async for evt in event_stream:
        if evt.type == "content" and evt.content:
            result.content += evt.content
            result.text += evt.content
        elif evt.type == "thinking" and evt.thinking_content:
            result.thinking_content += evt.thinking_content
        elif evt.type == "tool_use" and evt.tool_use:
            result.tool_calls.append(evt.tool_use)
        elif evt.type == "usage" and evt.usage:
            result.usage = evt.usage
            result.input_tokens = evt.usage.get("input_tokens", result.input_tokens)
            result.output_tokens = evt.usage.get("output_tokens", result.output_tokens)
        elif evt.type == "context_usage":
            result.context_usage_percentage = evt.context_usage_percentage
    return result


def calculate_tokens_from_context_usage(
    context_usage_percentage: float,
    max_context_tokens: int,
) -> int:
    """Derive used context tokens from the percentage reported by Kiro API."""
    return int(max_context_tokens * context_usage_percentage / 100.0)


# ---------------------------------------------------------------------------
# stream_with_first_token_retry
# ---------------------------------------------------------------------------

async def stream_with_first_token_retry(
    stream_factory: Callable[[], AsyncIterator[KiroEvent]],
    first_token_timeout: float = 30.0,
    max_retries: int = 2,
) -> AsyncIterator[KiroEvent]:
    """Wrap *stream_factory* with a first-token timeout + retry loop."""
    attempt = 0
    while True:
        attempt += 1
        stream = stream_factory()
        try:
            async for evt in stream:
                yield evt
            return
        except (asyncio.TimeoutError, FirstTokenTimeoutError):
            if attempt > max_retries:
                raise FirstTokenTimeoutError(first_token_timeout)
            continue
        except Exception:
            raise
