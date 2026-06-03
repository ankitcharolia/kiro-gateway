"""In-memory cache for truncation detection state."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolTruncationEntry:
    tool_call_id: str
    tool_name: str
    truncation_info: dict[str, Any]


@dataclass
class ContentTruncationEntry:
    message_hash: str
    truncation_info: dict[str, Any] = field(default_factory=dict)


_tool_truncations: dict[str, ToolTruncationEntry] = {}
_content_truncations: dict[str, ContentTruncationEntry] = {}


def _content_hash(content: str) -> str:
    return hashlib.sha256(content[:500].encode()).hexdigest()[:16]


def save_tool_truncation(
    tool_call_id: str,
    tool_name: str,
    truncation_info: dict[str, Any],
) -> None:
    _tool_truncations[tool_call_id] = ToolTruncationEntry(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        truncation_info=truncation_info,
    )


def get_tool_truncation(tool_call_id: str) -> Optional[ToolTruncationEntry]:
    return _tool_truncations.pop(tool_call_id, None)


def save_content_truncation(
    content: str,
    truncation_info: Optional[dict[str, Any]] = None,
) -> str:
    h = _content_hash(content)
    _content_truncations[h] = ContentTruncationEntry(
        message_hash=h,
        truncation_info=truncation_info or {},
    )
    return h


def get_content_truncation(content: str) -> Optional[ContentTruncationEntry]:
    h = _content_hash(content)
    return _content_truncations.get(h)


def clear_all() -> None:
    _tool_truncations.clear()
    _content_truncations.clear()


def get_cache_stats() -> dict[str, int]:
    return {
        "tool_truncations": len(_tool_truncations),
        "content_truncations": len(_content_truncations),
    }
