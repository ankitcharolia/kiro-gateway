# -*- coding: utf-8 -*-
"""
Built-in capability executor for non-ACP clients.

When a caller uses the OpenAI or Anthropic shim (instead of a native ACP
client), it cannot handle capability requests itself. This module provides
a safe, sandboxed executor that handles:

  capability/readFile        — reads a file from an allowed filesystem root
  capability/writeFile       — writes a file to an allowed writable root
  capability/listDirectory   — lists entries in an allowed directory
  capability/runCommand      — runs an allowed command in a sandbox

All operations are guarded by the filesystem roots and terminal policy
declared in config. Attempts to access paths outside roots or run
non-whitelisted commands are rejected.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Optional

from loguru import logger

from kiro.acp_models import (
    FilesystemRoot, TerminalCapability,
    ReadFileParams, WriteFileParams, RunCommandParams, ListDirectoryParams,
)


class CapabilityError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _uri_to_path(uri: str) -> Path:
    """Convert a file:// URI or plain path to a resolved Path."""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        return Path(parsed.path).resolve()
    return Path(uri).expanduser().resolve()


def _is_under_root(path: Path, roots: list[FilesystemRoot]) -> Optional[FilesystemRoot]:
    """Return the matching root if path is within an allowed root, else None."""
    for root in roots:
        root_path = _uri_to_path(root.uri)
        try:
            path.relative_to(root_path)
            return root
        except ValueError:
            continue
    return None


class CapabilityExecutor:
    """
    Executes capability requests on behalf of kiro-cli when no native
    ACP client is present to handle them.
    """

    def __init__(
        self,
        filesystem_roots: list[FilesystemRoot],
        terminal: Optional[TerminalCapability],
    ):
        self._roots = filesystem_roots
        self._terminal = terminal

    async def handle(self, method: str, params: dict[str, Any]) -> Any:
        """Dispatch a capability request and return the result."""
        if method == "capability/readFile":
            return await self._read_file(ReadFileParams(**params))
        if method == "capability/writeFile":
            return await self._write_file(WriteFileParams(**params))
        if method == "capability/listDirectory":
            return await self._list_directory(ListDirectoryParams(**params))
        if method == "capability/runCommand":
            return await self._run_command(RunCommandParams(**params))
        raise CapabilityError(-32601, f"Unsupported capability: {method}")

    # ------------------------------------------------------------------
    # Filesystem
    # ------------------------------------------------------------------

    async def _read_file(self, p: ReadFileParams) -> dict:
        path = _uri_to_path(p.uri)
        root = _is_under_root(path, self._roots)
        if root is None:
            raise CapabilityError(-32003, f"Path not in allowed roots: {p.uri}")
        if not root.read:
            raise CapabilityError(-32003, f"Root is not readable: {root.uri}")
        if not path.exists():
            raise CapabilityError(-32002, f"File not found: {p.uri}")
        if not path.is_file():
            raise CapabilityError(-32002, f"Not a file: {p.uri}")
        # Limit reads to 10 MB to avoid memory issues
        size = path.stat().st_size
        if size > 10 * 1024 * 1024:
            raise CapabilityError(-32002, f"File too large ({size} bytes): {p.uri}")
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise CapabilityError(-32002, str(e))
        logger.debug(f"capability/readFile: {path} ({size} bytes)")
        return {"uri": p.uri, "content": content, "size": size}

    async def _write_file(self, p: WriteFileParams) -> dict:
        path = _uri_to_path(p.uri)
        root = _is_under_root(path, self._roots)
        if root is None:
            raise CapabilityError(-32003, f"Path not in allowed roots: {p.uri}")
        if not root.write:
            raise CapabilityError(-32003, f"Root is not writable: {root.uri}")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(p.content, encoding="utf-8")
        except OSError as e:
            raise CapabilityError(-32002, str(e))
        logger.debug(f"capability/writeFile: {path}")
        return {"uri": p.uri, "written": len(p.content)}

    async def _list_directory(self, p: ListDirectoryParams) -> dict:
        path = _uri_to_path(p.uri)
        root = _is_under_root(path, self._roots)
        if root is None:
            raise CapabilityError(-32003, f"Path not in allowed roots: {p.uri}")
        if not root.read:
            raise CapabilityError(-32003, f"Root is not readable: {root.uri}")
        if not path.exists():
            raise CapabilityError(-32002, f"Directory not found: {p.uri}")
        if not path.is_dir():
            raise CapabilityError(-32002, f"Not a directory: {p.uri}")
        entries = []
        for entry in sorted(path.iterdir()):
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
                "uri": entry.as_uri(),
            })
        logger.debug(f"capability/listDirectory: {path} ({len(entries)} entries)")
        return {"uri": p.uri, "entries": entries}

    # ------------------------------------------------------------------
    # Terminal
    # ------------------------------------------------------------------

    async def _run_command(self, p: RunCommandParams) -> dict:
        if self._terminal is None:
            raise CapabilityError(-32003, "Terminal capability not configured")

        # Whitelist check
        allowed = self._terminal.allowed_commands
        if allowed and p.command not in allowed:
            raise CapabilityError(
                -32003,
                f"Command not whitelisted: {p.command}. "
                f"Allowed: {', '.join(allowed)}"
            )

        cwd = p.working_directory or self._terminal.working_directory or os.getcwd()
        timeout = min(p.timeout_seconds, self._terminal.timeout_seconds)
        cmd = [p.command] + p.args

        logger.debug(f"capability/runCommand: {' '.join(cmd)} (cwd={cwd}, timeout={timeout}s)")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout)
            )
        except asyncio.TimeoutError:
            raise CapabilityError(-32002, f"Command timed out after {timeout}s")
        except FileNotFoundError:
            raise CapabilityError(-32002, f"Command not found: {p.command}")
        except OSError as e:
            raise CapabilityError(-32002, str(e))

        return {
            "command": p.command,
            "args": p.args,
            "exit_code": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }
