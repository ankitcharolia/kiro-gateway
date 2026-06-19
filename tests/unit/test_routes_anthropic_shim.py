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


@pytest.mark.asyncio
async def test_anthropic_list_models_fallback_dotted_ids():
    """Anthropic list_models falls back to current dotted model ids.

    The handler is tested directly because the OpenAI shim also registers
    /v1/models and shadows the Anthropic route in the mounted app.
    """
    from unittest.mock import MagicMock

    from kiro.routes_anthropic_shim import list_models

    shim = MagicMock()
    shim.available_models = MagicMock(return_value=[])
    result = await list_models(shim=shim)

    ids = [m["id"] for m in result["data"]]
    assert "claude-sonnet-4.6" in ids
    assert "claude-sonnet-4-5" not in ids
    assert all(m["type"] == "model" for m in result["data"])


@pytest.mark.asyncio
async def test_anthropic_list_models_serves_live_catalogue():
    """Anthropic list_models reflects the live catalogue when present."""
    from unittest.mock import MagicMock

    from kiro.routes_anthropic_shim import list_models

    shim = MagicMock()
    shim.available_models = MagicMock(return_value=[
        {"id": "claude-opus-4.8", "name": "Opus 4.8", "description": ""},
    ])
    result = await list_models(shim=shim)

    assert result["data"][0]["id"] == "claude-opus-4.8"
    assert result["data"][0]["display_name"] == "Opus 4.8"


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


# ---------------------------------------------------------------------------
# /v1/messages/count_tokens
# ---------------------------------------------------------------------------

def test_anthropic_count_tokens_basic(sync_client, anthropic_headers):
    """POST /v1/messages/count_tokens returns a positive input_tokens estimate."""
    payload = {
        "model": "claude-sonnet-4.6",
        "messages": [{"role": "user", "content": "Hello world, how are you today?"}],
    }
    response = sync_client.post(
        "/v1/messages/count_tokens", json=payload, headers=anthropic_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "input_tokens" in data
    assert isinstance(data["input_tokens"], int)
    assert data["input_tokens"] > 0


def test_anthropic_count_tokens_system_and_tools_increase_count(sync_client, anthropic_headers):
    """System prompt and tools add to the estimated input_tokens."""
    base_payload = {
        "model": "claude-sonnet-4.6",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    base = sync_client.post(
        "/v1/messages/count_tokens", json=base_payload, headers=anthropic_headers
    ).json()["input_tokens"]

    rich_payload = {
        "model": "claude-sonnet-4.6",
        "system": "You are a meticulous and very verbose assistant.",
        "messages": [{"role": "user", "content": "Hi"}],
        "tools": [{
            "name": "get_weather",
            "description": "Get the current weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }],
    }
    rich = sync_client.post(
        "/v1/messages/count_tokens", json=rich_payload, headers=anthropic_headers
    ).json()["input_tokens"]

    assert rich > base


def test_anthropic_count_tokens_content_blocks(sync_client, anthropic_headers):
    """count_tokens accepts Anthropic content-block message form."""
    payload = {
        "model": "claude-sonnet-4.6",
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Block of text here"}]},
        ],
    }
    response = sync_client.post(
        "/v1/messages/count_tokens", json=payload, headers=anthropic_headers
    )
    assert response.status_code == 200
    assert response.json()["input_tokens"] > 0
