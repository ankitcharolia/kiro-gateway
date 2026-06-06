"""Utilities for parsing <thinking> blocks from model output."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

_THINK_RE = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL)


@dataclass
class ParsedThinking:
    thinking: str
    remaining_text: str


def extract_thinking(text: str) -> ParsedThinking:
    """Extract the first ``<thinking>`` block from *text*.

    Returns a :class:`ParsedThinking` with the thinking content and the
    remaining text with the block removed.
    """
    m = _THINK_RE.search(text)
    if m:
        thinking = m.group(1).strip()
        remaining = (text[: m.start()] + text[m.end() :]).strip()
        return ParsedThinking(thinking=thinking, remaining_text=remaining)
    return ParsedThinking(thinking="", remaining_text=text)


def strip_thinking(text: str) -> str:
    """Remove all ``<thinking>`` … ``</thinking>`` blocks from *text*."""
    return _THINK_RE.sub("", text).strip()


def has_thinking(text: str) -> bool:
    """Return True if *text* contains at least one ``<thinking>`` block."""
    return bool(_THINK_RE.search(text))


# ---------------------------------------------------------------------------
# Class-based API (used by shim_service and tests)
# ---------------------------------------------------------------------------

class ThinkingParser:
    """Stateless wrapper around the module-level parsing functions."""

    @staticmethod
    def extract(text: str) -> ParsedThinking:
        """Alias for :func:`extract_thinking`."""
        return extract_thinking(text)

    @staticmethod
    def strip(text: str) -> str:
        """Alias for :func:`strip_thinking`."""
        return strip_thinking(text)

    @staticmethod
    def has_thinking(text: str) -> bool:
        """Alias for :func:`has_thinking`."""
        return has_thinking(text)


# ---------------------------------------------------------------------------
# Backward-compat alias expected by tests
# ---------------------------------------------------------------------------

# ThinkingParseResult -> ParsedThinking
ThinkingParseResult = ParsedThinking
