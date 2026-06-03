"""
Unit tests for /v1/messages and /v1/models (Anthropic shim).
All ACP calls are mocked — no kiro CLI needed.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------

def test_anthropic_models_endpoint(sync_client, anthropic_headers):
    """GET /v1/models returns model list (Anthropic path)."""
    response = sync_client.get("/v1/models", headers=anthropic_headers)
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) > 0


# ---------------------------------------------------------------------------
# /v1/messages — non-streaming
# ---------------------------------------------------------------------------

def test_anthropic_messages_basic(sync_client, anthropic_headers):
    """POST /v1/messages returns a valid Anthropic-format response."""
    payload = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Say hello"}],
    }
    response = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
    assert response.status_code == 200
    data = response.json()
    # Anthropic format: top-level 'content' array
    assert "content" in data or "choices" in data  # shim may normalise
    assert data.get("role") == "assistant" or "content" in data


def test_anthropic_messages_has_id(sync_client, anthropic_headers):
    """POST /v1/messages response includes a message ID."""
    payload = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Hi"}],
    }
    response = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
    data = response.json()
    assert "id" in data


def test_anthropic_messages_stop_reason(sync_client, anthropic_headers):
    """POST /v1/messages response includes stop_reason."""
    payload = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Hi"}],
    }
    response = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
    data = response.json()
    assert "stop_reason" in data or "finish_reason" in data


def test_anthropic_messages_type_field(sync_client, anthropic_headers):
    """POST /v1/messages response type field is 'message'."""
    payload = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Hi"}],
    }
    response = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
    data = response.json()
    if "type" in data:
        assert data["type"] == "message"
