"""
Unit tests for CapabilityExecutor — ACP capability dispatch.
Tests use the public handle() method to verify dispatch behaviour.
"""
from __future__ import annotations

import pytest

from kiro.capability_executor import CapabilityError, CapabilityExecutor


@pytest.fixture
def executor():
    return CapabilityExecutor(filesystem_roots=[], terminal=None)


# ---------------------------------------------------------------------------
# handle() dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_unknown_method_raises(executor):
    """handle() raises CapabilityError for unknown methods."""
    with pytest.raises(CapabilityError, match="Unknown capability method"):
        await executor.handle("doesNotExist", {})


@pytest.mark.asyncio
async def test_handle_read_file_raises_capability_error(executor):
    """readFile raises CapabilityError (stub implementation)."""
    with pytest.raises(CapabilityError):
        await executor.handle("readFile", {"path": "/tmp/x"})


@pytest.mark.asyncio
async def test_handle_write_file_raises_capability_error(executor):
    """writeFile raises CapabilityError (stub implementation)."""
    with pytest.raises(CapabilityError):
        await executor.handle("writeFile", {"path": "/tmp/x", "content": "hi"})


@pytest.mark.asyncio
async def test_handle_list_directory_raises_capability_error(executor):
    """listDirectory raises CapabilityError (stub implementation)."""
    with pytest.raises(CapabilityError):
        await executor.handle("listDirectory", {"path": "/tmp"})


@pytest.mark.asyncio
async def test_handle_run_command_raises_capability_error(executor):
    """runCommand raises CapabilityError (stub implementation)."""
    with pytest.raises(CapabilityError):
        await executor.handle("runCommand", {"command": "echo", "args": []})


# ---------------------------------------------------------------------------
# execute_tool_call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_tool_call_returns_result(executor):
    """execute_tool_call returns a tool_result dict."""
    result = await executor.execute_tool_call("my_tool", {"key": "val"}, "call_123")
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "call_123"


# ---------------------------------------------------------------------------
# CapabilityError
# ---------------------------------------------------------------------------

def test_capability_error_default_code():
    err = CapabilityError("bad")
    assert err.code == -32000


def test_capability_error_custom_code():
    err = CapabilityError("not found", code=-32601)
    assert err.code == -32601
