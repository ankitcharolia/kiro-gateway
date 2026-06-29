# -*- coding: utf-8 -*-
"""
Output-stream limiting: gateway-side ``stop`` and ``max_tokens`` enforcement.

kiro-cli does not honor ``stop`` sequences or ``max_tokens`` over ACP (it
advertises no sampling capability — issue #32). These are output-shaping
controls the gateway *can* apply itself by watching the generated text stream:

* **stop sequences** — when a stop string appears in the output, emit up to it
  and finish with ``finish_reason="stop"``. Always active when the client
  supplies ``stop`` (it is an explicit request).
* **max_tokens** — cap the cumulative output at the requested token count and
  finish with ``finish_reason="length"``. Opt-in via ``ENFORCE_MAX_TOKENS``
  (default off) since it truncates output and Anthropic always sends a
  ``max_tokens``.

:class:`StreamLimiter` is fed text deltas and returns the slice to emit now plus
an optional terminal ``finish_reason``. A short tail (``longest_stop - 1`` chars)
is held back between deltas so a stop sequence split across chunk boundaries is
still caught; :meth:`flush` releases it at natural end. Sampling parameters
(``temperature`` / ``top_p`` / ``top_k``) cannot be enforced post-hoc and are
out of scope here.
"""
from __future__ import annotations

from typing import Optional

from kiro.tokenizer import truncate_to_tokens


class StreamLimiter:
    """Enforce ``stop`` sequences and an optional ``max_tokens`` cap on text."""

    def __init__(
        self,
        stop: Optional[list[str]],
        max_tokens: Optional[int],
        enforce_max_tokens: bool,
    ):
        """Build a limiter.

        Args:
            stop: Stop sequences supplied by the client (enforced when present).
            max_tokens: The requested output-token cap.
            enforce_max_tokens: Whether to act on *max_tokens* (else ignored).
        """
        self._stops = [s for s in (stop or []) if s]
        self._max_tokens = (
            max_tokens if (enforce_max_tokens and max_tokens and max_tokens > 0) else None
        )
        self._tail_keep = (max(len(s) for s in self._stops) - 1) if self._stops else 0
        self._buffer = ""   # received-but-not-yet-emitted text (held tail)
        self._emitted = ""  # everything emitted so far (for token counting)
        self._done = False

    @property
    def active(self) -> bool:
        """Whether any limit is in effect (else the caller should no-op)."""
        return bool(self._stops) or self._max_tokens is not None

    def feed(self, chunk: str) -> tuple[str, Optional[str]]:
        """Process an output text *chunk*.

        Args:
            chunk: The next text delta from the model.

        Returns:
            ``(emit, finish_reason)`` — *emit* is the text to forward now (may be
            empty while a tail is held back); *finish_reason* is ``"stop"`` /
            ``"length"`` when a limit was hit (the caller should then terminate
            the turn), else ``None``.
        """
        if self._done or not chunk:
            return "", None
        self._buffer += chunk

        # 1) Stop sequence: earliest occurrence anywhere in the held buffer.
        cut: Optional[int] = None
        for s in self._stops:
            idx = self._buffer.find(s)
            if idx != -1 and (cut is None or idx < cut):
                cut = idx
        if cut is not None:
            emit = self._buffer[:cut]
            self._buffer = ""
            self._done = True
            self._emitted += emit
            return emit, "stop"

        # 2) Emit everything except the held tail so a stop split across deltas
        #    can still be matched next time.
        if self._tail_keep:
            if len(self._buffer) > self._tail_keep:
                emit = self._buffer[: -self._tail_keep]
                self._buffer = self._buffer[-self._tail_keep:]
            else:
                emit = ""  # whole buffer is within the held tail
        else:
            emit = self._buffer
            self._buffer = ""

        # 3) max_tokens cap on the cumulative emitted text.
        if self._max_tokens is not None and emit:
            combined = self._emitted + emit
            capped, truncated = truncate_to_tokens(combined, self._max_tokens)
            if truncated:
                emit = capped[len(self._emitted):]
                self._buffer = ""
                self._done = True
                self._emitted = capped
                return emit, "length"

        self._emitted += emit
        return emit, None

    def flush(self) -> str:
        """Release any held-back tail at natural end (no limit hit).

        Returns:
            The remaining buffered text (empty when a limit already terminated
            the stream).
        """
        if self._done:
            return ""
        emit = self._buffer
        self._buffer = ""
        self._emitted += emit
        return emit
