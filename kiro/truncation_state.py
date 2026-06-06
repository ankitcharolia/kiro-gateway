"""Per-request state tracking for context-window truncation."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
_store: Dict[str, List[TruncationRecord]] = {}


def save_tool_truncation(
    request_id: str,
    tool_call_id: str,
    original_count: int,
    truncated_to: int,
) -> TruncationRecord:
    record = TruncationRecord(
        request_id=request_id,
        tool_call_id=tool_call_id,
        original_message_count=original_count,
        truncated_to=truncated_to,
        reason="tool_context_limit",
    )
    with _lock:
        _store.setdefault(request_id, []).append(record)
    return record


def save_content_truncation(
    request_id: str,
    content_index: int,
    original_count: int,
    truncated_to: int,
) -> TruncationRecord:
    """Record a content-block truncation event (e.g. oversized image/text block)."""
    record = TruncationRecord(
        request_id=request_id,
        content_index=content_index,
        original_message_count=original_count,
        truncated_to=truncated_to,
        reason="content_context_limit",
    )
    with _lock:
        _store.setdefault(request_id, []).append(record)
    return record


def get_truncation_records(request_id: str) -> List[TruncationRecord]:
    with _lock:
        return list(_store.get(request_id, []))


def clear_truncation_records(request_id: str) -> None:
    with _lock:
        _store.pop(request_id, None)


get_tool_truncation = get_truncation_records


def estimate_conversation_tokens(messages: List[Dict[str, Any]]) -> int:
    from .tokenizer import count_message_tokens
    return count_message_tokens(messages)


class TruncationState:
    def __init__(self, request_id: str, max_input_tokens: int = 100_000) -> None:
        self.request_id = request_id
        self.max_input_tokens = max_input_tokens
        self._records: List[TruncationRecord] = []

    def should_truncate(self, messages: List[Dict[str, Any]]) -> bool:
        return estimate_conversation_tokens(messages) > self.max_input_tokens

    def record(
        self,
        tool_call_id: str,
        original: int,
        truncated_to: int,
    ) -> TruncationRecord:
        rec = save_tool_truncation(self.request_id, tool_call_id, original, truncated_to)
        self._records.append(rec)
        return rec

    def records(self) -> List[TruncationRecord]:
        return list(self._records)


def truncate_messages(
    messages: List[Dict[str, Any]],
    max_input_tokens: int = 100_000,
) -> List[Dict[str, Any]]:
    from .payload_guards import trim_messages as _trim
    trimmed, _ = _trim(messages, max_input_tokens)
    return trimmed
