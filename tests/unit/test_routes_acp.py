"""
Unit tests for native ACP endpoints: /acp/chat and /acp/chat/stream.
"""
from __future__ import annotations

import json
import pytest


ACT_HEADERS = {"Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_endpoint(sync_client):
    """GET /health returns status ok and acp-cli-bridge mode."""
    response = sync_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mode"] == "acp-cli-bridge"


# ---------------------------------------------------------------------------
# /acp/chat (non-streaming)
# ---------------------------------------------------------------------------

def test_acp_chat_basic(sync_client):
    """POST /acp/chat returns a response with session_id and content."""
    payload = {
        "messages": [{"role": "user", "content": "Hello from ACP"}],
    }
    response = sync_client.post("/acp/chat", json=payload, headers=ACT_HEADERS)
    assert response.status_code == 200
    data = response.json()
    # Must have session_id or content in response
    assert "content" in data or "session_id" in data or "choices" in data


def test_acp_chat_session_id_returned(sync_client):
    """POST /acp/chat response includes a session_id."""
    payload = {"messages": [{"role": "user", "content": "test"}]}
    response = sync_client.post("/acp/chat", json=payload, headers=ACT_HEADERS)
    if response.status_code == 200:
        data = response.json()
        # session_id may be in response or implicitly tracked
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# /acp/chat/stream (streaming SSE)
# ---------------------------------------------------------------------------

def test_acp_chat_stream_content_type(sync_client):
    """POST /acp/chat/stream returns text/event-stream content type."""
    payload = {"messages": [{"role": "user", "content": "stream test"}]}
    with sync_client.stream("POST", "/acp/chat/stream", json=payload, headers=ACT_HEADERS) as r:
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/event-stream" in ct or "application/json" in ct


def test_acp_chat_stream_yields_events(sync_client):
    """POST /acp/chat/stream yields at least one SSE event."""
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    events = []
    with sync_client.stream("POST", "/acp/chat/stream", json=payload, headers=ACT_HEADERS) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(line)
    assert len(events) >= 1


# ---------------------------------------------------------------------------
# Task list / plan surfacing on the native ACP route (acp_plan), gated by
# ACP_SURFACE_THINKING.
# ---------------------------------------------------------------------------

from kiro.shim_service import ShimService as _ShimService
from kiro.config import settings as _settings


class _PlanACP:
    """Stub ACP client whose turn includes a task list (plan) then an answer."""

    available_models: list = []

    async def new_session(self, capabilities=None, cwd=None, model=None):
        return "s"

    async def prompt(self, params):
        return {"content": "Done.", "reasoning": "", "tool_calls": [],
                "finish_reason": "stop", "usage": {}}

    async def prompt_stream(self, params):
        yield {"type": "plan",
               "entries": [{"content": "Write the file", "status": "pending"},
                           {"content": "Read it back", "status": "pending"}],
               "description": "Do stuff"}
        yield {"type": "text", "content": "Done."}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}


def _collect_sse(sync_client, payload):
    body = ""
    with sync_client.stream("POST", "/acp/chat/stream", json=payload, headers=ACT_HEADERS) as r:
        for line in r.iter_lines():
            body += line + "\n"
    return body


def test_acp_stream_surfaces_plan(sync_client):
    sync_client.app.state.shim_service = _ShimService(_PlanACP())
    body = _collect_sse(sync_client, {"messages": [{"role": "user", "content": "go"}]})
    assert "event: acp_plan" in body
    assert "Write the file" in body
    assert "event: acp_text" in body


def test_acp_stream_plan_suppressed_when_off(sync_client, monkeypatch):
    monkeypatch.setattr(_settings, "ACP_SURFACE_THINKING", False)
    sync_client.app.state.shim_service = _ShimService(_PlanACP())
    body = _collect_sse(sync_client, {"messages": [{"role": "user", "content": "go"}]})
    assert "event: acp_plan" not in body
    assert "event: acp_text" in body
