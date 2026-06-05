"""Tests for payload guard validation."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from kiro.payload_guards import guard_openai_request, guard_anthropic_request
from kiro.models_openai import ChatCompletionRequest, Message, Tool, FunctionDefinition
from kiro.models_anthropic import AnthropicRequest, AnthropicMessage, ThinkingConfig, AnthropicTool


class TestOpenAIGuards:
    def test_thinking_and_tools_mutually_exclusive(self):
        req = ChatCompletionRequest(
            model="claude-sonnet-4-5",
            messages=[Message(role="user", content="hi")],
            thinking={"type": "enabled", "budget_tokens": 1024},
            tools=[
                Tool(type="function", function=FunctionDefinition(name="fn", parameters={}))
            ],
        )
        guard_openai_request(req)
        assert req.tools is None

    def test_max_tokens_clamped(self):
        req = ChatCompletionRequest(
            model="claude-haiku-3-5",
            messages=[Message(role="user", content="hi")],
            max_tokens=999_999,
        )
        guard_openai_request(req)
        assert req.max_tokens <= 8_192

    def test_stop_sequences_truncated(self):
        req = ChatCompletionRequest(
            model="claude-sonnet-4-5",
            messages=[Message(role="user", content="hi")],
            stop=["a", "b", "c", "d", "e"],
        )
        guard_openai_request(req)
        assert len(req.stop) == 4

    def test_too_many_tools_raises(self):
        tools = [
            Tool(type="function", function=FunctionDefinition(name=f"fn_{i}", parameters={}))
            for i in range(130)
        ]
        req = ChatCompletionRequest(
            model="claude-sonnet-4-5",
            messages=[Message(role="user", content="hi")],
            tools=tools,
        )
        with pytest.raises(HTTPException) as exc_info:
            guard_openai_request(req)
        assert exc_info.value.status_code == 422


class TestAnthropicGuards:
    def test_thinking_stripped_for_non_supporting_model(self):
        req = AnthropicRequest(
            model="claude-haiku-3-5",
            messages=[AnthropicMessage(role="user", content="hi")],
            max_tokens=512,
            thinking=ThinkingConfig(type="enabled", budget_tokens=2048),
        )
        guard_anthropic_request(req)
        assert req.thinking is None

    def test_max_tokens_default_set(self):
        req = AnthropicRequest(
            model="claude-sonnet-4-5",
            messages=[AnthropicMessage(role="user", content="hi")],
            max_tokens=0,
        )
        guard_anthropic_request(req)
        assert req.max_tokens > 0
