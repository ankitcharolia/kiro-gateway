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


class TestAuthClassification:
    """kiro-cli's own credentials being unusable maps to 401 (issue #52).

    Distinct from the gateway's client auth: the remedy is `kiro-cli login` on
    the gateway host. The messages below are the ones the v3 agent server and
    the auth bridge actually produce (verified against a live kiro-cli 2.18.0
    probe: declining the callback fails session/prompt with
    "-32000 Auth refresh callback failed").
    """

    @pytest.mark.parametrize("message", [
        "Auth refresh callback failed: not supported",
        "[TokenExpiredError] Auth refresh callback failed",
        "TokenInvalidError: host returned no access token",
        "kiro-cli authentication failed; run `kiro-cli login`",
        "kiro-cli authentication bridge is disabled; set ACP_AUTH_BRIDGE=true",
        "upstream returned 401",
    ])
    def test_auth_failures_map_to_401(self, message):
        assert classify_error(message).status_code == 401

    def test_auth_error_types_are_native(self):
        mapped = classify_error("Auth refresh callback failed")
        assert mapped.openai_type == "authentication_error"
        assert mapped.anthropic_type == "authentication_error"

    def test_auth_message_names_the_remedy_when_empty(self):
        """Signal in structured data, empty message -> the fallback names the fix."""
        mapped = classify_error("", data={"message": "Auth refresh callback failed"})
        assert mapped.status_code == 401
        assert "kiro-cli login" in mapped.message

    def test_auth_envelopes_render_in_both_shapes(self):
        mapped = classify_error("Auth refresh callback failed")
        assert mapped.to_openai_error()["error"]["type"] == "authentication_error"
        assert mapped.to_anthropic_error()["error"]["type"] == "authentication_error"

    def test_rate_limit_still_wins_over_auth(self):
        """A throttled auth-bearing message stays retryable (429), not 401."""
        assert classify_error(
            "429 rate limit exceeded while refreshing token"
        ).status_code == 429

    def test_timeout_still_wins_over_auth(self):
        assert classify_error(
            "kiro-cli token callback timed out"
        ).status_code == 504

    def test_exception_path_classifies_auth(self):
        """Non-streaming completions surface ACPError -> 401."""
        exc = ACPError(-32000, "Auth refresh callback failed: not supported")
        assert classify_exception(exc).status_code == 401

    def test_event_path_classifies_auth(self):
        """Streaming error events classify identically to the exception path."""
        event = {"type": "error", "code": -32000,
                 "message": "Auth refresh callback failed: not supported"}
        assert classify_event(event).status_code == 401

    def test_auth_carries_no_retry_after(self):
        """Retrying without re-login cannot help, so no Retry-After is set."""
        assert classify_error("Auth refresh callback failed").headers() == {}

    def test_ordinary_failures_are_unaffected(self):
        """The word 'token' alone must not trip the auth class."""
        assert classify_error("max output tokens reached").status_code == 502
