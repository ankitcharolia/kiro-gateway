"""Tests for OpenAI SSE chunk generator."""
from __future__ import annotations

import json
import pytest

from kiro.streaming_openai import acp_stream_to_openai_chunks


async def _collect(gen):
    chunks = []
    async for line in gen:
        chunks.append(line)
    return chunks


class TestOpenAIStreamChunks:
    @pytest.mark.streaming
    async def test_basic_stream_ends_with_done(self, acp_stream_events, make_event_gen):
        gen = acp_stream_to_openai_chunks(make_event_gen(acp_stream_events), model="gpt-4o")
        chunks = await _collect(gen)
        assert chunks[-1].strip() == "data: [DONE]"

    @pytest.mark.streaming
    async def test_text_delta_present(self, acp_stream_events, make_event_gen):
        gen = acp_stream_to_openai_chunks(make_event_gen(acp_stream_events), model="gpt-4o")
        chunks = await _collect(gen)
        payloads = [c for c in chunks if c.startswith("data: {")]
        texts = []
        for p in payloads:
            data = json.loads(p[6:])
            for choice in data.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("content"):
                    texts.append(delta["content"])
        assert "Hello" in texts or any("Hello" in t for t in texts)

    @pytest.mark.streaming
    async def test_finish_reason_stop(self, acp_stream_events, make_event_gen):
        gen = acp_stream_to_openai_chunks(make_event_gen(acp_stream_events), model="gpt-4o")
        chunks = await _collect(gen)
        finish_chunks = []
        for c in chunks:
            if c.startswith("data: {"):
                data = json.loads(c[6:])
                for choice in data.get("choices", []):
                    if choice.get("finish_reason"):
                        finish_chunks.append(choice["finish_reason"])
        assert "stop" in finish_chunks

    @pytest.mark.streaming
    async def test_tool_call_chunks(self, acp_stream_tool_events, make_event_gen):
        gen = acp_stream_to_openai_chunks(make_event_gen(acp_stream_tool_events), model="gpt-4o")
        chunks = await _collect(gen)
        tool_chunks = []
        for c in chunks:
            if c.startswith("data: {"):
                data = json.loads(c[6:])
                for choice in data.get("choices", []):
                    tc = choice.get("delta", {}).get("tool_calls")
                    if tc:
                        tool_chunks.extend(tc)
        assert any(t.get("function", {}).get("name") == "get_weather" for t in tool_chunks)

    @pytest.mark.streaming
    async def test_thinking_delta(self, acp_stream_thinking_events, make_event_gen):
        gen = acp_stream_to_openai_chunks(make_event_gen(acp_stream_thinking_events), model="claude-sonnet-4-5")
        chunks = await _collect(gen)
        reasoning = []
        for c in chunks:
            if c.startswith("data: {"):
                data = json.loads(c[6:])
                for choice in data.get("choices", []):
                    rc = choice.get("delta", {}).get("reasoning_content")
                    if rc:
                        reasoning.append(rc)
        assert any("Thinking" in r for r in reasoning)
