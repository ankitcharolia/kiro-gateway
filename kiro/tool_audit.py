"""Bounded and redacted audit state for ACP tool execution.

The ACP agent owns tool execution, so this module records what the gateway
observes rather than claiming to prove external side effects. Records are
kept per ACP session, capped in size, and evicted after a short TTL.
"""
from __future__ import annotations

import copy
import re
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any

_COLLAPSED = "[TRUNCATED]"

_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|credential|password|passwd|private[_-]?key|secret|token)",
    re.IGNORECASE,
)
_SECRET_TEXT = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)(\b(?:api[_-]?key|access[_-]?token|password|passwd|secret|token)\s*[:=]\s*)[^\s,'\"&]+"
    ),
    re.compile(r"(?i)(://[^/:\s]+:)[^@\s]+(@)"),
)

_ACTIVE_TOOL_STATUSES = frozenset({
    "permission_requested",
    "permission_granted",
    "started",
    "running",
})
_TERMINAL_TOOL_STATUSES = frozenset({
    "completed",
    "failed",
    "permission_denied",
    "cancelled_before_start",
    "cancelled_after_start",
    "unknown",
})
_SUCCESS_UPDATE_WORDS = frozenset({
    "complete",
    "completed",
    "done",
    "finished",
    "success",
    "succeeded",
})
_FAILURE_UPDATE_WORDS = frozenset({
    "error",
    "failed",
    "failure",
    "rejected",
})
_CANCEL_UPDATE_WORDS = frozenset({
    "abort",
    "aborted",
    "cancel",
    "cancelled",
    "canceled",
})


def _redact_text(value: str, max_chars: int) -> str:
    """Redact common credential forms and cap a text value."""
    text = value
    for pattern in _SECRET_TEXT:
        text = pattern.sub("[REDACTED]", text)
    if len(text) > max_chars:
        return text[:max_chars] + "…[TRUNCATED]"
    return text


def redact_audit_value(
    value: Any,
    *,
    max_chars: int = 2048,
    max_depth: int = 6,
) -> Any:
    """Return a bounded, best-effort redacted copy of an audit value.

    Args:
        value: Arbitrary ACP input or output data.
        max_chars: Maximum length of each retained string.
        max_depth: Maximum recursive container depth.

    Returns:
        A JSON-compatible value with sensitive key values redacted and large
        containers truncated.
    """
    if max_depth <= 0:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return _redact_text(value, max_chars)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 64:
                result["[TRUNCATED]"] = "additional fields omitted"
                break
            key_text = _redact_text(str(key), max_chars=128)
            if _SENSITIVE_KEY.search(key_text):
                result[key_text] = "[REDACTED]"
            else:
                result[key_text] = redact_audit_value(
                    item, max_chars=max_chars, max_depth=max_depth - 1
                )
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        result = [
            redact_audit_value(item, max_chars=max_chars, max_depth=max_depth - 1)
            for item in items[:64]
        ]
        if len(items) > 64:
            result.append("[TRUNCATED]")
        return result
    return _redact_text(str(value), max_chars)


def _normalise_update_status(status: str) -> str:
    """Map an ACP update status to an audit status category."""
    value = status.strip().lower().replace("-", "_").replace(" ", "_")
    if value in _SUCCESS_UPDATE_WORDS or any(
        word in value for word in ("complete", "success", "finish")
    ):
        return "completed"
    if value in _FAILURE_UPDATE_WORDS or any(
        word in value for word in ("fail", "error", "reject")
    ):
        return "failed"
    if value in _CANCEL_UPDATE_WORDS or any(
        word in value for word in ("cancel", "abort")
    ):
        return "cancelled_after_start"
    return "running" if value else "started"


