"""Shared pytest fixtures for kiro-gateway tests."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict, Any, List
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiro.models_openai import (
    ChatCompletionRequest, Message, Tool, FunctionDefinition, ToolCall, FunctionCall
)
from kiro.models_anthropic import (
    AnthropicRequest, AnthropicMessage, TextContentBlock,
    ToolUseContentBlock, AnthropicTool,
    AnthropicResponse, AnthropicUsage,
)
from kiro.acp_models import (
    ACPRequest, ACPMessage, ACPResponse, ACPUsage,
    ACPTextBlock, ACPToolUseBlock, ACPThinkingBlock,
)


# ---------------------------------------------------------------------------
# OpenAI fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def openai_basic_request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="gpt-4o",
        messages=[
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello!"),
        ],
        max_tokens=256,
        stream=False,
    )


@pytest.fixture
def openai_tool_request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="gpt-4o",
        messages=[Message(role="user", content="What is the weather?")],
        tools=[
            Tool(
                type="function",
                function=FunctionDefinition(
                    name="get_weather",
                    description="Get current weather",
                    parameters={
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                    },
                ),
            )
        ],
        max_tokens=512,
    )


@pytest.fixture
def openai_thinking_request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="claude-sonnet-4-5",
        messages=[Message(role="user", content="Solve this step by step.")],
        thinking={"type": "enabled", "budget_tokens": 4096},
        max_tokens=2048,
    )


# ---------------------------------------------------------------------------
# Anthropic fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anthropic_basic_request() -> AnthropicRequest:
    return AnthropicRequest(
        model="claude-sonnet-4-5",
        messages=[AnthropicMessage(role="user", content="Hello!")],
        system="You are a helpful assistant.",
        max_tokens=256,
    )


@pytest.fixture
def anthropic_tool_request() -> AnthropicRequest:
    return AnthropicRequest(
        model="claude-sonnet-4-5",
        messages=[AnthropicMessage(role="user", content="What is the weather?")],
        tools=[
            AnthropicTool(
                name="get_weather",
                description="Get current weather",
                input_schema={
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            )
        ],
        max_tokens=512,
    )


# ---------------------------------------------------------------------------
# ACP response fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def acp_text_response() -> ACPResponse:
    return ACPResponse(
        id="msg_test123",
        type="message",
        role="assistant",
        model="claude-sonnet-4-5",
        content=[ACPTextBlock(type="text", text="Hello, world!")],
        stop_reason="end_turn",
        usage=ACPUsage(input_tokens=10, output_tokens=5),
    )


@pytest.fixture
def acp_tool_response() -> ACPResponse:
    return ACPResponse(
        id="msg_tool456",
        type="message",
        role="assistant",
        model="claude-sonnet-4-5",
        content=[
            ACPToolUseBlock(
                type="tool_use",
                id="toolu_abc",
                name="get_weather",
                input={"location": "Berlin"},
            )
        ],
        stop_reason="tool_use",
        usage=ACPUsage(input_tokens=20, output_tokens=8),
    )


@pytest.fixture
def acp_thinking_response() -> ACPResponse:
    return ACPResponse(
        id="msg_think789",
        type="message",
        role="assistant",
        model="claude-sonnet-4-5",
        content=[
            ACPThinkingBlock(type="thinking", thinking="Let me reason through this..."),
            ACPTextBlock(type="text", text="The answer is 42."),
        ],
        stop_reason="end_turn",
        usage=ACPUsage(input_tokens=30, output_tokens=15),
    )


# ---------------------------------------------------------------------------
# Streaming event sequences
# ---------------------------------------------------------------------------

def _make_acp_events(include_tool: bool = False, include_thinking: bool = False):
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 10}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " world"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    ]
    if include_thinking:
        events.insert(1, {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}})
        events.insert(2, {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Thinking..."}})
        events.insert(3, {"type": "content_block_stop", "index": 0})
    if include_tool:
        events.insert(1, {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "toolu_x", "name": "get_weather"}})
        events.insert(2, {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"location":'}})
        events.insert(3, {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '"Berlin"}'}})
        events.insert(4, {"type": "content_block_stop", "index": 0})
    return events


async def _event_gen(events):
    for e in events:
        yield e


@pytest.fixture
def acp_stream_events():
    return _make_acp_events()


@pytest.fixture
def acp_stream_tool_events():
    return _make_acp_events(include_tool=True)


@pytest.fixture
def acp_stream_thinking_events():
    return _make_acp_events(include_thinking=True)


@pytest.fixture
def make_event_gen():
    return _event_gen


# ---------------------------------------------------------------------------
# MCP tools fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_auth_manager():
    """Mock auth manager for MCP API tests."""
    manager = Mock()
    manager.get_token = AsyncMock(return_value="test-bearer-token")
    manager.base_url = "https://test.kiro.dev"
    manager.mcp_endpoint = "https://test.kiro.dev/mcp/search"
    return manager


# ---------------------------------------------------------------------------
# Integration test fixtures
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient
from main import app  # app lives at repo root main.py, not inside kiro package
from kiro.config import PROXY_API_KEY


@pytest.fixture(scope="session")
def test_client():
    """Session-scoped FastAPI TestClient for integration tests.

    ACPClient.start/stop/initialize are patched with async no-ops so that the
    app lifespan does not attempt to spawn the real `kiro` binary, which is
    not available in the CI test environment.
    """
    async def _noop_start(self) -> None:
        self._proc = None
        self._reader_task = None

    async def _noop_stop(self) -> None:
        pass

    async def _noop_initialize(self, capabilities=None) -> None:
        pass

    with (
        patch("kiro.acp_client.ACPClient.start", new=_noop_start),
        patch("kiro.acp_client.ACPClient.stop", new=_noop_stop),
        patch("kiro.acp_client.ACPClient.initialize", new=_noop_initialize),
    ):
        with TestClient(app) as client:
            yield client


@pytest.fixture
def sync_client():
    """Function-scoped TestClient with ACP and ShimService fully mocked.

    Patches start/stop/initialize so no kiro CLI is spawned. Also installs a
    mock ShimService on app.state so shim routes return valid responses.
    Uses function scope to avoid cross-test state contamination.
    """
    from unittest.mock import AsyncMock, MagicMock

    async def _noop_start(self) -> None:
        self._proc = None
        self._reader_task = None

    async def _noop_stop(self) -> None:
        pass

    async def _noop_initialize(self, capabilities=None) -> None:
        pass

    mock_shim = MagicMock()
    mock_shim.complete = AsyncMock(return_value={
        "content": "Hello, world!",
        "tool_calls": [],
        "finish_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })

    async def _mock_stream(*args, **kwargs):
        yield {"type": "text", "content": "Hello"}
        yield {"type": "done", "finish_reason": "end_turn"}

    mock_shim.stream_tokens = _mock_stream

    with (
        patch("kiro.acp_client.ACPClient.start", new=_noop_start),
        patch("kiro.acp_client.ACPClient.stop", new=_noop_stop),
        patch("kiro.acp_client.ACPClient.initialize", new=_noop_initialize),
    ):
        with TestClient(app) as client:
            client.app.state.shim_service = mock_shim
            yield client


@pytest.fixture
def openai_headers() -> dict:
    """Authorization headers for OpenAI-compatible endpoints."""
    return {"Authorization": f"Bearer {PROXY_API_KEY}"}


@pytest.fixture
def anthropic_headers() -> dict:
    """x-api-key headers for Anthropic-compatible endpoints."""
    return {"x-api-key": PROXY_API_KEY}


@pytest.fixture
def sample_tool_definition() -> dict:
    """A valid OpenAI-format tool definition for use in request payloads."""
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                },
                "required": ["location"],
            },
        },
    }


@pytest.fixture
def valid_proxy_api_key() -> str:
    """Valid API key for authentication tests."""
    return PROXY_API_KEY


@pytest.fixture
def invalid_proxy_api_key() -> str:
    """Invalid API key for authentication failure tests."""
    return "invalid-key-000"


@pytest.fixture
def sample_models_data():
    """Sample model list for cache tests."""
    return [
        {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5"},
        {"id": "claude-opus-4-5", "name": "Claude Opus 4.5"},
    ]
