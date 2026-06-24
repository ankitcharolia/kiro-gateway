"""
Unit tests for kiro.error_mapping.

Verify that ACP/upstream failures classify into the correct HTTP status codes
and into the OpenAI/Anthropic native error envelopes, including Retry-After
extraction.
"""
from __future__ import annotations

import pytest

from kiro.acp_client import ACPError
from kiro.error_mapping import (
    MappedError,
    classify_error,
    classify_event,
    classify_exception,
)


class TestClassifyErrorStatus:
    """classify_error resolves the right HTTP status for each condition."""

    @pytest.mark.parametrize("message", [
        "Rate limit exceeded",
        "rate-limited by upstream",
        "Too Many Requests",
        "request was throttled",
        "quota exceeded for this account",
        "upstream returned 429",
    ])
    def test_rate_limit_maps_to_429(self, message):
        assert classify_error(message).status_code == 429

    @pytest.mark.parametrize("message", [
        "The service is overloaded",
        "503 Service Unavailable",
        "server is temporarily unavailable",
        "model is at capacity, try again later",
        "Anthropic 529 overloaded_error",
    ])
    def test_overloaded_maps_to_503(self, message):
        assert classify_error(message).status_code == 503

    @pytest.mark.parametrize("message", [
        "ACP session/prompt timed out after 120s",
        "upstream timeout",
        "deadline exceeded",
    ])
    def test_timeout_maps_to_504(self, message):
        assert classify_error(message).status_code == 504

    @pytest.mark.parametrize("message", [
        "kiro-cli subprocess exited",
        "some unexpected internal failure",
        "",
    ])
    def test_default_maps_to_502(self, message):
        assert classify_error(message).status_code == 502


class TestClassifyErrorTypes:
    """Native error type strings are correct per API."""

    def test_rate_limit_types(self):
        mapped = classify_error("rate limit exceeded")
        assert mapped.openai_type == "rate_limit_error"
        assert mapped.anthropic_type == "rate_limit_error"

    def test_overloaded_types(self):
        mapped = classify_error("overloaded")
        assert mapped.openai_type == "server_error"
        assert mapped.anthropic_type == "overloaded_error"

    def test_timeout_types(self):
        mapped = classify_error("timed out")
        assert mapped.openai_type == "server_error"
        assert mapped.anthropic_type == "api_error"

    def test_default_types(self):
        mapped = classify_error("boom")
        assert mapped.openai_type == "server_error"
        assert mapped.anthropic_type == "api_error"


class TestRetryAfter:
    """Retry-After hints are extracted and surfaced as a header."""

    @pytest.mark.parametrize("message,expected", [
        ("rate limit exceeded, retry after 30", 30),
        ("Too many requests; retry-after: 12", 12),
        ("overloaded, try again in 5 seconds", 5),
    ])
    def test_extracts_retry_after(self, message, expected):
        assert classify_error(message).retry_after == expected

    def test_no_retry_after_when_absent(self):
        assert classify_error("rate limit exceeded").retry_after is None

    def test_header_present_when_retry_after(self):
        mapped = classify_error("rate limit exceeded, retry after 7")
        assert mapped.headers() == {"Retry-After": "7"}

    def test_header_empty_when_no_retry_after(self):
        assert classify_error("boom").headers() == {}


class TestNativeEnvelopes:
    """to_openai_error / to_anthropic_error render the documented shapes."""

    def test_openai_envelope(self):
        mapped = classify_error("rate limit exceeded")
        body = mapped.to_openai_error()
        assert set(body) == {"error"}
        assert body["error"]["type"] == "rate_limit_error"
        assert body["error"]["message"] == "rate limit exceeded"
        assert body["error"]["code"] is None
        assert body["error"]["param"] is None

    def test_anthropic_envelope(self):
        mapped = classify_error("the service is overloaded")
        body = mapped.to_anthropic_error()
        assert body["type"] == "error"
        assert body["error"]["type"] == "overloaded_error"
        assert body["error"]["message"] == "the service is overloaded"


class TestClassifyExceptionAndEvent:
    """classify_exception / classify_event read code/data and message."""

    def test_classify_acp_exception_rate_limit(self):
        exc = ACPError(-32000, "Too Many Requests")
        assert classify_exception(exc).status_code == 429

    def test_classify_exception_reads_data(self):
        exc = ACPError(-32000, "upstream failure", data={"reason": "throttled"})
        assert classify_exception(exc).status_code == 429

    def test_classify_plain_exception_defaults_502(self):
        assert classify_exception(RuntimeError("kaboom")).status_code == 502

    def test_classify_event_uses_message(self):
        mapped = classify_event({"type": "error", "message": "rate limit exceeded"})
        assert mapped.status_code == 429
        assert mapped.openai_type == "rate_limit_error"

    def test_classify_event_falls_back_to_unknown(self):
        mapped = classify_event({"type": "error"})
        assert mapped.status_code == 502
        assert mapped.message == "Unknown error"
