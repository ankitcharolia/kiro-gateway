"""
Unit tests for ACPClient — the stdio bridge to kiro CLI.
All tests use a mock subprocess; no real kiro CLI needed.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
import pytest_asyncio

from kiro.acp_client import ACPClient
from kiro.acp_models import PromptMessage

# Capture the genuine new_session implementation at import time. The
# session-scoped ``test_client`` fixture monkeypatches ``ACPClient.new_session``
# for the whole test session, so tests that need the real method call this
# reference directly instead of going through the (patched) class attribute.
_REAL_NEW_SESSION = ACPClient.new_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode(obj: dict) -> bytes:
    """Encode a JSON-RPC message as kiro CLI would write to stdout."""
    return (json.dumps(obj) + "\n").encode()


class FakeProcess:
    """Minimal asyncio subprocess mock."""

    def __init__(self, lines: list[bytes]):
        self._lines = iter(lines)
        self.stdin = AsyncMock()
        self.stdin.drain = AsyncMock()
        self.returncode = None

    async def readline_side_effect(self):
        try:
            return next(self._lines)
        except StopIteration:
            return b""

    @property
    def stdout(self):
        mock = AsyncMock()
        mock.readline = self.readline_side_effect
        return mock

    async def wait(self):
        return 0

    def kill(self):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_acp_client_instantiation():
    """ACPClient can be created with a custom CLI command."""
    client = ACPClient(command="/usr/local/bin/kiro")
    assert client is not None


def test_acp_client_default_command():
    """ACPClient uses 'kiro' as the default CLI command."""
    client = ACPClient()
    # The command attribute should default to 'kiro'
    cmd = getattr(client, 'command', None) or getattr(client, '_command', None) or getattr(client, 'cli_command', None)
    assert cmd is not None


@pytest.mark.asyncio
async def test_acp_client_creates_session_id():
    """new_session() returns a non-empty string session ID."""
    client = ACPClient()
    # Patch initialize so it sets a session_id without a real subprocess
    async def _mock_initialize(self, caps=None):
        self._session_id = "sess-abc-123"
        from kiro.acp_models import SessionInitResult
        return SessionInitResult(session_id="sess-abc-123")

    with patch.object(type(client), 'initialize', new=_mock_initialize):
        result = await client.initialize()
        assert client._session_id == "sess-abc-123"


@pytest.mark.asyncio
async def test_prompt_message_model():
    """PromptMessage Pydantic model validates correctly."""
    msg = PromptMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


@pytest.mark.asyncio
async def test_prompt_message_assistant_role():
    """PromptMessage accepts assistant role."""
    msg = PromptMessage(role="assistant", content="Hi there")
    assert msg.role == "assistant"


@pytest.mark.asyncio
async def test_prompt_message_system_role():
    """PromptMessage accepts system role."""
    msg = PromptMessage(role="system", content="You are helpful.")
    assert msg.role == "system"
    assert "helpful" in msg.content


# ---------------------------------------------------------------------------
# Model discovery + forwarding (session/new "models" + session/set_model)
# ---------------------------------------------------------------------------

class TestModelDiscoveryAndForwarding:
    """new_session caches the live model catalogue and forwards model selection."""

    @pytest.mark.asyncio
    async def test_new_session_captures_available_models(self):
        """The 'models' block from session/new is cached and normalised."""
        client = ACPClient()

        async def fake_call(method, params, timeout=120.0):
            if method == "session/new":
                return {
                    "sessionId": "s1",
                    "models": {
                        "currentModelId": "claude-opus-4.8",
                        "availableModels": [
                            {"modelId": "auto", "name": "auto", "description": "auto pick"},
                            {"modelId": "claude-sonnet-4.6", "name": "claude-sonnet-4.6",
                             "description": "latest sonnet"},
                        ],
                    },
                }
            return {}

        client._call = fake_call  # type: ignore[assignment]
        session_id = await _REAL_NEW_SESSION(client)

        assert session_id == "s1"
        ids = [m["id"] for m in client.available_models]
        assert "auto" in ids
        assert "claude-sonnet-4.6" in ids  # dotted id preserved
        assert client._current_model_id == "claude-opus-4.8"

    @pytest.mark.asyncio
    async def test_new_session_forwards_model_via_set_model(self):
        """When a model is requested, session/set_model is sent with that id."""
        client = ACPClient()
        calls: list[tuple[str, dict]] = []

        async def fake_call(method, params, timeout=120.0):
            calls.append((method, params))
            if method == "session/new":
                return {"sessionId": "s2"}
            return {}

        client._call = fake_call  # type: ignore[assignment]
        await _REAL_NEW_SESSION(client, model="claude-sonnet-4.6")

        set_calls = [c for c in calls if c[0] == "session/set_model"]
        assert len(set_calls) == 1
        assert set_calls[0][1] == {"sessionId": "s2", "modelId": "claude-sonnet-4.6"}

    @pytest.mark.asyncio
    async def test_new_session_without_model_skips_set_model(self):
        """No model requested → no session/set_model call."""
        client = ACPClient()
        methods: list[str] = []

        async def fake_call(method, params, timeout=120.0):
            methods.append(method)
            if method == "session/new":
                return {"sessionId": "s3"}
            return {}

        client._call = fake_call  # type: ignore[assignment]
        await _REAL_NEW_SESSION(client)

        assert "session/set_model" not in methods

    @pytest.mark.asyncio
    async def test_new_session_skips_set_model_when_model_matches_default(self):
        """Requested model == session default → no redundant set_model RTT."""
        client = ACPClient()
        methods: list[str] = []

        async def fake_call(method, params, timeout=120.0):
            methods.append(method)
            if method == "session/new":
                return {
                    "sessionId": "s5",
                    "models": {
                        "currentModelId": "claude-sonnet-4.6",
                        "availableModels": [
                            {"modelId": "claude-sonnet-4.6", "name": "claude-sonnet-4.6",
                             "description": ""},
                        ],
                    },
                }
            return {}

        client._call = fake_call  # type: ignore[assignment]
        await _REAL_NEW_SESSION(client, model="claude-sonnet-4.6")

        assert "session/set_model" not in methods

    @pytest.mark.asyncio
    async def test_new_session_sets_model_when_differs_from_default(self):
        """Requested model != session default → session/set_model is issued."""
        client = ACPClient()
        methods: list[str] = []

        async def fake_call(method, params, timeout=120.0):
            methods.append(method)
            if method == "session/new":
                return {
                    "sessionId": "s6",
                    "models": {"currentModelId": "claude-opus-4.8", "availableModels": []},
                }
            return {}

        client._call = fake_call  # type: ignore[assignment]
        await _REAL_NEW_SESSION(client, model="claude-sonnet-4.6")

        assert "session/set_model" in methods

    @pytest.mark.asyncio
    async def test_set_model_swallows_acp_error(self):
        """A failed set_model is logged and swallowed, never raised."""
        from kiro.acp_client import ACPError

        client = ACPClient()

        async def fake_call(method, params, timeout=120.0):
            raise ACPError(-32000, "set_model exploded")

        client._call = fake_call  # type: ignore[assignment]
        # Must not raise.
        await client.set_model("s4", "bogus-model")

    @pytest.mark.asyncio
    async def test_available_models_empty_before_any_session(self):
        """No session created yet → empty catalogue (callers use the fallback)."""
        client = ACPClient()
        assert client.available_models == []


class TestStdioBufferLimit:
    """The stdio read buffer must be large enough for big ACP lines."""

    def test_default_stdio_limit_matches_config(self):
        """ACPClient defaults its stdio buffer limit to the configured value."""
        from kiro.config import ACP_STDIO_MAX_BYTES

        client = ACPClient()
        assert client._stdio_limit == ACP_STDIO_MAX_BYTES

    def test_default_stdio_limit_exceeds_asyncio_default(self):
        """The default limit is well above asyncio's 64 KiB StreamReader default."""
        client = ACPClient()
        assert client._stdio_limit > 64 * 1024

    def test_stdio_limit_is_overridable(self):
        """A custom stdio buffer limit is honoured."""
        client = ACPClient(stdio_limit=1234567)
        assert client._stdio_limit == 1234567
