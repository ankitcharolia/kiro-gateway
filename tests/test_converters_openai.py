"""Tests for OpenAI <-> ACP converters."""
from __future__ import annotations

import json
import pytest

from kiro.converters_openai import openai_request_to_acp, acp_response_to_openai
from kiro.models_openai import Message


class TestOpenAIRequestToACP:
    def test_basic_conversion(self, openai_basic_request):
        acp = openai_request_to_acp(openai_basic_request)
        assert acp.model == "gpt-4o"
        # system message is extracted
        assert acp.system == "You are a helpful assistant."
        # only user message remains
        assert len(acp.messages) == 1
        assert acp.messages[0].role == "user"

    def test_user_content_preserved(self, openai_basic_request):
        acp = openai_request_to_acp(openai_basic_request)
        text_block = acp.messages[0].content[0]
        assert text_block.type == "text"
        assert text_block.text == "Hello!"

    def test_tool_definitions_converted(self, openai_tool_request):
        acp = openai_request_to_acp(openai_tool_request)
        assert acp.tools is not None
        assert len(acp.tools) == 1
        assert acp.tools[0].name == "get_weather"
        assert "location" in acp.tools[0].input_schema.get("properties", {})

    def test_thinking_passthrough(self, openai_thinking_request):
        acp = openai_request_to_acp(openai_thinking_request)
        assert acp.thinking is not None
        assert acp.thinking["type"] == "enabled"
        assert acp.thinking["budget_tokens"] == 4096

    def test_reasoning_effort_mapped(self):
        from kiro.models_openai import ChatCompletionRequest
        req = ChatCompletionRequest(
            model="claude-sonnet-4-5",
            messages=[Message(role="user", content="hi")],
            reasoning_effort="high",
        )
        acp = openai_request_to_acp(req)
        assert acp.thinking["budget_tokens"] == 32768

    def test_tool_call_turn_converted(self):
        from kiro.models_openai import ChatCompletionRequest, ToolCall, FunctionCall
        req = ChatCompletionRequest(
            model="gpt-4o",
            messages=[
                Message(role="user", content="weather?"),
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ToolCall(id="tc1", type="function",
                                 function=FunctionCall(name="get_weather", arguments='{"location":"Berlin"}'))
                    ],
                ),
                Message(role="tool", content='{"temp": 20}', tool_call_id="tc1"),
            ],
        )
        acp = openai_request_to_acp(req)
        roles = [m.role for m in acp.messages]
        assert "assistant" in roles
        assert "tool" in roles

    def test_multi_system_messages_merged(self):
        from kiro.models_openai import ChatCompletionRequest
        req = ChatCompletionRequest(
            model="gpt-4o",
            messages=[
                Message(role="system", content="Part 1."),
                Message(role="system", content="Part 2."),
                Message(role="user", content="hi"),
            ],
        )
        acp = openai_request_to_acp(req)
        assert "Part 1." in acp.system
        assert "Part 2." in acp.system


class TestACPResponseToOpenAI:
    def test_text_response(self, acp_text_response):
        resp = acp_response_to_openai(acp_text_response, model="gpt-4o")
        assert resp.choices[0].message.content == "Hello, world!"
        assert resp.choices[0].finish_reason == "stop"

    def test_tool_response(self, acp_tool_response):
        resp = acp_response_to_openai(acp_tool_response, model="gpt-4o")
        assert resp.choices[0].finish_reason == "tool_calls"
        tc = resp.choices[0].message.tool_calls[0]
        assert tc.function.name == "get_weather"
        args = json.loads(tc.function.arguments)
        assert args["location"] == "Berlin"

    def test_usage_mapped(self, acp_text_response):
        resp = acp_response_to_openai(acp_text_response, model="gpt-4o")
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.completion_tokens == 5
        assert resp.usage.total_tokens == 15

    def test_request_id_preserved(self, acp_text_response):
        resp = acp_response_to_openai(acp_text_response, model="gpt-4o", request_id="chatcmpl-abc")
        assert resp.id == "chatcmpl-abc"
