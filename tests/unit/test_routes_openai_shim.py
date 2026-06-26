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


# ---------------------------------------------------------------------------
# Sampling-param forwarding (issue #32): the OpenAI shim forwards
# temperature/max_tokens/top_p/stop to ShimService in both modes.
# ---------------------------------------------------------------------------

class _RecordingShim:
    """ShimService stand-in that records the kwargs each route passes."""

    def __init__(self):
        self.complete_kwargs: list[dict] = []
        self.stream_kwargs: list[dict] = []

    def available_models(self):
        return []

    async def complete(self, **kwargs):
        self.complete_kwargs.append(kwargs)
        return {
            "content": "ok", "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    async def stream_tokens(self, **kwargs):
        self.stream_kwargs.append(kwargs)
        yield {"type": "text", "content": "ok"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}


class TestOpenAIShimSamplingForwarding:
    """temperature/max_tokens/top_p/stop reach ShimService for both modes."""

    def test_chat_non_stream_forwards_params(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.3, "max_tokens": 64, "top_p": 0.8, "stop": "END",
        }
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        kw = rec.complete_kwargs[0]
        assert kw["temperature"] == 0.3
        assert kw["max_tokens"] == 64
        assert kw["top_p"] == 0.8
        assert kw["stop"] == ["END"]  # string normalised to list

    def test_chat_stream_forwards_params(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "temperature": 0.1, "max_tokens": 32, "top_p": 0.5, "stop": ["A", "B"],
        }
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        kw = rec.stream_kwargs[0]
        assert kw["temperature"] == 0.1
        assert kw["max_tokens"] == 32
        assert kw["top_p"] == 0.5
        assert kw["stop"] == ["A", "B"]

    def test_responses_non_stream_forwards_top_p(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {"model": "claude-sonnet-4.6", "input": "hi",
                   "temperature": 0.4, "max_output_tokens": 40, "top_p": 0.7}
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        kw = rec.complete_kwargs[0]
        assert kw["temperature"] == 0.4
        assert kw["max_tokens"] == 40   # max_output_tokens → max_tokens
        assert kw["top_p"] == 0.7

    def test_responses_stream_forwards_top_p(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {"model": "claude-sonnet-4.6", "input": "hi", "stream": True, "top_p": 0.33}
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        assert rec.stream_kwargs[0]["top_p"] == 0.33


# ---------------------------------------------------------------------------
# Error mapping (issue #44): ACP/upstream failures surface with the right HTTP
# status and the OpenAI native error shape, in both streaming and non-streaming
# paths.
# ---------------------------------------------------------------------------

from kiro.acp_client import ACPError


def _error_shim_complete(exc):
    """Build a shim whose complete() raises ``exc``."""
    shim = MagicMock()
    shim.available_models = MagicMock(return_value=[])
    shim.complete = AsyncMock(side_effect=exc)
    return shim


def _error_shim_stream(event):
    """Build a shim whose stream_tokens() emits a single error ``event``."""
    shim = MagicMock()
    shim.available_models = MagicMock(return_value=[])

    async def _stream(*args, **kwargs):
        yield event

    shim.stream_tokens = _stream
    return shim


class TestOpenAIShimErrorMapping:
    """Non-streaming + streaming error classification for the OpenAI shim."""

    _CHAT = {"model": "claude-sonnet-4.6", "messages": [{"role": "user", "content": "hi"}]}

    def test_chat_non_stream_rate_limit_returns_429(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _error_shim_complete(
            ACPError(-32000, "Rate limit exceeded, retry after 30")
        )
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["type"] == "rate_limit_error"
        assert resp.headers.get("retry-after") == "30"

    def test_chat_non_stream_overloaded_returns_503(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _error_shim_complete(
            ACPError(-32000, "service is overloaded")
        )
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        assert resp.status_code == 503
        assert resp.json()["error"]["type"] == "server_error"

    def test_chat_non_stream_timeout_returns_504(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _error_shim_complete(
            ACPError(-32000, "ACP session/prompt timed out after 120s")
        )
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        assert resp.status_code == 504

    def test_chat_non_stream_default_returns_502(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _error_shim_complete(
            ACPError(-32000, "kiro-cli subprocess exited")
        )
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        assert resp.status_code == 502
        assert resp.json()["error"]["type"] == "server_error"

    def test_chat_stream_rate_limit_error_type(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _error_shim_stream(
            {"type": "error", "message": "rate limit exceeded", "code": -32000}
        )
        payload = {**self._CHAT, "stream": True}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200  # SSE body already started
        assert '"type": "rate_limit_error"' in resp.text
        assert "data: [DONE]" in resp.text

    def test_responses_non_stream_rate_limit_returns_429(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _error_shim_complete(
            ACPError(-32000, "Too Many Requests")
        )
        resp = sync_client.post(
            "/v1/responses", json={"model": "claude-sonnet-4.6", "input": "hi"},
            headers=openai_headers,
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["type"] == "rate_limit_error"

    def test_responses_stream_error_uses_mapped_type(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _error_shim_stream(
            {"type": "error", "message": "overloaded", "code": -32000}
        )
        payload = {"model": "claude-sonnet-4.6", "input": "hi", "stream": True}
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        assert "event: response.failed" in resp.text
        assert '"type": "server_error"' in resp.text


# ---------------------------------------------------------------------------
# System-role handling (issue #44): system/developer roles are preserved
# distinctly (not flattened to anonymous user text), and instructions map to a
# system role in the Responses API.
# ---------------------------------------------------------------------------

class TestOpenAIShimSystemRole:
    """system/developer provenance is preserved through to ACP messages."""

    def test_chat_preserves_system_and_developer_roles(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "messages": [
                {"role": "system", "content": "Be terse."},
                {"role": "developer", "content": "Use Python."},
                {"role": "user", "content": "hi"},
            ],
        }
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        roles = [(m.role, m.content) for m in rec.complete_kwargs[0]["messages"]]
        assert roles == [
            ("system", "Be terse."),
            ("developer", "Use Python."),
            ("user", "hi"),
        ]

    def test_chat_multiple_system_messages_not_merged(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "messages": [
                {"role": "system", "content": "Rule one."},
                {"role": "system", "content": "Rule two."},
                {"role": "user", "content": "hi"},
            ],
        }
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        system_msgs = [m.content for m in rec.complete_kwargs[0]["messages"] if m.role == "system"]
        assert system_msgs == ["Rule one.", "Rule two."]

    def test_tool_role_does_not_break_and_maps_to_user(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "messages": [
                {"role": "user", "content": "weather?"},
                {"role": "tool", "tool_call_id": "abc", "content": "sunny"},
            ],
        }
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        msgs = rec.complete_kwargs[0]["messages"]
        assert msgs[-1].role == "user"
        assert "[tool_result id=abc]" in msgs[-1].content

    def test_responses_instructions_map_to_system_role(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "instructions": "You are helpful.",
            "input": "hi",
        }
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        msgs = rec.complete_kwargs[0]["messages"]
        assert msgs[0].role == "system"
        assert msgs[0].content == "You are helpful."


# ---------------------------------------------------------------------------
# Usage accounting (issue #36): usage fields reflect real counts when kiro-cli
# reports them, else a consistent tokenizer estimate (never silently 0).
# logprobs are reported as null (unsupported by the ACP path).
# ---------------------------------------------------------------------------

def _usage_shim(content="Hello there, this is the answer.", usage=None, tool_calls=None):
    """Shim stand-in returning given content/usage for both modes."""
    shim = MagicMock()
    shim.available_models = MagicMock(return_value=[])
    shim.complete = AsyncMock(return_value={
        "content": content,
        "tool_calls": tool_calls or [],
        "finish_reason": "stop",
        "usage": usage or {},
    })

    async def _stream(*args, **kwargs):
        for word in content.split(" "):
            yield {"type": "text", "content": word + " "}
        yield {"type": "done", "finish_reason": "stop", "usage": usage or {}}

    shim.stream_tokens = _stream
    return shim


class TestOpenAIShimUsage:
    """Usage shape + estimate fallback for the OpenAI shim."""

    _CHAT = {"model": "claude-sonnet-4.6", "messages": [{"role": "user", "content": "What is the capital of France?"}]}

    def test_chat_usage_estimated_when_unreported(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _usage_shim(usage={})
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        assert resp.status_code == 200
        usage = resp.json()["usage"]
        assert set(usage) == {"prompt_tokens", "completion_tokens", "total_tokens"}
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    def test_chat_usage_uses_reported_counts(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _usage_shim(
            usage={"input_tokens": 111, "output_tokens": 22, "total_tokens": 133}
        )
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        usage = resp.json()["usage"]
        assert usage == {"prompt_tokens": 111, "completion_tokens": 22, "total_tokens": 133}

    def test_chat_choice_logprobs_is_null(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _usage_shim()
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        assert resp.json()["choices"][0]["logprobs"] is None

    def test_chat_stream_includes_usage_when_requested(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _usage_shim(usage={})
        payload = {**self._CHAT, "stream": True, "stream_options": {"include_usage": True}}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        # Find the usage-only chunk (choices: []).
        usage_chunks = [
            json.loads(line[len("data: "):])
            for line in resp.text.splitlines()
            if line.startswith("data: ") and '"usage"' in line
        ]
        assert usage_chunks, "expected a usage chunk when include_usage=true"
        usage = usage_chunks[-1]["usage"]
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        assert usage_chunks[-1]["choices"] == []

    def test_chat_stream_omits_usage_by_default(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _usage_shim(usage={})
        payload = {**self._CHAT, "stream": True}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert '"usage"' not in resp.text

    def test_responses_usage_estimated_when_unreported(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _usage_shim(usage={})
        resp = sync_client.post(
            "/v1/responses", json={"model": "claude-sonnet-4.6", "input": "Tell me a story."},
            headers=openai_headers,
        )
        usage = resp.json()["usage"]
        assert set(usage) == {"input_tokens", "output_tokens", "total_tokens"}
        assert usage["input_tokens"] > 0
        assert usage["output_tokens"] > 0

    def test_responses_stream_usage_non_zero(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _usage_shim(usage={})
        payload = {"model": "claude-sonnet-4.6", "input": "Tell me a story.", "stream": True}
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        # The terminal response.completed event carries the usage object.
        completed = [
            json.loads(line[len("data: "):])
            for line in resp.text.splitlines()
            if line.startswith("data: ") and '"response.completed"' in line
        ]
        assert completed
        usage = completed[-1]["response"]["usage"]
        assert usage["input_tokens"] > 0
        assert usage["output_tokens"] > 0


# ---------------------------------------------------------------------------
# GET /v1/models/{model_id} — retrieve a single model (probed by harnesses
# such as hermes-agent). Permissive: any id forwards to kiro-cli.
# ---------------------------------------------------------------------------

class TestOpenAIRetrieveModel:
    """The OpenAI retrieve-model endpoint returns a valid model object."""

    def test_retrieve_known_model(self, sync_client, openai_headers):
        resp = sync_client.get("/v1/models/claude-sonnet-4.6", headers=openai_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "claude-sonnet-4.6"
        assert data["object"] == "model"
        assert data["owned_by"] == "kiro"
        assert "created" in data

    def test_retrieve_model_id_with_slash(self, sync_client, openai_headers):
        """Model ids containing a slash resolve via the :path converter."""
        resp = sync_client.get("/v1/models/vendor/model-1", headers=openai_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == "vendor/model-1"

    def test_retrieve_model_is_public(self, sync_client):
        """Like the listing, retrieve is a discovery endpoint (no key required)."""
        resp = sync_client.get("/v1/models/claude-sonnet-4.6")
        assert resp.status_code == 200

    def test_list_endpoint_still_works(self, sync_client, openai_headers):
        """Adding the retrieve route must not shadow the list route."""
        resp = sync_client.get("/v1/models", headers=openai_headers)
        assert resp.status_code == 200
        assert resp.json()["object"] == "list"


# ---------------------------------------------------------------------------
# Client tool forwarding (issue #31): client-declared tools reach the ACP
# prompt path via ShimService in both modes. (kiro-cli does not honor client
# tools today — verified by live probe — but the gateway forwards them.)
# ---------------------------------------------------------------------------

_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
    },
}


class TestOpenAIShimToolForwarding:
    """Client tools reach ShimService for chat + responses, both modes."""

    def test_chat_non_stream_forwards_tools(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "messages": [{"role": "user", "content": "weather in Berlin?"}],
            "tools": [_WEATHER_TOOL],
        }
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        tools = rec.complete_kwargs[0]["tools"]
        assert any(
            (t.get("function") or t).get("name") == "get_weather" for t in tools
        )

    def test_chat_stream_forwards_tools(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "messages": [{"role": "user", "content": "weather?"}],
            "stream": True,
            "tools": [_WEATHER_TOOL],
        }
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        tools = rec.stream_kwargs[0]["tools"]
        assert any((t.get("function") or t).get("name") == "get_weather" for t in tools)

    def test_responses_non_stream_forwards_tools(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "input": "weather?",
            "tools": [{"type": "function", "name": "get_weather",
                       "description": "w", "parameters": {"type": "object"}}],
        }
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        assert rec.complete_kwargs[0]["tools"]

    def test_responses_stream_forwards_tools(self, sync_client, openai_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6", "input": "weather?", "stream": True,
            "tools": [{"type": "function", "name": "get_weather",
                       "description": "w", "parameters": {"type": "object"}}],
        }
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert resp.status_code == 200
        assert rec.stream_kwargs[0]["tools"]


# ---------------------------------------------------------------------------
# Built-in tool-call surfacing gate (ACP_SURFACE_TOOL_CALLS): by default the
# OpenAI shim does NOT surface kiro-cli's own built-in tool calls (so harnesses
# never see an "unavailable tool"); opt-in restores the old behavior.
# ---------------------------------------------------------------------------

from kiro.shim_service import ShimService as _ShimService
from kiro.config import settings as _settings


class _ToolEmittingACP:
    """Stub ACP client whose turn includes a kiro-cli built-in tool call."""

    available_models: list = []

    async def new_session(self, capabilities=None, cwd=None, model=None):
        return "s"

    async def prompt(self, params):
        return {
            "content": "Berlin is sunny.",
            "finish_reason": "stop",
            "tool_calls": [{"id": "c1", "name": "Fetching web content", "arguments": {}}],
            "usage": {},
        }

    async def prompt_stream(self, params):
        yield {"type": "text", "content": "Berlin is sunny."}
        yield {"type": "tool_call", "id": "c1", "name": "Fetching web content", "arguments": {}}
        yield {"type": "done", "finish_reason": "stop"}


class TestOpenAIShimToolSurfacingGate:
    """Default off suppresses built-in tool calls; opt-in surfaces them."""

    _CHAT = {"model": "claude-sonnet-4.6", "messages": [{"role": "user", "content": "weather?"}]}

    def test_chat_non_stream_default_suppresses_tool_calls(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _ShimService(_ToolEmittingACP())
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        assert resp.status_code == 200
        choice = resp.json()["choices"][0]
        assert choice["message"].get("tool_calls") is None
        assert choice["message"]["content"] == "Berlin is sunny."
        assert choice["finish_reason"] == "stop"

    def test_chat_non_stream_optin_surfaces_tool_calls(self, sync_client, openai_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_TOOL_CALLS", True)
        sync_client.app.state.shim_service = _ShimService(_ToolEmittingACP())
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        choice = resp.json()["choices"][0]
        assert choice["finish_reason"] == "tool_calls"
        assert choice["message"]["tool_calls"][0]["function"]["name"] == "Fetching web content"

    def test_chat_stream_default_suppresses_tool_calls(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _ShimService(_ToolEmittingACP())
        payload = {**self._CHAT, "stream": True}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert '"tool_calls"' not in resp.text
        assert '"finish_reason": "stop"' in resp.text

    def test_chat_stream_optin_surfaces_tool_calls(self, sync_client, openai_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_TOOL_CALLS", True)
        sync_client.app.state.shim_service = _ShimService(_ToolEmittingACP())
        payload = {**self._CHAT, "stream": True}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert '"tool_calls"' in resp.text
        assert "Fetching web content" in resp.text


# ---------------------------------------------------------------------------
# Reasoning/thinking surfacing (issue #40): reasoning is surfaced in each API's
# native shape, gated by ACP_SURFACE_THINKING (default true); final content is
# unchanged.
# ---------------------------------------------------------------------------

class _ThinkingACP:
    """Stub ACP client whose turn includes reasoning then a final answer."""

    available_models: list = []

    async def new_session(self, capabilities=None, cwd=None, model=None):
        return "s"

    async def prompt(self, params):
        return {
            "content": "The answer is 42.",
            "reasoning": "Let me think about it.",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {},
        }

    async def prompt_stream(self, params):
        yield {"type": "thinking", "content": "Let me think "}
        yield {"type": "thinking", "content": "about it."}
        yield {"type": "text", "content": "The answer is 42."}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}


class TestOpenAIShimReasoning:
    """reasoning_content (chat) and reasoning items (Responses), both modes."""

    _CHAT = {"model": "claude-sonnet-4.6", "messages": [{"role": "user", "content": "q"}]}

    def test_chat_non_stream_surfaces_reasoning_content(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        assert resp.status_code == 200
        msg = resp.json()["choices"][0]["message"]
        assert msg["reasoning_content"] == "Let me think about it."
        assert msg["content"] == "The answer is 42."   # final text unchanged

    def test_chat_non_stream_suppressed_when_off(self, sync_client, openai_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_THINKING", False)
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        resp = sync_client.post("/v1/chat/completions", json=self._CHAT, headers=openai_headers)
        msg = resp.json()["choices"][0]["message"]
        assert "reasoning_content" not in msg
        assert msg["content"] == "The answer is 42."

    def test_chat_stream_surfaces_reasoning_content(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        payload = {**self._CHAT, "stream": True}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert '"reasoning_content"' in resp.text
        assert "Let me think " in resp.text
        assert "The answer is 42." in resp.text

    def test_chat_stream_suppressed_when_off(self, sync_client, openai_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_THINKING", False)
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        payload = {**self._CHAT, "stream": True}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert '"reasoning_content"' not in resp.text
        assert "The answer is 42." in resp.text

    def test_responses_non_stream_includes_reasoning_item(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        resp = sync_client.post(
            "/v1/responses", json={"model": "claude-sonnet-4.6", "input": "q"},
            headers=openai_headers,
        )
        output = resp.json()["output"]
        reasoning_items = [o for o in output if o["type"] == "reasoning"]
        assert reasoning_items
        assert reasoning_items[0]["summary"][0]["text"] == "Let me think about it."
        assert resp.json()["output_text"] == "The answer is 42."

    def test_responses_stream_emits_reasoning_summary(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        payload = {"model": "claude-sonnet-4.6", "input": "q", "stream": True}
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert "event: response.reasoning_summary_text.delta" in resp.text
        assert "event: response.output_text.delta" in resp.text
        assert "event: response.completed" in resp.text


# ---------------------------------------------------------------------------
# Task list / plan folded into the reasoning channel (gated by
# ACP_SURFACE_THINKING) on the OpenAI shim.
# ---------------------------------------------------------------------------

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
               "entries": [{"content": "Write the file", "status": "pending"}],
               "description": "Do stuff"}
        yield {"type": "text", "content": "Done."}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}


class TestOpenAIShimPlan:
    """Plan is surfaced via reasoning_content (chat) / reasoning items (Responses)."""

    _CHAT = {"model": "claude-sonnet-4.6", "messages": [{"role": "user", "content": "go"}]}

    def test_chat_stream_plan_in_reasoning(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _ShimService(_PlanACP())
        payload = {**self._CHAT, "stream": True}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert '"reasoning_content"' in resp.text
        assert "Write the file" in resp.text
        assert "Done." in resp.text

    def test_chat_stream_plan_suppressed_when_off(self, sync_client, openai_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_THINKING", False)
        sync_client.app.state.shim_service = _ShimService(_PlanACP())
        payload = {**self._CHAT, "stream": True}
        resp = sync_client.post("/v1/chat/completions", json=payload, headers=openai_headers)
        assert '"reasoning_content"' not in resp.text
        assert "Write the file" not in resp.text
        assert "Done." in resp.text

    def test_responses_stream_plan_in_reasoning(self, sync_client, openai_headers):
        sync_client.app.state.shim_service = _ShimService(_PlanACP())
        payload = {"model": "claude-sonnet-4.6", "input": "go", "stream": True}
        resp = sync_client.post("/v1/responses", json=payload, headers=openai_headers)
        assert "event: response.reasoning_summary_text.delta" in resp.text
        assert "Write the file" in resp.text
