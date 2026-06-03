"""
Unit tests for ShimService — the ACP orchestration layer.
Verifies event translation for text, tool_call, thinking, error, and done events.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from kiro.shim_service import ShimService


# ---------------------------------------------------------------------------
# Stub ACP client with configurable event stream
# ---------------------------------------------------------------------------

class ConfigurableStubACP:
    def __init__(self, events: list[dict]):
        self._events = events

    async def create_session(self) -> str:
        return "shim-test-session"

    async def prompt(self, session_id: str, messages, **kwargs) -> dict:
        # Return last text event content as the non-streaming response
        texts = [e["content"] for e in self._events if e.get("type") == "text"]
        return {
            "session_id": session_id,
            "content": "".join(texts),
            "finish_reason": "stop",
            "tool_calls": [],
        }

    async def prompt_stream(self, session_id: str, messages, **kwargs):
        for event in self._events:
            yield event

    async def close_session(self, session_id: str):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def collect_stream(gen) -> list[dict]:
    results = []
    async for item in gen:
        results.append(item)
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shim_service_text_stream():
    """ShimService yields text events from the ACP stream."""
    acp = ConfigurableStubACP([
        {"type": "text", "content": "Hello "},
        {"type": "text", "content": "world"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    msgs = [{"role": "user", "content": "Hi"}]

    events = await collect_stream(svc.stream_tokens(msgs))
    text_events = [e for e in events if e.get("type") == "text"]
    assert len(text_events) >= 1
    combined = "".join(e["content"] for e in text_events)
    assert "Hello" in combined


@pytest.mark.asyncio
async def test_shim_service_done_event():
    """ShimService emits a done event at stream end."""
    acp = ConfigurableStubACP([
        {"type": "text", "content": "Done."},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "go"}]))
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) >= 1


@pytest.mark.asyncio
async def test_shim_service_error_event():
    """ShimService propagates error events from ACP."""
    acp = ConfigurableStubACP([
        {"type": "error", "message": "kiro CLI crashed"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "go"}]))
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1


@pytest.mark.asyncio
async def test_shim_service_tool_call_event():
    """ShimService passes through tool_call events from ACP."""
    acp = ConfigurableStubACP([
        {"type": "tool_call", "id": "call_1", "name": "read_file", "arguments": "{\"path\": \"/tmp/x\"}"},
        {"type": "done", "finish_reason": "tool_calls"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "read it"}]))
    tool_events = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_events) >= 1
    assert tool_events[0].get("name") == "read_file"


@pytest.mark.asyncio
async def test_shim_service_thinking_event():
    """ShimService passes through thinking events from ACP."""
    acp = ConfigurableStubACP([
        {"type": "thinking", "content": "Let me think..."},
        {"type": "text", "content": "Answer"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "think"}]))
    thinking_events = [e for e in events if e.get("type") == "thinking"]
    assert len(thinking_events) >= 1


@pytest.mark.asyncio
async def test_shim_service_non_streaming_complete():
    """ShimService.complete() returns aggregated text for non-streaming callers."""
    acp = ConfigurableStubACP([
        {"type": "text", "content": "Paris"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    result = await svc.complete([{"role": "user", "content": "Capital of France?"}])
    assert isinstance(result, dict)
    assert "content" in result or "text" in str(result)
