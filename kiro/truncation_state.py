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
