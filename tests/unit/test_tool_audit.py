"""Unit tests for bounded ACP tool-execution audit state."""
from __future__ import annotations

import json

from kiro.tool_audit import ToolAuditStore


def test_audit_redacts_sensitive_values_and_caps_updates():
    """Tool arguments and output do not retain obvious credential values."""
    store = ToolAuditStore(max_updates=2, max_text=32)
    store.begin("session-1")
    store.record_tool_call(
        "session-1",
        "tool-1",
        name="execute",
        kind="execute",
        arguments={
            "api_key": "super-secret-key",
            "command": "curl -H 'Authorization: Bearer abcdefghijklmnop'",
            "nested": {"password": "also-secret"},
        },
    )
    store.record_tool_update("session-1", "tool-1", status="running", output="first")
    store.record_tool_update(
        "session-1", "tool-1", status="completed", output="Bearer qwertyuiopasdfgh"
    )
    store.record_tool_update("session-1", "tool-1", status="done", output="third")
    store.record_terminal("session-1", reason="end_turn")

    audit = store.get("session-1")
    assert audit is not None
    encoded = json.dumps(audit)
    assert "super-secret-key" not in encoded
    assert "also-secret" not in encoded
    assert "abcdefghijklmnop" not in encoded
    assert "qwertyuiopasdfgh" not in encoded
    assert audit["tools"][0]["status"] == "completed"
    assert len(audit["tools"][0]["updates"]) == 2


def test_cancel_after_tool_start_is_classified_as_race():
    """A cancelled turn records that a tool had already been observed."""
    store = ToolAuditStore()
    store.begin("session-2")
    store.record_permission_result(
        "session-2", "tool-2", allowed=True, option_id="allow_once"
    )
    store.record_tool_call("session-2", "tool-2", name="shell", kind="execute")
    store.request_cancel("session-2")
    store.record_terminal("session-2", reason="cancelled")

    audit = store.get("session-2")
    assert audit is not None
    assert audit["status"] == "cancelled_after_start"
    assert audit["tools"][0]["status"] == "cancelled_after_start"
    assert audit["tools"][0]["cancel_race"] == "cancel_after_start"


def test_cancel_before_any_tool_is_classified_separately():
    """A cancelled turn with no observed permission/tool event is pre-start."""
    store = ToolAuditStore()
    store.begin("session-3")
    store.request_cancel("session-3")
    store.record_terminal("session-3", reason="cancelled")

    audit = store.get("session-3")
    assert audit is not None
    assert audit["status"] == "cancelled_before_start"
    assert audit["tools"] == []


def test_drain_timeout_marks_side_effect_state_unknown():
    """Missing terminal evidence is explicitly classified as unknown."""
    store = ToolAuditStore()
    store.begin("session-4")
    store.record_permission_result(
        "session-4", "tool-4", allowed=True, option_id="allow_once"
    )
    store.request_cancel("session-4")
    store.mark_drain_timeout("session-4")

    audit = store.get("session-4")
    assert audit is not None
    assert audit["status"] == "unknown"
    assert audit["drain_status"] == "timeout"
    assert audit["tools"][0]["status"] == "unknown"


def test_finalized_records_expire_after_ttl():
    """Finalized audit data is removed after its configured retention window."""
    now = [100.0]
    store = ToolAuditStore(ttl_seconds=10, clock=lambda: now[0])
    store.begin("session-5")
    store.record_terminal("session-5", reason="end_turn")
    assert store.get("session-5") is not None

    now[0] = 105
    assert store.get("session-5") is not None
    now[0] = 110.1
    assert store.get("session-5") is None


def test_tool_count_and_serialized_byte_budgets_are_enforced():
    """A single noisy session cannot bypass the audit memory bounds."""
    store = ToolAuditStore(max_tools=2, max_bytes=2048, max_text=512)
    store.begin("session-6")
    for index in range(3):
        store.record_tool_call(
            "session-6",
            f"tool-{index}",
            name="execute",
            kind="execute",
            arguments={"command": "x" * 10_000},
            content=[{"type": "diff", "newText": "y" * 10_000}],
        )
    store.record_terminal("session-6", reason="end_turn")

    audit = store.get("session-6")
    assert audit is not None
    assert len(audit["tools"]) <= 2
    assert audit["evicted_tool_count"] >= 1
    assert audit["budget_truncated"] is True
    retained = sum(
        len(str(tool.get(name)))
        for tool in audit["tools"]
        for name in ("arguments", "latest_output", "latest_content")
        if tool.get(name)
    )
    assert retained < 10_000


def test_record_count_is_bounded():
    """The store evicts old finalized records when the count cap is reached."""
    store = ToolAuditStore(max_records=1)
    store.begin("session-old")
    store.record_terminal("session-old", reason="end_turn")
    store.begin("session-new")
    store.record_terminal("session-new", reason="end_turn")

    assert store.get("session-old") is None
    assert store.get("session-new") is not None
