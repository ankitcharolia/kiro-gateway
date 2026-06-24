"""
Unit tests for the usage-accounting helpers in kiro.tokenizer.

Verify that normalize_usage prefers real reported counts and otherwise falls
back to consistent tokenizer estimates (never silently 0), and that the
estimate is field-independent.
"""
from __future__ import annotations

import pytest

from kiro.tokenizer import (
    estimate_completion_tokens,
    normalize_usage,
)


class TestEstimateCompletionTokens:
    """estimate_completion_tokens covers text and tool calls."""

    def test_empty_is_zero(self):
        assert estimate_completion_tokens("", None) == 0

    def test_text_is_positive(self):
        assert estimate_completion_tokens("Hello, world! This is some output.") > 0

    def test_tool_calls_counted(self):
        text_only = estimate_completion_tokens("hi")
        with_tool = estimate_completion_tokens(
            "hi",
            [{"name": "get_weather", "arguments": {"location": "Berlin"}}],
        )
        assert with_tool > text_only

    def test_anthropic_input_key_supported(self):
        assert estimate_completion_tokens(
            "", [{"name": "x", "input": {"a": 1}}]
        ) > 0


class TestNormalizeUsageReported:
    """Reported, positive counts win and mark the result non-estimated."""

    def test_all_reported(self):
        usage = normalize_usage(
            {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            prompt_messages=[{"role": "user", "content": "x"}],
            completion_text="y",
        )
        assert usage == {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated": False,
        }

    def test_total_derived_when_absent(self):
        usage = normalize_usage(
            {"input_tokens": 10, "output_tokens": 5},
            prompt_messages=[{"role": "user", "content": "x"}],
            completion_text="y",
        )
        assert usage["total_tokens"] == 15


class TestNormalizeUsageEstimated:
    """Missing/zero counts fall back to a consistent tokenizer estimate."""

    def test_no_reported_estimates_both(self):
        usage = normalize_usage(
            None,
            prompt_messages=[{"role": "user", "content": "Hello there, how are you?"}],
            completion_text="I am doing well, thank you!",
        )
        assert usage["input_tokens"] > 0
        assert usage["output_tokens"] > 0
        assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
        assert usage["estimated"] is True

    def test_zero_reported_treated_as_missing(self):
        usage = normalize_usage(
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            prompt_messages=[{"role": "user", "content": "some prompt text"}],
            completion_text="some completion text",
        )
        assert usage["input_tokens"] > 0
        assert usage["output_tokens"] > 0
        assert usage["estimated"] is True

    def test_per_field_fallback(self):
        usage = normalize_usage(
            {"input_tokens": 100},
            prompt_messages=[{"role": "user", "content": "x"}],
            completion_text="hello world output here",
        )
        assert usage["input_tokens"] == 100      # reported wins
        assert usage["output_tokens"] > 0          # estimated
        assert usage["estimated"] is True

    def test_shape_keys_always_present(self):
        usage = normalize_usage(None)
        assert set(usage) == {"input_tokens", "output_tokens", "total_tokens", "estimated"}
