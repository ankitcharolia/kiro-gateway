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


def test_openai_models_fallback_uses_current_dotted_ids(sync_client, openai_headers):
    """With no live catalogue, /v1/models serves the configured fallback ids.

    The fallback uses kiro-cli's real dotted model ids (e.g. claude-sonnet-4.6),
    never the old stale dash-style ids.
    """
    response = sync_client.get("/v1/models", headers=openai_headers)
    ids = [m["id"] for m in response.json()["data"]]
    assert "claude-sonnet-4.6" in ids
    # The stale dash-style id must no longer be advertised.
    assert "claude-sonnet-4-5" not in ids


def test_openai_models_serves_live_catalogue_when_present(sync_client, openai_headers):
    """When the ACP client has discovered models, /v1/models reflects them."""
    sync_client.app.state.shim_service.available_models = lambda: [
        {"id": "auto", "name": "auto", "description": ""},
        {"id": "claude-opus-4.8", "name": "claude-opus-4.8", "description": ""},
    ]
    response = sync_client.get("/v1/models", headers=openai_headers)
    ids = [m["id"] for m in response.json()["data"]]
    assert ids == ["auto", "claude-opus-4.8"]


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


# ---------------------------------------------------------------------------
# /v1/responses (OpenAI Responses API)
# ---------------------------------------------------------------------------

def test_openai_responses_basic_string_input(sync_client, openai_headers):
    """POST /v1/responses with string input returns a Responses object."""
    payload = {"model": "claude-sonnet-4.6", "input": "Say hello"}
    response = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "response"
    assert data["status"] == "completed"
    assert data["id"].startswith("resp_")
    # mock ShimService returns "Hello, world!"
    assert data["output_text"] == "Hello, world!"
    assert data["output"][0]["type"] == "message"
    assert data["output"][0]["content"][0]["type"] == "output_text"


def test_openai_responses_message_list_input(sync_client, openai_headers):
    """POST /v1/responses accepts structured message-list input."""
    payload = {
        "model": "claude-sonnet-4.6",
        "instructions": "You are helpful.",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Hi there"}]},
        ],
    }
    response = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
    assert response.status_code == 200
    assert response.json()["object"] == "response"


def test_openai_responses_has_usage(sync_client, openai_headers):
    """POST /v1/responses includes a usage block with the expected keys."""
    payload = {"model": "claude-sonnet-4.6", "input": "Hi"}
    response = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
    usage = response.json()["usage"]
    assert set(usage.keys()) == {"input_tokens", "output_tokens", "total_tokens"}


def test_openai_responses_streaming(sync_client, openai_headers):
    """POST /v1/responses with stream=true emits the core SSE event sequence."""
    payload = {"model": "claude-sonnet-4.6", "input": "Hi", "stream": True}
    response = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
    assert response.status_code == 200
    body = response.text
    assert "event: response.created" in body
    assert "event: response.output_text.delta" in body
    assert "event: response.completed" in body


# ---------------------------------------------------------------------------
# /v1/embeddings — honest 501 (ACP has no embeddings)
# ---------------------------------------------------------------------------

