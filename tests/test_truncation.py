"""Tests for message truncation and recovery."""
from __future__ import annotations

import pytest

from kiro.truncation_state import truncate_messages, TruncationState, estimate_conversation_tokens
from kiro.truncation_recovery import with_truncation_recovery
from kiro.acp_models import ACPMessage, ACPTextBlock


def _msg(role: str, text: str) -> ACPMessage:
    return ACPMessage(role=role, content=[ACPTextBlock(type="text", text=text)])


class TestTruncation:
    def test_no_truncation_needed(self):
        messages = [_msg("user", "short"), _msg("assistant", "ok")]
        result, state = truncate_messages(messages, context_window=200_000)
        assert state.was_truncated is False
        assert len(result) == 2

    def test_truncation_drops_oldest(self):
        messages = [_msg("user", "a " * 500) for _ in range(20)]
        result, state = truncate_messages(messages, context_window=4_000, output_reserve=512)
        assert state.was_truncated is True
        assert len(result) < 20

    def test_min_messages_kept(self):
        messages = [_msg("user", "x " * 1000) for _ in range(10)]
        result, state = truncate_messages(messages, context_window=100, output_reserve=50)
        assert len(result) >= 2

    def test_system_tokens_counted(self):
        messages = [_msg("user", "hi")]
        _, state_with = truncate_messages(messages, system="Long system " * 100, context_window=200_000)
        _, state_without = truncate_messages(messages, system=None, context_window=200_000)
        assert state_with.input_tokens_estimated >= state_without.input_tokens_estimated


class TestTruncationRecovery:
    async def test_successful_invoke_no_truncation(self):
        messages = [_msg("user", "hello")]
        call_count = 0

        async def invoke(msgs, sys):
            nonlocal call_count
            call_count += 1
            return "ok"

        result, state = await with_truncation_recovery(messages, None, None, invoke)
        assert result == "ok"
        assert call_count == 1
        assert state.was_truncated is False

    async def test_recovery_on_overflow(self):
        messages = [_msg("user", "x " * 200) for _ in range(30)]
        attempt = 0

        async def invoke(msgs, sys):
            nonlocal attempt
            attempt += 1
            if attempt <= 2:
                raise RuntimeError("context_length_exceeded: too long")
            return "recovered"

        result, state = await with_truncation_recovery(
            messages, None, None, invoke, context_window=50_000
        )
        assert result == "recovered"
        assert state.was_truncated is True

    async def test_non_overflow_error_propagates(self):
        messages = [_msg("user", "hi")]

        async def invoke(msgs, sys):
            raise ValueError("unrelated error")

        with pytest.raises(ValueError, match="unrelated error"):
            await with_truncation_recovery(messages, None, None, invoke)
