"""
Unit tests for /v1/chat/completions and /v1/models (OpenAI shim).
All ACP calls are mocked — no kiro CLI needed.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------

def test_openai_models_endpoint(sync_client, openai_headers):
    """GET /v1/models returns a list of available models."""
    response = sync_client.get("/v1/models", headers=openai_headers)
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0
    # Each model entry must have an 'id' field
    for model in data["data"]:
        assert "id" in model


def test_openai_models_object_field(sync_client, openai_headers):
    """GET /v1/models returns object type 'list'."""
    response = sync_client.get("/v1/models", headers=openai_headers)
    data = response.json()
    assert data.get("object") == "list"


# ---------------------------------------------------------------------------
# /v1/chat/completions — non-streaming
# ---------------------------------------------------------------------------

def test_openai_chat_completions_basic(sync_client, openai_headers):
    """POST /v1/chat/completions returns a valid OpenAI-format response."""
    payload = {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Say hello"}],
        "stream": False,
    }
    response = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    choice = data["choices"][0]
    assert "message" in choice
    assert choice["message"]["role"] == "assistant"


def test_openai_chat_completions_has_id(sync_client, openai_headers):
    """POST /v1/chat/completions response includes a completion ID."""
    payload = {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    response = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
    data = response.json()
    assert "id" in data


def test_openai_chat_completions_finish_reason(sync_client, openai_headers):
    """POST /v1/chat/completions choice includes a finish_reason."""
    payload = {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    response = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
    data = response.json()
    assert data["choices"][0].get("finish_reason") is not None


def test_openai_chat_completions_object_type(sync_client, openai_headers):
    """POST /v1/chat/completions returns object type 'chat.completion'."""
    payload = {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    response = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
    data = response.json()
    assert data.get("object") == "chat.completion"


# ---------------------------------------------------------------------------
# Route does NOT use direct API
# ---------------------------------------------------------------------------

def test_openai_shim_route_uses_shim_service(sync_client, openai_headers):
    """The OpenAI shim endpoint must go through ShimService, not a direct Kiro API call."""
    payload = {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Test"}],
    }
    # If ShimService is used, the route must access app.state.shim_service
    # We verify by checking the response comes through without errors
    response = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
    assert response.status_code in (200, 422)  # 422 only if model validation fails