class ToolAuditStore:
    """Store bounded, redacted per-session ACP tool observations.

    The store deliberately uses lazy TTL cleanup plus a maximum record count.
    Lazy cleanup avoids one background task per session while the record cap
    guarantees memory remains bounded even when the process is idle.
    """

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        max_records: int = 256,
        max_tools: int = 128,
        max_updates: int = 32,
        max_bytes: int = 1_048_576,
        max_text: int = 2048,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Initialise the audit store.

        Args:
            ttl_seconds: How long a finalized record is retained.
            max_records: Maximum number of session records retained.
            max_tools: Maximum number of tool records retained per session.
            max_updates: Maximum update entries retained per tool.
            max_bytes: Maximum serialized size of one public session record.
            max_text: Maximum length of retained text values.
            clock: Monotonic clock used by tests and TTL eviction.
        """
        self._ttl_seconds = max(float(ttl_seconds), 0.0)
        self._max_records = max(int(max_records), 1)
        self._max_tools = max(int(max_tools), 1)
        self._max_updates = max(int(max_updates), 1)
        self._max_bytes = max(int(max_bytes), 1024)
        self._max_text = max(int(max_text), 1)
        self._clock = clock or time.monotonic
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def begin(self, session_id: str) -> None:
        """Register an ACP session as active if it is not already known."""
        if not session_id:
            return
        self.cleanup()
        record = self._records.get(session_id)
        if record is None:
            now = time.time()
            record = {
                "session_id": session_id,
                "status": "running",
                "turn_count": 1,
                "cancel_requested": False,
                "cancel_requested_at": None,
                "terminal_reason": None,
                "terminal_at": None,
                "drain_status": "not_requested",
                "created_at": now,
                "updated_at": now,
                "_finalized": False,
                "_expires_at": None,
                "_tools": OrderedDict(),
            }
            self._records[session_id] = record
        elif record.get("_finalized"):
            record["turn_count"] = int(record.get("turn_count", 1)) + 1
            record["status"] = "running"
            record["cancel_requested"] = False
            record["cancel_requested_at"] = None
            record["terminal_reason"] = None
            record["terminal_at"] = None
            record["drain_status"] = "not_requested"
            record["_finalized"] = False
            record["_expires_at"] = None
        self._touch(record)
        self.cleanup()

    def record_permission_request(
        self,
        session_id: str,
        tool_id: str,
        *,
        name: str = "",
        kind: str = "",
        arguments: Any = None,
    ) -> None:
        """Record that kiro-cli asked permission for a tool invocation."""
        record = self._session(session_id)
        tool = self._tool(record, tool_id, name=name, kind=kind)
        tool["permission_requested_at"] = self._timestamp()
        if arguments is not None:
            tool["arguments"] = self._redact(arguments)
        if tool["status"] not in _TERMINAL_TOOL_STATUSES:
            tool["status"] = "permission_requested"
        self._touch(record)

    def record_permission_result(
        self,
        session_id: str,
        tool_id: str,
        *,
        allowed: bool,
        option_id: str,
    ) -> None:
        """Record the gateway's allow/reject response for a tool."""
        record = self._session(session_id)
        tool = self._tool(record, tool_id)
        tool["permission"] = "allowed" if allowed else "denied"
        tool["permission_option"] = self._redact(option_id)
        tool["permission_at"] = self._timestamp()
        if not allowed:
            tool["status"] = "permission_denied"
        elif tool["status"] not in _TERMINAL_TOOL_STATUSES:
            tool["status"] = "permission_granted"
        self._touch(record)

    def record_tool_call(
        self,
        session_id: str,
        tool_id: str,
        *,
        name: str = "",
        kind: str = "",
        arguments: Any = None,
        content: Any = None,
    ) -> None:
        """Record an ACP ``tool_call`` notification."""
        record = self._session(session_id)
        now = self._timestamp()
        tool = self._tool(record, tool_id, name=name, kind=kind)
        tool["observed_at"] = now
        if tool.get("started_at") is None:
            tool["started_at"] = now
        if record.get("cancel_requested_at") is not None:
            if tool["started_at"] <= record["cancel_requested_at"]:
                tool["cancel_race"] = "cancel_after_start"
            else:
                tool["cancel_race"] = "started_after_cancel"
        if arguments is not None:
            tool["arguments"] = self._redact(arguments)
        if content:
            tool["latest_content"] = self._redact(content)
        tool["status"] = "started"
        self._append_update(tool, {
            "type": "tool_call",
            "observed_at": now,
        })
        self._touch(record)

    def record_tool_update(
        self,
        session_id: str,
        tool_id: str,
        *,
        status: str = "",
        output: Any = None,
        content: Any = None,
    ) -> None:
        """Record an ACP ``tool_call_update`` notification."""
        record = self._session(session_id)
        now = self._timestamp()
        tool = self._tool(record, tool_id)
        if tool.get("started_at") is None:
            # An update without a preceding tool_call is still evidence that
            # execution was observed; do not classify it as pre-start.
            tool["started_at"] = now
            tool["observed_without_start"] = True
        raw_status = self._redact(status)
        classified = _normalise_update_status(status)
        if classified == "cancelled_after_start":
            tool["status"] = classified
        elif classified == "completed":
            tool["status"] = "completed"
            tool["completed_at"] = now
        elif classified == "failed":
            tool["status"] = "failed"
            tool["completed_at"] = now
        elif tool["status"] not in _TERMINAL_TOOL_STATUSES:
            tool["status"] = classified
        if output:
            tool["latest_output"] = self._redact(output)
        if content:
            tool["latest_content"] = self._redact(content)
        update: dict[str, Any] = {
            "type": "tool_call_update",
            "status": raw_status,
            "observed_at": now,
        }
        if output:
            update["output"] = self._redact(output)
        if content:
            update["content"] = self._redact(content)
        self._append_update(tool, update)
        self._touch(record)

    def request_cancel(self, session_id: str) -> None:
        """Record that the gateway requested cancellation for a session."""
        record = self._session(session_id)
        now = self._timestamp()
        if record.get("cancel_requested_at") is None:
            record["cancel_requested_at"] = now
        record["cancel_requested"] = True
        record["drain_status"] = "waiting"
        if not record.get("_finalized"):
            record["status"] = "cancel_requested"
        for tool in record["_tools"].values():
            started_at = tool.get("started_at")
            if started_at is not None:
                tool["cancel_race"] = (
                    "cancel_after_start"
                    if started_at <= record["cancel_requested_at"]
                    else "started_after_cancel"
                )
        self._touch(record)

    def record_terminal(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        error: bool = False,
    ) -> None:
        """Record the terminal ACP prompt result and classify tool races."""
        record = self._session(session_id)
        now = self._timestamp()
        normalized_reason = (reason or "").strip().lower()
        cancelled = normalized_reason in {"cancelled", "canceled", "cancel"}
        record["terminal_reason"] = self._redact(reason or ("error" if error else ""))
        record["terminal_at"] = now
        record["drain_status"] = "terminal"

        for tool in record["_tools"].values():
            status = tool.get("status", "unknown")
            started = tool.get("started_at") is not None
            permission = tool.get("permission")
            if cancelled:
                if started and status in _ACTIVE_TOOL_STATUSES:
                    tool["status"] = "cancelled_after_start"
                elif not started and permission == "allowed":
                    tool["status"] = "unknown"
                elif not started and status == "permission_requested":
                    tool["status"] = "unknown"
            elif status in _ACTIVE_TOOL_STATUSES:
                tool["status"] = "unknown"

        if cancelled:
            if any(tool.get("started_at") is not None for tool in record["_tools"].values()):
                record["status"] = "cancelled_after_start"
            elif any(tool.get("status") == "unknown" for tool in record["_tools"].values()):
                record["status"] = "unknown"
            else:
                record["status"] = "cancelled_before_start"
        elif error:
            record["status"] = (
                "failed_with_unknown_tool_state"
                if any(tool.get("status") == "unknown" for tool in record["_tools"].values())
                else "failed"
            )
        elif any(tool.get("status") == "unknown" for tool in record["_tools"].values()):
            record["status"] = "completed_with_unknown_tool_state"
        else:
            record["status"] = "completed"
        self._finalize(record)

    def mark_drain_timeout(self, session_id: str) -> None:
        """Mark a session unknown when its post-cancel terminal result did not arrive."""
        record = self._session(session_id)
        for tool in record["_tools"].values():
            if tool.get("status") in _ACTIVE_TOOL_STATUSES or tool.get("permission") == "allowed":
                tool["status"] = "unknown"
        record["status"] = "unknown"
        record["drain_status"] = "timeout"
        record["terminal_reason"] = "drain_timeout"
        record["terminal_at"] = self._timestamp()
        self._finalize(record)

    def get(self, session_id: str) -> dict[str, Any] | None:
        """Return a redacted copy of a session audit record, if retained."""
        self.cleanup()
        record = self._records.get(session_id)
        if record is None:
            return None
        return self._public(record)

    def cleanup(self) -> None:
        """Evict expired records and enforce the maximum record count."""
        now = self._clock()
        expired = [
            session_id
            for session_id, record in self._records.items()
            if record.get("_expires_at") is not None and record["_expires_at"] <= now
        ]
        for session_id in expired:
            self._records.pop(session_id, None)

        while len(self._records) > self._max_records:
            finalized = next(
                (
                    session_id
                    for session_id, record in self._records.items()
                    if record.get("_finalized")
                ),
                None,
            )
            self._records.pop(finalized or next(iter(self._records)), None)

    def _session(self, session_id: str) -> dict[str, Any]:
        """Return or create a session record without resetting finalized state."""
        if not session_id:
            raise ValueError("session_id is required")
        self.cleanup()
        record = self._records.get(session_id)
        if record is None:
            self.begin(session_id)
            record = self._records[session_id]
        return record

    def _tool(
        self,
        record: dict[str, Any],
        tool_id: str,
        *,
        name: str = "",
        kind: str = "",
    ) -> dict[str, Any]:
        """Return or create a tool record inside a session record."""
        identifier = self._redact(tool_id or "unknown-tool")
        tools: OrderedDict[str, dict[str, Any]] = record["_tools"]
        tool = tools.get(identifier)
        if tool is None:
            if len(tools) >= self._max_tools:
                tools.popitem(last=False)
                record["evicted_tool_count"] = int(
                    record.get("evicted_tool_count", 0)
                ) + 1
            tool = {
                "id": identifier,
                "name": self._redact(name),
                "kind": self._redact(kind),
                "status": "observed",
                "permission": None,
                "permission_option": None,
                "permission_requested_at": None,
                "permission_at": None,
                "arguments": {},
                "started_at": None,
                "completed_at": None,
                "cancel_race": None,
                "latest_output": None,
                "latest_content": None,
                "updates": [],
            }
            tools[identifier] = tool
        else:
            if name:
                tool["name"] = self._redact(name)
            if kind:
                tool["kind"] = self._redact(kind)
        return tool

    def _append_update(self, tool: dict[str, Any], update: dict[str, Any]) -> None:
        """Append a bounded update to a tool record."""
        updates: list[dict[str, Any]] = tool["updates"]
        updates.append(update)
        del updates[:-self._max_updates]

    def _redact(self, value: Any) -> Any:
        """Apply this store's configured text bound to a value."""
        return redact_audit_value(value, max_chars=self._max_text)

    @staticmethod
    def _timestamp() -> float:
        """Return a wall-clock timestamp for human-readable audit output."""
        return round(time.time(), 3)

    def _touch(self, record: dict[str, Any]) -> None:
        """Update timestamps, enforce size bounds, and refresh finalized TTL."""
        record["updated_at"] = self._timestamp()
        self._enforce_record_budget(record)
        if record.get("_finalized"):
            record["_expires_at"] = self._clock() + self._ttl_seconds

    def _enforce_record_budget(self, record: dict[str, Any]) -> None:
        """Trim retained payloads until the record fits its size budget.

        Uses a cheap character estimate rather than serialising the record, so
        this stays inexpensive on the per-event path.
        """
        if self._estimate_size(record) <= self._max_bytes:
            return
        record["budget_truncated"] = True
        while self._estimate_size(record) > self._max_bytes:
            # 1. Drop the oldest retained update payloads first.
            trimmed = False
            for tool in record["_tools"].values():
                updates = tool.get("updates", [])
                if updates:
                    del updates[0]
                    trimmed = True
                    break
            if trimmed:
                continue
            # 2. Collapse large per-tool payloads (idempotent: skip already
            #    collapsed fields so this cannot loop).
            for tool in record["_tools"].values():
                for name in ("arguments", "latest_output", "latest_content"):
                    value = tool.get(name)
                    if value and value != _COLLAPSED:
                        tool[name] = _COLLAPSED
                        trimmed = True
                        break
                if trimmed:
                    break
            if trimmed:
                continue
            # 3. Finally evict whole tool records, oldest first.
            if record["_tools"]:
                record["_tools"].popitem(last=False)
                record["evicted_tool_count"] = int(
                    record.get("evicted_tool_count", 0)
                ) + 1
                continue
            return

    @staticmethod
    def _estimate_size(record: dict[str, Any]) -> int:
        """Approximate the retained payload size of a record in characters."""
        total = 256
        for tool in record["_tools"].values():
            total += 256
            for name in ("arguments", "latest_output", "latest_content"):
                value = tool.get(name)
                if value:
                    total += len(str(value))
            for update in tool.get("updates", []):
                total += 64 + sum(
                    len(str(item)) for item in update.values() if item is not None
                )
        return total

    def _finalize(self, record: dict[str, Any]) -> None:
        """Mark a record finalized and start its TTL."""
        record["_finalized"] = True
        record["_expires_at"] = self._clock() + self._ttl_seconds
        self._touch(record)
        self.cleanup()

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        """Convert internal ordered records into a JSON-compatible copy."""
        public = copy.deepcopy(record)
        public.pop("_finalized", None)
        public.pop("_expires_at", None)
        tools = public.pop("_tools", OrderedDict())
        public["tools"] = list(tools.values())
        return public
