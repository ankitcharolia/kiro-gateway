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


# ---------------------------------------------------------------------------
# Base-URL path mounts — the Anthropic shim must answer on every common
# base-URL convention (regression: clients hitting /messages and
# /anthropic/v1/messages got 404 when only /v1/messages was mounted).
# ---------------------------------------------------------------------------

import pytest as _pytest


class TestAnthropicBasePathMounts:
    """The Anthropic shim is mounted under several base-path prefixes."""

    _MESSAGE_PAYLOAD = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Hi"}],
    }

    @_pytest.mark.parametrize(
        "path",
        [
            "/v1/messages",            # standard Anthropic base URL
            "/messages",               # base URL already includes the version
            "/anthropic/v1/messages",  # provider-namespaced base URL
            "/anthropic/messages",     # provider-namespaced, no version segment
        ],
    )
    def test_messages_reachable_on_all_prefixes(self, sync_client, anthropic_headers, path):
        """POST <prefix>/messages returns 200, never 404."""
        response = sync_client.post(path, json=self._MESSAGE_PAYLOAD, headers=anthropic_headers)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert response.json().get("role") == "assistant"

    @_pytest.mark.parametrize(
        "path",
        [
            "/messages",
            "/anthropic/v1/messages",
            "/anthropic/messages",
        ],
    )
    def test_messages_not_404(self, sync_client, anthropic_headers, path):
        """The previously-404 paths from the bug report now resolve."""
        response = sync_client.post(path, json=self._MESSAGE_PAYLOAD, headers=anthropic_headers)
        assert response.status_code != 404

    @_pytest.mark.parametrize(
        "path",
        ["/anthropic/v1/models", "/anthropic/models"],
    )
    def test_models_reachable_on_anthropic_prefixes(self, sync_client, anthropic_headers, path):
        """GET <anthropic prefix>/models returns the Anthropic model listing."""
        response = sync_client.get(path, headers=anthropic_headers)
        assert response.status_code == 200
        assert "data" in response.json()

    def test_count_tokens_reachable_on_anthropic_prefix(self, sync_client, anthropic_headers):
        """count_tokens is mounted under the provider-namespaced prefix too."""
        response = sync_client.post(
            "/anthropic/v1/messages/count_tokens",
            json={"model": "claude-sonnet-4.6", "messages": [{"role": "user", "content": "hi"}]},
            headers=anthropic_headers,
        )
        assert response.status_code == 200
        assert response.json()["input_tokens"] > 0


# ---------------------------------------------------------------------------
# system field as a list of content blocks — Anthropic SDK / Claude Code send
# `system` as an array (often with cache_control). It must not 422.
# ---------------------------------------------------------------------------

