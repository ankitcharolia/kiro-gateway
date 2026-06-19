"""
Unit tests for ShimService — the ACP orchestration layer.
Verifies event translation for text, tool_call, thinking, error, and done events.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from kiro.shim_service import ShimService


# ---------------------------------------------------------------------------
# Stub ACP client matching ACPClient's interface used by ShimService
# ---------------------------------------------------------------------------

class StubACP:
    """Minimal ACP client stub for ShimService unit tests."""

    def __init__(self, stream_events: list[dict], prompt_result: dict | None = None):
        self._events = stream_events
        self._prompt_result = prompt_result or {
            "content": "".join(
                e.get("content", "") for e in stream_events if e.get("type") == "text"
            ),
            "finish_reason": "stop",
            "tool_calls": [],
            "usage": {},
        }
        # Records the model passed to new_session so tests can assert forwarding.
        self.last_model: str | None = None
        self.available_models: list[dict] = []

    async def new_session(self, capabilities=None, cwd=None, model=None) -> str:
        self.last_model = model
        return "stub-session-id"

    async def prompt(self, params) -> dict:
        return self._prompt_result

    async def prompt_stream(self, params):
        for event in self._events:
            yield event

    async def capability_requests(self, session_id: str):
        # Empty async generator — no capability requests in unit tests
        return
        yield  # make it an async generator


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
    acp = StubACP([
        {"type": "text", "content": "Hello "},
        {"type": "text", "content": "world"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "Hi"}]))
    text_events = [e for e in events if e.get("type") == "text"]
    assert len(text_events) >= 1
    combined = "".join(e.get("content", "") for e in text_events)
    assert "Hello" in combined


@pytest.mark.asyncio
async def test_shim_service_done_event():
    """ShimService emits a done event at stream end."""
    acp = StubACP([
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
    acp = StubACP([{"type": "error", "message": "kiro CLI crashed"}])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "go"}]))
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1


@pytest.mark.asyncio
async def test_shim_service_tool_call_event():
    """ShimService passes through tool_call events from ACP."""
    acp = StubACP([
        {"type": "tool_call", "id": "call_1", "name": "read_file", "arguments": '{"path": "/tmp/x"}'},
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
    acp = StubACP([
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
    """ShimService.complete() returns aggregated result for non-streaming callers."""
    acp = StubACP(
        stream_events=[],
        prompt_result={"content": "Paris", "finish_reason": "stop", "tool_calls": [], "usage": {}},
    )
    svc = ShimService(acp)
    result = await svc.complete([{"role": "user", "content": "Capital of France?"}])
    assert isinstance(result, dict)
    assert result.get("content") == "Paris"


# ---------------------------------------------------------------------------
# Model forwarding + catalogue exposure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_forwards_model_to_new_session():
    """complete() passes the requested model down to ACPClient.new_session."""
    acp = StubACP(
        stream_events=[],
        prompt_result={"content": "ok", "finish_reason": "stop", "tool_calls": [], "usage": {}},
    )
    svc = ShimService(acp)
    await svc.complete([{"role": "user", "content": "hi"}], model="claude-sonnet-4.6")
    assert acp.last_model == "claude-sonnet-4.6"


@pytest.mark.asyncio
async def test_stream_tokens_forwards_model_to_new_session():
    """stream_tokens() passes the requested model down to ACPClient.new_session."""
    acp = StubACP([
        {"type": "text", "content": "hi"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    await collect_stream(
        svc.stream_tokens([{"role": "user", "content": "hi"}], model="claude-opus-4.8")
    )
    assert acp.last_model == "claude-opus-4.8"


@pytest.mark.asyncio
async def test_available_models_proxies_to_acp_client():
    """available_models() returns the ACP client's cached catalogue."""
    acp = StubACP([])
    acp.available_models = [{"id": "claude-sonnet-4.6", "name": "claude-sonnet-4.6", "description": ""}]
    svc = ShimService(acp)
    models = svc.available_models()
    assert [m["id"] for m in models] == ["claude-sonnet-4.6"]
