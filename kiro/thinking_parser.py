"""Utilities for parsing and handling extended-thinking blocks."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ThinkingBlock:
    thinking: str
    signature: Optional[str] = None

    def __post_init__(self) -> None:
        if self.signature is None:
            self.signature = hashlib.sha256(self.thinking.encode()).hexdigest()[:32]


@dataclass
class ThinkingParseResult:
    """Result of extracting thinking blocks from a response."""
    thinking_blocks: List[ThinkingBlock] = field(default_factory=list)
    text_blocks: List[str] = field(default_factory=list)
    raw_content: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def has_thinking(self) -> bool:
        return len(self.thinking_blocks) > 0

    @property
    def combined_thinking(self) -> str:
        return "\n\n".join(b.thinking for b in self.thinking_blocks)

    @property
    def combined_text(self) -> str:
        return "".join(self.text_blocks)


def parse_thinking_blocks(
    content: List[Dict[str, Any]],
) -> ThinkingParseResult:
    """Extract thinking and text blocks from an Anthropic content list."""
    result = ThinkingParseResult(raw_content=list(content))
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "thinking":
            result.thinking_blocks.append(
                ThinkingBlock(
                    thinking=block.get("thinking", ""),
                    signature=block.get("signature"),
                )
            )
        elif btype == "text":
            result.text_blocks.append(block.get("text", ""))
    return result


def strip_thinking_blocks(
    content: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Return (content_without_thinking, combined_thinking_text)."""
    parsed = parse_thinking_blocks(content)
    clean = [b for b in content if isinstance(b, dict) and b.get("type") != "thinking"]
    thinking_text = parsed.combined_thinking or None
    return clean, thinking_text


class ThinkingParser:
    """Stateful parser that accumulates thinking blocks from streaming content."""

    def __init__(self) -> None:
        self._blocks: List[ThinkingBlock] = []
        self._text: List[str] = []
        self._raw: List[Dict[str, Any]] = []

    def feed_block(self, block: Dict[str, Any]) -> None:
        """Feed a single content block dict into the parser."""
        self._raw.append(block)
        btype = block.get("type", "")
        if btype == "thinking":
            self._blocks.append(
                ThinkingBlock(
                    thinking=block.get("thinking", ""),
                    signature=block.get("signature"),
                )
            )
        elif btype == "text":
            self._text.append(block.get("text", ""))

    def result(self) -> ThinkingParseResult:
        """Return the accumulated :class:`ThinkingParseResult`."""
        r = ThinkingParseResult(raw_content=list(self._raw))
        r.thinking_blocks = list(self._blocks)
        r.text_blocks = list(self._text)
        return r

    def reset(self) -> None:
        self._blocks.clear()
        self._text.clear()
        self._raw.clear()