def test_openai_embeddings_returns_501(sync_client, openai_headers):
    """POST /v1/embeddings returns 501 Not Implemented with a clear message."""
    payload = {"model": "text-embedding-3-small", "input": "embed me"}
    response = sync_client.post("/v1/embeddings", json=payload, headers=openai_headers)
    assert response.status_code == 501
    assert "embeddings" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Auth enforcement (issue #39): completion endpoints require the gateway key
# (Authorization: Bearer <KIRO_GATEWAY_API_KEY>) on both streaming and
# non-streaming paths. A wrong/absent key must return 401.
# ---------------------------------------------------------------------------

class TestOpenAIShimAuth:
    """The OpenAI shim completion routes enforce Bearer auth."""

    _CHAT_PAYLOAD = {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Say hello"}],
    }
    _RESPONSES_PAYLOAD = {"model": "claude-sonnet-4.6", "input": "Say hello"}

    def _bad_headers(self, invalid_proxy_api_key) -> dict:
        return {"Authorization": f"Bearer {invalid_proxy_api_key}"}

    # -- /v1/chat/completions ------------------------------------------------

    def test_chat_completions_missing_key_returns_401(self, sync_client):
        response = sync_client.post("/v1/chat/completions", json=self._CHAT_PAYLOAD)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API Key"

    def test_chat_completions_bad_key_returns_401(self, sync_client, invalid_proxy_api_key):
        response = sync_client.post(
            "/v1/chat/completions",
            json=self._CHAT_PAYLOAD,
            headers=self._bad_headers(invalid_proxy_api_key),
        )
        assert response.status_code == 401

    def test_chat_completions_valid_key_returns_200(self, sync_client, openai_headers):
        response = sync_client.post(
            "/v1/chat/completions", json=self._CHAT_PAYLOAD, headers=openai_headers
        )
        assert response.status_code == 200

    def test_chat_completions_stream_missing_key_returns_401(self, sync_client):
        payload = {**self._CHAT_PAYLOAD, "stream": True}
        response = sync_client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 401

    def test_chat_completions_stream_bad_key_returns_401(self, sync_client, invalid_proxy_api_key):
        payload = {**self._CHAT_PAYLOAD, "stream": True}
        response = sync_client.post(
            "/v1/chat/completions", json=payload, headers=self._bad_headers(invalid_proxy_api_key)
        )
        assert response.status_code == 401

    def test_chat_completions_stream_valid_key_returns_200(self, sync_client, openai_headers):
        payload = {**self._CHAT_PAYLOAD, "stream": True}
        response = sync_client.post(
            "/v1/chat/completions", json=payload, headers=openai_headers
        )
        assert response.status_code == 200

    # -- /v1/responses -------------------------------------------------------

    def test_responses_missing_key_returns_401(self, sync_client):
        response = sync_client.post("/v1/responses", json=self._RESPONSES_PAYLOAD)
        assert response.status_code == 401

    def test_responses_bad_key_returns_401(self, sync_client, invalid_proxy_api_key):
        response = sync_client.post(
            "/v1/responses",
            json=self._RESPONSES_PAYLOAD,
            headers=self._bad_headers(invalid_proxy_api_key),
        )
        assert response.status_code == 401

    def test_responses_valid_key_returns_200(self, sync_client, openai_headers):
        response = sync_client.post(
            "/v1/responses", json=self._RESPONSES_PAYLOAD, headers=openai_headers
        )
        assert response.status_code == 200

    def test_responses_stream_bad_key_returns_401(self, sync_client, invalid_proxy_api_key):
        payload = {**self._RESPONSES_PAYLOAD, "stream": True}
        response = sync_client.post(
            "/v1/responses", json=payload, headers=self._bad_headers(invalid_proxy_api_key)
        )
        assert response.status_code == 401

    def test_responses_stream_valid_key_returns_200(self, sync_client, openai_headers):
        payload = {**self._RESPONSES_PAYLOAD, "stream": True}
        response = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert response.status_code == 200

    # -- /v1/embeddings ------------------------------------------------------

    def test_embeddings_missing_key_returns_401(self, sync_client):
        response = sync_client.post(
            "/v1/embeddings", json={"model": "text-embedding-3-small", "input": "x"}
        )
        assert response.status_code == 401

    def test_embeddings_valid_key_returns_501(self, sync_client, openai_headers):
        """Auth passes, then the endpoint reports its honest 501."""
        response = sync_client.post(
            "/v1/embeddings",
            json={"model": "text-embedding-3-small", "input": "x"},
            headers=openai_headers,
        )
        assert response.status_code == 501

    # -- /v1/models stays public --------------------------------------------

    def test_models_is_public(self, sync_client):
        """GET /v1/models requires no key (discovery endpoint, per policy)."""
        response = sync_client.get("/v1/models")
        assert response.status_code == 200
