"""Tests for Anthropic SSE event generator."""
from __future__ import annotations

import json
import pytest

from kiro.streaming_anthropic import acp_stream_to_anthropic_events


async def _collect(gen):
    events = []
    async for line in gen:
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


class TestAnthropicStreamEvents:
    @pytest.mark.streaming
    async def test_message_start_first(self, acp_stream_events, make_event_gen):
        gen = acp_stream_to_anthropic_events(make_event_gen(acp_stream_events), model="claude-sonnet-4-5")
        events = await _collect(gen)
        assert events[0]["type"] == "message_start"

    @pytest.mark.streaming
    async def test_message_stop_last(self, acp_stream_events, make_event_gen):
        gen = acp_stream_to_anthropic_events(make_event_gen(acp_stream_events), model="claude-sonnet-4-5")
        events = await _collect(gen)
        assert events[-1]["type"] == "message_stop"

    @pytest.mark.streaming
    async def test_content_block_sequence(self, acp_stream_events, make_event_gen):
        gen = acp_stream_to_anthropic_events(make_event_gen(acp_stream_events), model="claude-sonnet-4-5")
        events = await _collect(gen)
        types = [e["type"] for e in events]
        assert "content_block_start" in types
        assert "content_block_delta" in types
        assert "content_block_stop" in types

    @pytest.mark.streaming
    async def test_text_delta_content(self, acp_stream_events, make_event_gen):
        gen = acp_stream_to_anthropic_events(make_event_gen(acp_stream_events), model="claude-sonnet-4-5")
        events = await _collect(gen)
        deltas = [
            e["delta"]["text"]
            for e in events
            if e.get("type") == "content_block_delta"
            and e.get("delta", {}).get("type") == "text_delta"
        ]
        assert "Hello" in deltas or any("Hello" in d for d in deltas)

    @pytest.mark.streaming
    async def test_stop_reason_in_message_delta(self, acp_stream_events, make_event_gen):
        gen = acp_stream_to_anthropic_events(make_event_gen(acp_stream_events), model="claude-sonnet-4-5")
        events = await _collect(gen)
        delta_events = [e for e in events if e.get("type") == "message_delta"]
        assert any(e.get("delta", {}).get("stop_reason") == "end_turn" for e in delta_events)
