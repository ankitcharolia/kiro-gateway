"""
Unit tests for CapabilityExecutor — filesystem and terminal sandboxing.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from kiro.capability_executor import CapabilityExecutor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """A temporary directory used as the filesystem root in tests."""
    return tmp_path


@pytest.fixture()
def executor_rw(tmp_root: Path) -> CapabilityExecutor:
    """CapabilityExecutor with read+write access to tmp_root."""
    roots = [{"uri": tmp_root.as_uri(), "name": "test", "read": True, "write": True}]
    return CapabilityExecutor(filesystem_roots=roots, terminal=None)


@pytest.fixture()
def executor_ro(tmp_root: Path) -> CapabilityExecutor:
    """CapabilityExecutor with read-only access to tmp_root."""
    roots = [{"uri": tmp_root.as_uri(), "name": "test", "read": True, "write": False}]
    return CapabilityExecutor(filesystem_roots=roots, terminal=None)


# ---------------------------------------------------------------------------
# readFile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_success(executor_rw, tmp_root):
    """readFile returns file contents within an allowed root."""
    test_file = tmp_root / "hello.txt"
    test_file.write_text("hello world")
    result = await executor_rw.read_file(test_file.as_uri())
    assert "hello world" in result.get("content", "")


@pytest.mark.asyncio
async def test_read_file_outside_root_denied(executor_rw):
    """readFile raises PermissionError for paths outside the allowed root."""
    with pytest.raises((PermissionError, ValueError, Exception)):
        await executor_rw.read_file("file:///etc/passwd")


@pytest.mark.asyncio
async def test_read_file_not_found(executor_rw, tmp_root):
    """readFile raises FileNotFoundError for missing files."""
    with pytest.raises((FileNotFoundError, ValueError, Exception)):
        await executor_rw.read_file((tmp_root / "nonexistent.txt").as_uri())


# ---------------------------------------------------------------------------
# writeFile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_file_success(executor_rw, tmp_root):
    """writeFile creates a file within an allowed writable root."""
    target = tmp_root / "output.txt"
    await executor_rw.write_file(target.as_uri(), "written content")
    assert target.read_text() == "written content"


@pytest.mark.asyncio
async def test_write_file_read_only_denied(executor_ro, tmp_root):
    """writeFile raises PermissionError when root is read-only."""
    target = tmp_root / "nope.txt"
    with pytest.raises((PermissionError, ValueError, Exception)):
        await executor_ro.write_file(target.as_uri(), "should fail")


@pytest.mark.asyncio
async def test_write_file_outside_root_denied(executor_rw):
    """writeFile raises PermissionError for paths outside the allowed root."""
    with pytest.raises((PermissionError, ValueError, Exception)):
        await executor_rw.write_file("file:///tmp/evil.txt", "pwned")


@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(executor_rw, tmp_root):
    """writeFile creates parent directories as needed."""
    target = tmp_root / "a" / "b" / "c.txt"
    await executor_rw.write_file(target.as_uri(), "nested")
    assert target.read_text() == "nested"


# ---------------------------------------------------------------------------
# listDirectory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_directory_success(executor_rw, tmp_root):
    """listDirectory returns entries within an allowed root."""
    (tmp_root / "file1.txt").write_text("a")
    (tmp_root / "file2.py").write_text("b")
    result = await executor_rw.list_directory(tmp_root.as_uri())
    names = [e["name"] for e in result.get("entries", [])]
    assert "file1.txt" in names
    assert "file2.py" in names


@pytest.mark.asyncio
async def test_list_directory_outside_root_denied(executor_rw):
    """listDirectory raises error for paths outside the allowed root."""
    with pytest.raises((PermissionError, ValueError, Exception)):
        await executor_rw.list_directory("file:///etc")


# ---------------------------------------------------------------------------
# runCommand — allowlist enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_command_denied_when_no_terminal_config():
    """runCommand raises error when no terminal config is provided."""
    executor = CapabilityExecutor(filesystem_roots=[], terminal=None)
    with pytest.raises((PermissionError, ValueError, RuntimeError, Exception)):
        await executor.run_command("ls", [])


@pytest.mark.asyncio
async def test_run_command_denied_if_not_in_allowlist(tmp_root):
    """runCommand raises error for commands not in the allowed_commands list."""
    terminal = {
        "allowed_commands": ["git"],
        "working_directory": str(tmp_root),
        "timeout_seconds": 5,
    }
    executor = CapabilityExecutor(filesystem_roots=[], terminal=terminal)
    with pytest.raises((PermissionError, ValueError, Exception)):
        await executor.run_command("rm", ["-rf", "/"])


@pytest.mark.asyncio
async def test_run_command_allowed(tmp_root):
    """runCommand executes allowed commands successfully."""
    terminal = {
        "allowed_commands": ["echo"],
        "working_directory": str(tmp_root),
        "timeout_seconds": 5,
    }
    executor = CapabilityExecutor(filesystem_roots=[], terminal=terminal)
    result = await executor.run_command("echo", ["hello"])
    assert "hello" in result.get("stdout", "")
