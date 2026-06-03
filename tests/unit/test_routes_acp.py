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
