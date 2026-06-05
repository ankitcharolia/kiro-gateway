"""Extract and inject extended-thinking blocks in ACP / Anthropic payloads."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .acp_models import ACPContentBlock, ACPTextBlock, ACPThinkingBlock

# Matches <thinking>...</thinking> produced by some Kiro builds
_THINKING_RE = re.compile(
    r"<thinking>(.*?)</thinking>",
    re.DOTALL,
)
# Matches generic <thinking>...</thinking>
_THINKING_GENERIC_RE = re.compile(
    r"<thinking>(.*?)</thinking>",
    re.DOTALL,
)


def extract_thinking_from_text(text: str) -> Tuple[Optional[str], str]:
    """
    Strip thinking XML tags from a raw text response.

    Returns:
        (thinking_content, cleaned_text)
    """
    thinking_parts: List[str] = []

    def _collect(m: re.Match) -> str:
        thinking_parts.append(m.group(1).strip())
        return ""

    cleaned = _THINKING_RE.sub(_collect, text)
    cleaned = _THINKING_GENERIC_RE.sub(_collect, cleaned)
    cleaned = cleaned.strip()
    thinking = "\n".join(thinking_parts) if thinking_parts else None
    return thinking, cleaned


def split_content_blocks(
    blocks: List[ACPContentBlock],
) -> Tuple[List[ACPThinkingBlock], List[ACPContentBlock]]:
    """Separate thinking blocks from all other content blocks."""
    thinking: List[ACPThinkingBlock] = []
    rest: List[ACPContentBlock] = []
    for b in blocks:
        if getattr(b, "type", None) == "thinking":
            thinking.append(b)  # type: ignore[arg-type]
        else:
            rest.append(b)
    return thinking, rest


def inject_thinking_block(
    blocks: List[ACPContentBlock],
    thinking_text: str,
    signature: Optional[str] = None,
) -> List[ACPContentBlock]:
    """Prepend a thinking block to a content block list."""
    tb = ACPThinkingBlock(type="thinking", thinking=thinking_text, signature=signature)
    return [tb, *blocks]


def needs_thinking_stripping(raw_text: str) -> bool:
    """Quick check whether raw_text contains any thinking XML tags."""
    return bool(_THINKING_RE.search(raw_text) or _THINKING_GENERIC_RE.search(raw_text))
