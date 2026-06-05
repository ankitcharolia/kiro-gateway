"""Tests for Anthropic <-> ACP converters."""
from __future__ import annotations

import pytest

from kiro.converters_anthropic import anthropic_request_to_acp, acp_response_to_anthropic


class TestAnthropicRequestToACP:
    def test_basic_conversion(self, anthropic_basic_request):
        acp = anthropic_request_to_acp(anthropic_basic_request)
        assert acp.model == "claude-sonnet-4-5"
        assert acp.system == "You are a helpful assistant."
        assert len(acp.messages) == 1
        assert acp.messages[0].role == "user"

    def test_tools_converted(self, anthropic_tool_request):
        acp = anthropic_request_to_acp(anthropic_tool_request)
        assert acp.tools is not None
        assert acp.tools[0].name == "get_weather"
        assert "location" in acp.tools[0].input_schema.get("properties", {})

    def test_thinking_passthrough(self):
        from kiro.models_anthropic import AnthropicRequest, AnthropicMessage, ThinkingConfig
        req = AnthropicRequest(
            model="claude-sonnet-4-5",
            messages=[AnthropicMessage(role="user", content="think!")],
            max_tokens=1024,
            thinking=ThinkingConfig(type="enabled", budget_tokens=8192),
        )
        acp = anthropic_request_to_acp(req)
        assert acp.thinking["budget_tokens"] == 8192

    def test_system_as_block_list(self):
        from kiro.models_anthropic import AnthropicRequest, AnthropicMessage, TextContentBlock
        req = AnthropicRequest(
            model="claude-sonnet-4-5",
            messages=[AnthropicMessage(role="user", content="hi")],
            system=[TextContentBlock(type="text", text="Block system prompt.")],
            max_tokens=128,
        )
        acp = anthropic_request_to_acp(req)
        assert "Block system prompt." in acp.system


class TestACPResponseToAnthropic:
    def test_text_response(self, acp_text_response):
        resp = acp_response_to_anthropic(acp_text_response, model="claude-sonnet-4-5")
        assert resp.role == "assistant"
        assert resp.content[0].type == "text"
        assert resp.content[0].text == "Hello, world!"
        assert resp.stop_reason == "end_turn"

    def test_tool_response(self, acp_tool_response):
        resp = acp_response_to_anthropic(acp_tool_response, model="claude-sonnet-4-5")
        assert resp.stop_reason == "tool_use"
        tc = resp.content[0]
        assert tc.type == "tool_use"
        assert tc.name == "get_weather"
        assert tc.input["location"] == "Berlin"

    def test_thinking_response(self, acp_thinking_response):
        resp = acp_response_to_anthropic(acp_thinking_response, model="claude-sonnet-4-5")
        types = [b.type for b in resp.content]
        assert "thinking" in types
        assert "text" in types

    def test_usage_mapped(self, acp_text_response):
        resp = acp_response_to_anthropic(acp_text_response, model="claude-sonnet-4-5")
        assert resp.usage.input_tokens == 10
        assert resp.usage.output_tokens == 5
