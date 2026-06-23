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
