"""Tests for kiro.streaming_core shared streaming primitives.

Focus: ``iter_with_keepalive``, which keeps an SSE stream alive while kiro-cli
is silent (it emits no ACP notification for as long as one of its built-in tools
runs, and harness watchdogs abort a silent stream — Claude Code after 300s).
"""
from __future__ import annotations

import asyncio

import pytest

from kiro.streaming_core import KEEPALIVE, iter_with_keepalive


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------

class TestIterWithKeepaliveSuccess:
    """Keepalives are injected while idle and never alter real events."""

    async def test_injects_sentinel_only_while_idle(self):
        async def source():
            await asyncio.sleep(0.25)
            yield "a"
            yield "b"

        got = [e async for e in iter_with_keepalive(source(), 0.05)]

        assert [e for e in got if e is not KEEPALIVE] == ["a", "b"]
        assert got.count(KEEPALIVE) >= 2
        # Back-to-back events must not be padded with keepalives.
        assert got[-2:] == ["a", "b"]

    async def test_event_order_is_preserved(self):
        async def source():
            for i in range(5):
                await asyncio.sleep(0.06)
                yield i

        got = [e async for e in iter_with_keepalive(source(), 0.02)]

        assert [e for e in got if e is not KEEPALIVE] == [0, 1, 2, 3, 4]

    async def test_idle_tail_before_exhaustion_still_pings(self):
        """A turn that goes quiet after its last event still emits keepalives."""
        async def source():
            yield "only"
            await asyncio.sleep(0.25)

        got = [e async for e in iter_with_keepalive(source(), 0.05)]

        assert got[0] == "only"
        assert got.count(KEEPALIVE) >= 2

    async def test_dict_events_pass_through_unchanged(self):
        """Real events are dicts, so the sentinel can never be mistaken for one."""
        event = {"type": "text", "content": "hi"}

        async def source():
            yield event

        got = [e async for e in iter_with_keepalive(source(), 0.05)]

        assert got == [event]
        assert got[0] is event


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class TestIterWithKeepaliveErrors:
    """Failures surface to the caller rather than being swallowed."""

    async def test_source_exception_propagates(self):
        async def source():
            yield "a"
            raise RuntimeError("upstream exploded")

        collected = []
        with pytest.raises(RuntimeError, match="upstream exploded"):
            async for item in iter_with_keepalive(source(), 0.05):
                collected.append(item)

        assert collected == ["a"]

    async def test_slow_source_exception_propagates(self):
        """An error that arrives after keepalives were sent is still raised."""
        async def source():
            await asyncio.sleep(0.15)
            raise RuntimeError("late failure")
            yield  # pragma: no cover - makes this an async generator

        with pytest.raises(RuntimeError, match="late failure"):
            async for _ in iter_with_keepalive(source(), 0.05):
                pass


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestIterWithKeepaliveEdgeCases:
    """Disabling, teardown and empty sources."""

    @pytest.mark.parametrize("interval", [0, 0.0, -1])
    async def test_non_positive_interval_passes_through(self, interval):
        async def source():
            yield 1
            yield 2

        got = [e async for e in iter_with_keepalive(source(), interval)]

        assert got == [1, 2]
        assert KEEPALIVE not in got

    async def test_closes_source_on_early_exit(self):
        """Closing the wrapper must close the upstream generator.

        ``prompt_stream``'s finally-block is what tells kiro-cli to abandon the
        turn, so it has to run when the consumer stops early (client disconnect).
        """
        closed = False

        async def source():
            nonlocal closed
            try:
                yield "a"
                yield "b"
            finally:
                closed = True

        wrapped = iter_with_keepalive(source(), 0.05)
        async for _ in wrapped:
            break
        # Deterministic teardown: rely on aclose() rather than on when the event
        # loop happens to finalize the abandoned generator.
        await wrapped.aclose()

        assert closed is True

    async def test_closes_source_when_breaking_during_idle(self):
        """Teardown also works while a pull is still in flight."""
        closed = False

        async def source():
            nonlocal closed
            try:
                await asyncio.sleep(5)
                yield "never"
            finally:
                closed = True

        wrapped = iter_with_keepalive(source(), 0.05)
        async for event in wrapped:
            assert event is KEEPALIVE
            break
        await wrapped.aclose()

        assert closed is True

    async def test_teardown_during_idle_does_not_hang(self):
        """Cancelling an in-flight pull must not wait for the source to finish."""
        async def source():
            await asyncio.sleep(30)
            yield "never"

        wrapped = iter_with_keepalive(source(), 0.05)
        async for _ in wrapped:
            break

        # A pending __anext__ is cancelled rather than awaited to completion.
        await asyncio.wait_for(wrapped.aclose(), timeout=5)

    async def test_empty_source_yields_nothing(self):
        async def source():
            return
            yield  # pragma: no cover - makes this an async generator

        got = [e async for e in iter_with_keepalive(source(), 0.05)]

        assert got == []

    async def test_no_keepalive_for_fast_source(self):
        """A source that never idles must produce a byte-identical stream."""
        async def source():
            for i in range(50):
                yield i

        got = [e async for e in iter_with_keepalive(source(), 0.05)]

        assert got == list(range(50))
