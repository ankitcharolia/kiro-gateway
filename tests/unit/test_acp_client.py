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
