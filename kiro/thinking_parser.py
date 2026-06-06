"""Utilities for parsing <thinking> blocks from model output."""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

_THINK_RE = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL)


# ---------------------------------------------------------------------------
# ParserState enum (tests import this by name)
# ---------------------------------------------------------------------------

class ParserState(enum.IntEnum):
    PRE_CONTENT = 0
    IN_THINKING = 1
    STREAMING = 2


# ---------------------------------------------------------------------------
# Simple result types
# ---------------------------------------------------------------------------

@dataclass
class ParsedThinking:
    thinking: str
    remaining_text: str


@dataclass
class ThinkingParseResult:
    """Result emitted by :class:`ThinkingParser` for each chunk processed."""
    text: str = ""
    thinking: str = ""
    state: ParserState = ParserState.PRE_CONTENT
    is_thinking_complete: bool = False


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def extract_thinking(text: str) -> ParsedThinking:
    m = _THINK_RE.search(text)
    if m:
        thinking = m.group(1).strip()
        remaining = (text[: m.start()] + text[m.end():]).strip()
        return ParsedThinking(thinking=thinking, remaining_text=remaining)
    return ParsedThinking(thinking="", remaining_text=text)


def strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


def has_thinking(text: str) -> bool:
    return bool(_THINK_RE.search(text))


# ---------------------------------------------------------------------------
# ThinkingParser FSM class
# ---------------------------------------------------------------------------

class ThinkingParser:
    """FSM-based parser for ``<thinking>`` blocks in streaming responses.

    Modes (``handling`` parameter):
    - ``"as_reasoning_content"`` — emit thinking as a separate field
    - ``"remove"`` — discard thinking blocks entirely
    - ``"pass"`` — pass the raw text through unchanged
    - ``"strip_tags"`` — emit thinking text without the XML tags
    """

    OPEN_TAG = "<thinking>"
    CLOSE_TAG = "</thinking>"

    def __init__(self, handling: str = "as_reasoning_content") -> None:
        self.handling = handling
        self.state: ParserState = ParserState.PRE_CONTENT
        self._buffer: str = ""
        self._thinking_buf: str = ""

    def feed(self, chunk: str) -> ThinkingParseResult:
        """Process *chunk* and return a :class:`ThinkingParseResult`."""
        self._buffer += chunk
        return self._process()

    def _process(self) -> ThinkingParseResult:
        result = ThinkingParseResult(state=self.state)
        buf = self._buffer
        self._buffer = ""

        if self.state == ParserState.PRE_CONTENT:
            if self.OPEN_TAG in buf:
                before, _, after = buf.partition(self.OPEN_TAG)
                if before:
                    result.text += before
                self.state = ParserState.IN_THINKING
                self._buffer = after
                inner = self._process()
                result.thinking += inner.thinking
                result.text += inner.text
                result.is_thinking_complete = inner.is_thinking_complete
                result.state = self.state
            else:
                # May be a partial open tag at end — hold in buffer
                cutoff = max(0, len(buf) - len(self.OPEN_TAG))
                result.text += buf[:cutoff]
                self._buffer = buf[cutoff:]

        elif self.state == ParserState.IN_THINKING:
            if self.CLOSE_TAG in buf:
                thinking_chunk, _, after = buf.partition(self.CLOSE_TAG)
                self._thinking_buf += thinking_chunk
                thinking_text = self._thinking_buf
                self._thinking_buf = ""
                self.state = ParserState.STREAMING

                if self.handling == "as_reasoning_content":
                    result.thinking = thinking_text
                elif self.handling == "strip_tags":
                    result.text += thinking_text
                elif self.handling == "pass":
                    result.text += self.OPEN_TAG + thinking_text + self.CLOSE_TAG
                # "remove" — discard

                result.is_thinking_complete = True
                result.state = self.state
                self._buffer = after
                tail = self._process()
                result.text += tail.text
            else:
                self._thinking_buf += buf

        elif self.state == ParserState.STREAMING:
            result.text += buf
            result.state = self.state

        return result

    def flush(self) -> ThinkingParseResult:
        """Flush any buffered data at end-of-stream."""
        result = ThinkingParseResult(state=self.state)
        if self._buffer:
            result.text += self._buffer
            self._buffer = ""
        if self._thinking_buf:
            if self.handling in ("strip_tags", "pass"):
                result.text += self._thinking_buf
            elif self.handling == "as_reasoning_content":
                result.thinking += self._thinking_buf
            self._thinking_buf = ""
        return result

    # --- Static/class helpers (backward compat) ---

    @staticmethod
    def extract(text: str) -> ParsedThinking:
        return extract_thinking(text)

    @staticmethod
    def strip(text: str) -> str:
        return strip_thinking(text)

    @staticmethod
    def has_thinking(text: str) -> bool:
        return has_thinking(text)
