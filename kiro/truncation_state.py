"""Per-request state tracking for context-window truncation."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ToolTruncationInfo:
    request_id: str
    tool_call_id: str
    original_message_count: int
    truncated_to: int
    timestamp: float = field(default_factory=time.time)
    reason: str = "tool_context_limit"


@dataclass
class ContentTruncationInfo:
    request_id: str
    content_index: int
    original_message_count: int
    truncated_to: int
    timestamp: float = field(default_factory=time.time)
    reason: str = "content_context_limit"


@dataclass
class TruncationRecord:
    request_id: str
    timestamp: float = field(default_factory=time.time)
    original_message_count: int = 0
    truncated_to: int = 0
    tool_call_id: Optional[str] = None
    content_index: Optional[int] = None
    reason: str = "context_limit"


_lock = threading.Lock()
_tool_truncation_cache: Dict[str, List[ToolTruncationInfo]] = {}
_content_truncation_cache: Dict[str, List[ContentTruncationInfo]] = {}
_store: Dict[str, List[TruncationRecord]] = {}


def save_tool_truncation(
    request_id: str,
    tool_call_id: str,
    original_count: int,
    truncated_to: int,
) -> ToolTruncationInfo:
    info = ToolTruncationInfo(
        request_id=request_id,
        tool_call_id=tool_call_id,
        original_message_count=original_count,
        truncated_to=truncated_to,
    )
    with _lock:
        _tool_truncation_cache.setdefault(request_id, []).append(info)
        _store.setdefault(request_id, []).append(
            TruncationRecord(
                request_id=request_id,
                tool_call_id=tool_call_id,
                original_message_count=original_count,
                truncated_to=truncated_to,
                reason="tool_context_limit",
            )
        )
    return info


def save_content_truncation(
    request_id: str,
    content_index: int,
    original_count: int,
    truncated_to: int,
) -> ContentTruncationInfo:
    info = ContentTruncationInfo(
        request_id=request_id,
        content_index=content_index,
        original_message_count=original_count,
        truncated_to=truncated_to,
    )
    with _lock:
        _content_truncation_cache.setdefault(request_id, []).append(info)
        _store.setdefault(request_id, []).append(
            TruncationRecord(
                request_id=request_id,
                content_index=content_index,
                original_message_count=original_count,
                truncated_to=truncated_to,
                reason="content_context_limit",
            )
        )
    return info


def get_tool_truncation(request_id: str) -> List[ToolTruncationInfo]:
    """Return all ToolTruncationInfo records for *request_id*."""
    with _lock:
        return list(_tool_truncation_cache.get(request_id, []))


def get_content_truncation(request_id: str) -> List[ContentTruncationInfo]:
    """Return all ContentTruncationInfo records for *request_id*."""
    with _lock:
        return list(_content_truncation_cache.get(request_id, []))


def get_cache_stats() -> Dict[str, int]:
    with _lock:
        return {
            "tool_entries": sum(len(v) for v in _tool_truncation_cache.values()),
            "content_entries": sum(len(v) for v in _content_truncation_cache.values()),
            "request_ids": len(_tool_truncation_cache) + len(_content_truncation_cache),
        }


def get_truncation_records(request_id: str) -> List[TruncationRecord]:
    with _lock:
        return list(_store.get(request_id, []))


def clear_truncation_records(request_id: str) -> None:
    with _lock:
        _store.pop(request_id, None)
        _tool_truncation_cache.pop(request_id, None)
        _content_truncation_cache.pop(request_id, None)


def estimate_conversation_tokens(messages: List[Dict[str, Any]]) -> int:
    from .tokenizer import count_message_tokens
    return count_message_tokens(messages)


class TruncationState:
    def __init__(self, request_id: str, max_input_tokens: int = 100_000) -> None:
        self.request_id = request_id
        self.max_input_tokens = max_input_tokens
        self._records: List[TruncationRecord] = []

    def record(
        self,
        original_count: int,
        truncated_to: int,
        tool_call_id: Optional[str] = None,
        content_index: Optional[int] = None,
        reason: str = "context_limit",
    ) -> TruncationRecord:
        rec = TruncationRecord(
            request_id=self.request_id,
            original_message_count=original_count,
            truncated_to=truncated_to,
            tool_call_id=tool_call_id,
            content_index=content_index,
            reason=reason,
        )
        self._records.append(rec)
        return rec

    @property
    def records(self) -> List[TruncationRecord]:
        return list(self._records)


def truncate_messages(
    messages: List[Dict[str, Any]],
    max_tokens: int = 100_000,
) -> Tuple[List[Dict[str, Any]], int]:
    """Drop oldest messages until the estimated token count fits *max_tokens*.

    Returns (trimmed_messages, estimated_tokens).
    """
    from .tokenizer import count_message_tokens

    result = list(messages)
    while result and count_message_tokens(result) > max_tokens:
        if len(result) > 1 and result[0].get("role") == "system":
            result.pop(1)
        else:
            result.pop(0)
    return result, count_message_tokens(result)
