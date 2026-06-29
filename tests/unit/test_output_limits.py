"""
Unit tests for kiro.output_limits (stop / max_tokens enforcement, issue #32)
and kiro.tokenizer.truncate_to_tokens.
"""
from __future__ import annotations

import pytest

from kiro.output_limits import StreamLimiter
from kiro.tokenizer import truncate_to_tokens


class TestActive:
    def test_inactive_without_stop_or_maxtokens(self):
        assert StreamLimiter(None, None, False).active is False

    def test_inactive_when_maxtokens_not_enforced(self):
        assert StreamLimiter(None, 100, False).active is False

    def test_active_with_stop(self):
        assert StreamLimiter(["X"], None, False).active is True

    def test_active_with_enforced_maxtokens(self):
        assert StreamLimiter(None, 100, True).active is True


class TestStopSequence:
    def test_stop_within_single_chunk(self):
        lim = StreamLimiter(["STOP"], None, False)
        emit, reason = lim.feed("hello STOP world")
        assert emit == "hello "
        assert reason == "stop"

    def test_stop_split_across_chunks(self):
        lim = StreamLimiter(["STOP"], None, False)
        out = []
        for chunk in ("hel", "lo ST", "OP end"):
            emit, reason = lim.feed(chunk)
            out.append(emit)
            if reason:
                assert reason == "stop"
                break
        assert "".join(out) == "hello "

    def test_no_stop_holds_tail_then_flush(self):
        lim = StreamLimiter(["STOP"], None, False)
        emit1, r1 = lim.feed("hello wor")
        assert r1 is None
        # The last 3 chars (len('STOP')-1) are held back.
        assert emit1 == "hello "
        tail = lim.flush()
        assert emit1 + tail == "hello wor"

    def test_multiple_stops_earliest_wins(self):
        lim = StreamLimiter(["END", "STOP"], None, False)
        emit, reason = lim.feed("a STOP b END")
        assert emit == "a "
        assert reason == "stop"

    def test_feed_after_done_is_noop(self):
        lim = StreamLimiter(["STOP"], None, False)
        lim.feed("x STOP y")
        assert lim.feed("more") == ("", None)


class TestMaxTokens:
    def test_truncates_and_reports_length(self):
        lim = StreamLimiter(None, 2, True)
        emit, reason = lim.feed("one two three four five six seven")
        assert reason == "length"
        assert len(emit) < len("one two three four five six seven")

    def test_under_limit_passes_through(self):
        lim = StreamLimiter(None, 1000, True)
        emit, reason = lim.feed("short text")
        assert reason is None
        assert emit == "short text"

    def test_not_enforced_passes_through(self):
        lim = StreamLimiter(None, 1, False)
        assert lim.active is False


class TestTruncateToTokens:
    def test_under_limit_unchanged(self):
        text = "hello world"
        assert truncate_to_tokens(text, 1000) == (text, False)

    def test_over_limit_truncated(self):
        text = "one two three four five six seven eight nine ten"
        out, truncated = truncate_to_tokens(text, 3)
        assert truncated is True
        assert len(out) < len(text)
        # Re-truncating the result is stable (already within limit).
        assert truncate_to_tokens(out, 3)[1] is False

    def test_zero_or_none_limit_is_noop(self):
        assert truncate_to_tokens("abc", 0) == ("abc", False)
        assert truncate_to_tokens("abc", None) == ("abc", False)  # type: ignore[arg-type]

    def test_empty_text(self):
        assert truncate_to_tokens("", 5) == ("", False)
