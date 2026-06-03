"""Parse <thinking>...</thinking> blocks emitted by extended thinking models."""
from __future__ import annotations
import re

_THINKING_RE = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL)


def extract_thinking(text: str) -> tuple[str, str]:
    """Return (thinking_content, remainder) stripping thinking tags."""
    thoughts: list[str] = []
    remainder = _THINKING_RE.sub(lambda m: thoughts.append(m.group(1)) or "", text)
    return "\n".join(thoughts).strip(), remainder.strip()


def has_thinking(text: str) -> bool:
    return bool(_THINKING_RE.search(text))
