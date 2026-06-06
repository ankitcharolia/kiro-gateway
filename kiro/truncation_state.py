"""Per-request state tracking for context-window truncation."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TruncationRecord:
    """Metadata about a single truncation event."""
    request_id: str
    timestamp: float = field(default_factory=time.time)
    original_message_count: int = 0
    truncated_to: int = 0
    tool_call_id: Optional[str] = None
    reason: str = "context_limit"


# ---------------------------------------------------------------------------
# In-memory store (keyed by request_id)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_store: Dict[str, List[TruncationRecord]] = {}


def save_tool_truncation(
    request_id: str,
    tool_call_id: str,
    original_count: int,
    truncated_to: int,
) -> TruncationRecord:
    """Persist a tool-call truncation event and return the record."""
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


def get_truncation_records(request_id: str) -> List[TruncationRecord]:
    """Retrieve all truncation records for a given request."""
    with _lock:
        return list(_store.get(request_id, []))


def clear_truncation_records(request_id: str) -> None:
    """Remove all records for *request_id* (call after request completes)."""
    with _lock:
        _store.pop(request_id, None)


# ---------------------------------------------------------------------------
# Backward-compat additions expected by tests
# ---------------------------------------------------------------------------

# get_tool_truncation -> get_truncation_records
get_tool_truncation = get_truncation_records


def estimate_conversation_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens in a list of chat messages."""
    from .tokenizer import count_message_tokens
    return count_message_tokens(messages)


class TruncationState:
    """Stateful helper that tracks and applies truncation for a single request."""

    def __init__(self, request_id: str, max_input_tokens: int = 100_000) -> None:
        self.request_id = request_id
        self.max_input_tokens = max_input_tokens
        self._records: List[TruncationRecord] = []

    def should_truncate(self, messages: List[Dict[str, Any]]) -> bool:
        """Return True if messages exceed the token budget."""
        return estimate_conversation_tokens(messages) > self.max_input_tokens

    def record(
        self,
        tool_call_id: str,
        original: int,
        truncated_to: int,
    ) -> TruncationRecord:
        """Record a truncation event and store it."""
        rec = save_tool_truncation(
            self.request_id, tool_call_id, original, truncated_to
        )
        self._records.append(rec)
        return rec

    def records(self) -> List[TruncationRecord]:
        """Return all recorded truncation events for this request."""
        return list(self._records)


def truncate_messages(
    messages: List[Dict[str, Any]],
    max_input_tokens: int = 100_000,
) -> List[Dict[str, Any]]:
    """Trim *messages* to fit within *max_input_tokens* (drops oldest first)."""
    from .payload_guards import trim_messages as _trim
    trimmed, _ = _trim(messages, max_input_tokens)
    return trimmed