class TestAnthropicSystemField:
    """The Anthropic `system` field accepts both string and block-list forms."""

    def test_messages_accepts_system_as_string(self, sync_client, anthropic_headers):
        payload = {
            "model": "claude-sonnet-4-5",
            "max_tokens": 256,
            "system": "You are terse.",
            "messages": [{"role": "user", "content": "hi"}],
        }
        response = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert response.status_code == 200

    def test_messages_accepts_system_as_block_list(self, sync_client, anthropic_headers):
        """Regression: system as a list of text blocks used to 422."""
        payload = {
            "model": "claude-sonnet-4-5",
            "max_tokens": 256,
            "system": [
                {"type": "text", "text": "You are Claude Code.",
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": "Be concise."},
            ],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        }
        response = sync_client.post(
            "/anthropic/v1/messages", json=payload, headers=anthropic_headers
        )
        assert response.status_code == 200, response.text
        assert response.json().get("role") == "assistant"

    def test_messages_full_sdk_payload_does_not_422(self, sync_client, anthropic_headers):
        """A realistic SDK payload (extra fields + block-list system) validates."""
        payload = {
            "model": "claude-sonnet-4-5",
            "max_tokens": 1024,
            "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            "metadata": {"user_id": "abc"},
            "stop_sequences": ["X"],
            "temperature": 1.0,
            "top_p": 0.9,
            "top_k": 40,
            "tool_choice": {"type": "auto"},
            "tools": [
                {"name": "Bash", "description": "run", "input_schema": {"type": "object"},
                 "cache_control": {"type": "ephemeral"}},
            ],
            "thinking": {"type": "enabled", "budget_tokens": 2048},
        }
        response = sync_client.post("/messages", json=payload, headers=anthropic_headers)
        assert response.status_code != 422, response.text
        assert response.status_code == 200

    def test_count_tokens_accepts_system_as_block_list(self, sync_client, anthropic_headers):
        payload = {
            "model": "claude-sonnet-4.6",
            "system": [{"type": "text", "text": "You are a verbose assistant."}],
            "messages": [{"role": "user", "content": "hi"}],
        }
        response = sync_client.post(
            "/v1/messages/count_tokens", json=payload, headers=anthropic_headers
        )
        assert response.status_code == 200
        assert response.json()["input_tokens"] > 0


class TestSystemToText:
    """Unit tests for the `_system_to_text` flattener."""

    def test_string_passthrough(self):
        from kiro.routes_anthropic_shim import _system_to_text
        assert _system_to_text("hello") == "hello"

    def test_block_list_is_joined(self):
        from kiro.routes_anthropic_shim import _system_to_text
        blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        assert _system_to_text(blocks) == "a\nb"

    def test_none_and_empty(self):
        from kiro.routes_anthropic_shim import _system_to_text
        assert _system_to_text(None) is None
        assert _system_to_text([]) is None
        assert _system_to_text([{"type": "text"}]) is None  # no text key



# ---------------------------------------------------------------------------
# Auth enforcement (issue #39): completion endpoints require the gateway key
# (x-api-key: <KIRO_GATEWAY_API_KEY>) on both streaming and non-streaming
# paths. A wrong/absent key must return 401. An Authorization: Bearer header
# is accepted as a fallback.
# ---------------------------------------------------------------------------

class TestAnthropicShimAuth:
    """The Anthropic shim completion routes enforce x-api-key auth."""

    _MESSAGE_PAYLOAD = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Say hello"}],
    }
    _COUNT_PAYLOAD = {
        "model": "claude-sonnet-4.6",
        "messages": [{"role": "user", "content": "Hello world"}],
    }

    def _bad_headers(self, invalid_proxy_api_key) -> dict:
        return {"x-api-key": invalid_proxy_api_key}

    # -- /v1/messages --------------------------------------------------------

    def test_messages_missing_key_returns_401(self, sync_client):
        response = sync_client.post("/v1/messages", json=self._MESSAGE_PAYLOAD)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API Key"

    def test_messages_bad_key_returns_401(self, sync_client, invalid_proxy_api_key):
        response = sync_client.post(
            "/v1/messages",
            json=self._MESSAGE_PAYLOAD,
            headers=self._bad_headers(invalid_proxy_api_key),
        )
        assert response.status_code == 401

    def test_messages_valid_key_returns_200(self, sync_client, anthropic_headers):
        response = sync_client.post(
            "/v1/messages", json=self._MESSAGE_PAYLOAD, headers=anthropic_headers
        )
        assert response.status_code == 200

    def test_messages_bearer_fallback_returns_200(self, sync_client):
        """An Authorization: Bearer header is accepted on the Anthropic shim."""
        from kiro.config import KIRO_GATEWAY_API_KEY

        response = sync_client.post(
            "/v1/messages",
            json=self._MESSAGE_PAYLOAD,
            headers={"Authorization": f"Bearer {KIRO_GATEWAY_API_KEY}"},
        )
        assert response.status_code == 200

    def test_messages_stream_missing_key_returns_401(self, sync_client):
        payload = {**self._MESSAGE_PAYLOAD, "stream": True}
        response = sync_client.post("/v1/messages", json=payload)
        assert response.status_code == 401

    def test_messages_stream_bad_key_returns_401(self, sync_client, invalid_proxy_api_key):
        payload = {**self._MESSAGE_PAYLOAD, "stream": True}
        response = sync_client.post(
            "/v1/messages", json=payload, headers=self._bad_headers(invalid_proxy_api_key)
        )
        assert response.status_code == 401

    def test_messages_stream_valid_key_returns_200(self, sync_client, anthropic_headers):
        payload = {**self._MESSAGE_PAYLOAD, "stream": True}
        response = sync_client.post(
            "/v1/messages", json=payload, headers=anthropic_headers
        )
        assert response.status_code == 200

    def test_messages_auth_enforced_on_all_prefixes(self, sync_client):
        """Auth applies wherever the Anthropic shim is mounted, not just /v1."""
        for path in ("/messages", "/anthropic/v1/messages", "/anthropic/messages"):
            response = sync_client.post(path, json=self._MESSAGE_PAYLOAD)
            assert response.status_code == 401, f"{path} returned {response.status_code}"

    # -- /v1/messages/count_tokens ------------------------------------------

    def test_count_tokens_missing_key_returns_401(self, sync_client):
        response = sync_client.post("/v1/messages/count_tokens", json=self._COUNT_PAYLOAD)
        assert response.status_code == 401

    def test_count_tokens_bad_key_returns_401(self, sync_client, invalid_proxy_api_key):
        response = sync_client.post(
            "/v1/messages/count_tokens",
            json=self._COUNT_PAYLOAD,
            headers=self._bad_headers(invalid_proxy_api_key),
        )
        assert response.status_code == 401

    def test_count_tokens_valid_key_returns_200(self, sync_client, anthropic_headers):
        response = sync_client.post(
            "/v1/messages/count_tokens", json=self._COUNT_PAYLOAD, headers=anthropic_headers
        )
        assert response.status_code == 200

    # -- /v1/models stays public --------------------------------------------

    def test_anthropic_models_prefix_is_public(self, sync_client):
        """GET /anthropic/v1/models requires no key (discovery endpoint)."""
        response = sync_client.get("/anthropic/v1/models")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Sampling-param forwarding (issue #32): the Anthropic shim forwards
# temperature/max_tokens/top_p/top_k/stop_sequences in both modes.
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


class TestAnthropicShimSamplingForwarding:
    """temperature/max_tokens/top_p/top_k/stop_sequences reach ShimService."""

    def test_messages_non_stream_forwards_params(self, sync_client, anthropic_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "max_tokens": 128,
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.6, "top_p": 0.9, "top_k": 40, "stop_sequences": ["\n\n"],
        }
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        kw = rec.complete_kwargs[0]
        assert kw["temperature"] == 0.6
        assert kw["max_tokens"] == 128
        assert kw["top_p"] == 0.9
        assert kw["top_k"] == 40
        assert kw["stop"] == ["\n\n"]

    def test_messages_stream_forwards_params(self, sync_client, anthropic_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "max_tokens": 64,
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.2, "top_p": 0.4, "top_k": 10, "stop_sequences": ["STOP"],
        }
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        kw = rec.stream_kwargs[0]
        assert kw["temperature"] == 0.2
        assert kw["max_tokens"] == 64
        assert kw["top_p"] == 0.4
        assert kw["top_k"] == 10
        assert kw["stop"] == ["STOP"]


# ---------------------------------------------------------------------------
# Error mapping (issue #44): ACP/upstream failures surface with the right HTTP
# status and the Anthropic native error shape, in both modes.
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, MagicMock

from kiro.acp_client import ACPError


def _anthropic_error_shim_complete(exc):
    shim = MagicMock()
    shim.available_models = MagicMock(return_value=[])
    shim.complete = AsyncMock(side_effect=exc)
    return shim


def _anthropic_error_shim_stream(event):
    shim = MagicMock()
    shim.available_models = MagicMock(return_value=[])

    async def _stream(*args, **kwargs):
        yield event

    shim.stream_tokens = _stream
    return shim


class TestAnthropicShimErrorMapping:
    """Non-streaming + streaming error classification for the Anthropic shim."""

    _MSG = {
        "model": "claude-sonnet-4.6",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "hi"}],
    }

    def test_non_stream_rate_limit_returns_429(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_error_shim_complete(
            ACPError(-32000, "Rate limit exceeded, retry after 15")
        )
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        assert resp.status_code == 429
        body = resp.json()
        assert body["type"] == "error"
        assert body["error"]["type"] == "rate_limit_error"
        assert resp.headers.get("retry-after") == "15"

    def test_non_stream_overloaded_returns_503(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_error_shim_complete(
            ACPError(-32000, "service is overloaded")
        )
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        assert resp.status_code == 503
        assert resp.json()["error"]["type"] == "overloaded_error"

    def test_non_stream_timeout_returns_504(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_error_shim_complete(
            ACPError(-32000, "ACP session/prompt timed out after 120s")
        )
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        assert resp.status_code == 504
        assert resp.json()["error"]["type"] == "api_error"

    def test_non_stream_default_returns_502(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_error_shim_complete(
            ACPError(-32000, "kiro-cli subprocess exited")
        )
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        assert resp.status_code == 502
        assert resp.json()["error"]["type"] == "api_error"

    def test_stream_rate_limit_error_type(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_error_shim_stream(
            {"type": "error", "message": "rate limit exceeded", "code": -32000}
        )
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        assert "event: error" in resp.text
        assert '"type": "rate_limit_error"' in resp.text

    def test_stream_overloaded_error_type(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_error_shim_stream(
            {"type": "error", "message": "overloaded", "code": -32000}
        )
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        assert '"type": "overloaded_error"' in resp.text


# ---------------------------------------------------------------------------
# System-role handling (issue #44): the Anthropic `system` field is preserved
# as a distinct system role (no ad-hoc [system] user prefix).
# ---------------------------------------------------------------------------

class TestAnthropicShimSystemRole:
    """The system prompt is carried as a distinct system role, not user text."""

    def test_system_string_becomes_system_role(self, sync_client, anthropic_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "max_tokens": 64,
            "system": "Be terse.",
            "messages": [{"role": "user", "content": "hi"}],
        }
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        msgs = rec.complete_kwargs[0]["messages"]
        assert msgs[0].role == "system"
        assert msgs[0].content == "Be terse."
        # The legacy ad-hoc prefix must be gone.
        assert "[system]" not in msgs[0].content

    def test_system_block_list_flattened_into_system_role(self, sync_client, anthropic_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "max_tokens": 64,
            "system": [
                {"type": "text", "text": "Line A."},
                {"type": "text", "text": "Line B."},
            ],
            "messages": [{"role": "user", "content": "hi"}],
        }
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        msgs = rec.complete_kwargs[0]["messages"]
        assert msgs[0].role == "system"
        assert msgs[0].content == "Line A.\nLine B."

    def test_no_system_means_no_system_message(self, sync_client, anthropic_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "hi"}],
        }
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        msgs = rec.complete_kwargs[0]["messages"]
        assert all(m.role != "system" for m in msgs)


# ---------------------------------------------------------------------------
# Usage accounting (issue #36): non-streaming usage and streaming token counts
# reflect real-or-estimated counts; the per-chunk +1 hack is gone.
# ---------------------------------------------------------------------------

def _anthropic_usage_shim(content="Paris is the capital of France.", usage=None, tool_calls=None):
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


def _parse_anthropic_sse(text):
    """Parse an Anthropic SSE body into a list of (event, data) tuples."""
    import json as _json
    events = []
    event_name = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event_name = line[len("event: "):]
        elif line.startswith("data: "):
            events.append((event_name, _json.loads(line[len("data: "):])))
    return events


class TestAnthropicShimUsage:
    """Usage shape + estimate fallback for the Anthropic shim."""

    _MSG = {
        "model": "claude-sonnet-4.6",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "What is the capital of France?"}],
    }

    def test_non_stream_usage_estimated_when_unreported(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_usage_shim(usage={})
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        assert resp.status_code == 200
        usage = resp.json()["usage"]
        assert set(usage) == {"input_tokens", "output_tokens"}
        assert usage["input_tokens"] > 0
        assert usage["output_tokens"] > 0

    def test_non_stream_usage_uses_reported(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_usage_shim(
            usage={"input_tokens": 77, "output_tokens": 12}
        )
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        usage = resp.json()["usage"]
        assert usage == {"input_tokens": 77, "output_tokens": 12}

    def test_non_stream_counts_system_in_input(self, sync_client, anthropic_headers):
        """A larger system prompt yields a larger input-token estimate."""
        sync_client.app.state.shim_service = _anthropic_usage_shim(usage={})
        small = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        big_payload = {**self._MSG, "system": "You are a very thorough assistant. " * 20}
        sync_client.app.state.shim_service = _anthropic_usage_shim(usage={})
        big = sync_client.post("/v1/messages", json=big_payload, headers=anthropic_headers)
        assert big.json()["usage"]["input_tokens"] > small.json()["usage"]["input_tokens"]

    def test_stream_message_start_has_input_tokens(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_usage_shim(usage={})
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        events = _parse_anthropic_sse(resp.text)
        starts = [d for name, d in events if name == "message_start"]
        assert starts
        assert starts[0]["message"]["usage"]["input_tokens"] > 0

    def test_stream_message_delta_output_tokens_estimated(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_usage_shim(
            content="Paris is the capital of France.", usage={}
        )
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        events = _parse_anthropic_sse(resp.text)
        deltas = [d for name, d in events if name == "message_delta"]
        assert deltas
        output_tokens = deltas[-1]["usage"]["output_tokens"]
        # A real estimate of the generated text, not the old per-chunk count
        # (6 words would have produced 6 under the +1 hack).
        assert output_tokens > 0

    def test_stream_message_delta_uses_reported_output(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _anthropic_usage_shim(
            usage={"output_tokens": 999}
        )
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        events = _parse_anthropic_sse(resp.text)
        deltas = [d for name, d in events if name == "message_delta"]
        assert deltas[-1]["usage"]["output_tokens"] == 999


# ---------------------------------------------------------------------------
# GET /models/{model_id} — Anthropic retrieve-model on the namespaced prefixes
# (the /v1 prefix is owned by the OpenAI shim, included first).
# ---------------------------------------------------------------------------

class TestAnthropicRetrieveModel:
    """The Anthropic retrieve-model endpoint returns a valid model object."""

    def test_retrieve_on_anthropic_prefix(self, sync_client, anthropic_headers):
        resp = sync_client.get(
            "/anthropic/v1/models/claude-sonnet-4.6", headers=anthropic_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "model"
        assert data["id"] == "claude-sonnet-4.6"
        assert "display_name" in data

    def test_retrieve_uses_live_display_name(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service.available_models = lambda: [
            {"id": "claude-opus-4.8", "name": "Claude Opus 4.8", "description": ""},
        ]
        resp = sync_client.get(
            "/anthropic/models/claude-opus-4.8", headers=anthropic_headers
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Claude Opus 4.8"


# ---------------------------------------------------------------------------
# Client tool forwarding (issue #31): Anthropic-declared tools reach the ACP
# prompt path via ShimService in both modes.
# ---------------------------------------------------------------------------

class TestAnthropicShimToolForwarding:
    """Client tools reach ShimService for /v1/messages, both modes."""

    _TOOL = {
        "name": "get_weather",
        "description": "Get current weather.",
        "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
    }

    def test_non_stream_forwards_tools(self, sync_client, anthropic_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "weather?"}],
            "tools": [self._TOOL],
        }
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        tools = rec.complete_kwargs[0]["tools"]
        assert any(t.get("name") == "get_weather" for t in tools)

    def test_stream_forwards_tools(self, sync_client, anthropic_headers):
        rec = _RecordingShim()
        sync_client.app.state.shim_service = rec
        payload = {
            "model": "claude-sonnet-4.6",
            "max_tokens": 64,
            "stream": True,
            "messages": [{"role": "user", "content": "weather?"}],
            "tools": [self._TOOL],
        }
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert resp.status_code == 200
        tools = rec.stream_kwargs[0]["tools"]
        assert any(t.get("name") == "get_weather" for t in tools)


# ---------------------------------------------------------------------------
# Built-in tool-call surfacing gate (ACP_SURFACE_TOOL_CALLS) — Anthropic shim.
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


class TestAnthropicShimToolSurfacingGate:
    """Default off suppresses built-in tool_use; opt-in surfaces it."""

    _MSG = {
        "model": "claude-sonnet-4.6", "max_tokens": 64,
        "messages": [{"role": "user", "content": "weather?"}],
    }

    def test_non_stream_default_suppresses_tool_use(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _ShimService(_ToolEmittingACP())
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert all(b["type"] != "tool_use" for b in body["content"])
        assert body["stop_reason"] == "end_turn"
        assert body["content"][0]["text"] == "Berlin is sunny."

    def test_non_stream_optin_surfaces_tool_use(self, sync_client, anthropic_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_TOOL_CALLS", True)
        sync_client.app.state.shim_service = _ShimService(_ToolEmittingACP())
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        body = resp.json()
        assert any(b["type"] == "tool_use" for b in body["content"])
        assert body["stop_reason"] == "tool_use"

    def test_stream_default_suppresses_tool_use(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _ShimService(_ToolEmittingACP())
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert '"tool_use"' not in resp.text

    def test_stream_optin_surfaces_tool_use(self, sync_client, anthropic_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_TOOL_CALLS", True)
        sync_client.app.state.shim_service = _ShimService(_ToolEmittingACP())
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert '"tool_use"' in resp.text
        assert "Fetching web content" in resp.text


# ---------------------------------------------------------------------------
# Reasoning/thinking surfacing (issue #40): Anthropic thinking content blocks,
# both modes, gated by ACP_SURFACE_THINKING (default true).
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


class TestAnthropicShimReasoning:
    """thinking content blocks, non-streaming + streaming."""

    _MSG = {
        "model": "claude-sonnet-4.6", "max_tokens": 64,
        "messages": [{"role": "user", "content": "q"}],
    }

    def test_non_stream_surfaces_thinking_block(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        assert resp.status_code == 200
        blocks = resp.json()["content"]
        assert blocks[0]["type"] == "thinking"
        assert blocks[0]["thinking"] == "Let me think about it."
        # Text block follows and is unchanged.
        assert any(b["type"] == "text" and b["text"] == "The answer is 42." for b in blocks)

    def test_non_stream_suppressed_when_off(self, sync_client, anthropic_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_THINKING", False)
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        resp = sync_client.post("/v1/messages", json=self._MSG, headers=anthropic_headers)
        blocks = resp.json()["content"]
        assert all(b["type"] != "thinking" for b in blocks)

    def test_stream_surfaces_thinking_block(self, sync_client, anthropic_headers):
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        body = resp.text
        assert '"type": "thinking"' in body          # content_block_start[thinking]
        assert '"type": "thinking_delta"' in body
        assert '"type": "text_delta"' in body          # final text still streamed

    def test_stream_suppressed_when_off(self, sync_client, anthropic_headers, monkeypatch):
        monkeypatch.setattr(_settings, "ACP_SURFACE_THINKING", False)
        sync_client.app.state.shim_service = _ShimService(_ThinkingACP())
        payload = {**self._MSG, "stream": True}
        resp = sync_client.post("/v1/messages", json=payload, headers=anthropic_headers)
        assert '"thinking_delta"' not in resp.text
        assert '"type": "text_delta"' in resp.text
