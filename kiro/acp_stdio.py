# -*- coding: utf-8 -*-
"""
ACP stdio proxy — thin passthrough for the ACP registry.

This module implements a minimal ACP agent that speaks JSON-RPC 2.0 over
stdin/stdout by proxying everything to ``kiro-cli acp``.  The only request
it handles locally is ``initialize``, where it returns ``authMethods``
pointing the user to ``kiro-cli login`` (terminal auth).

All other JSON-RPC traffic is forwarded verbatim to the underlying
``kiro-cli acp`` subprocess and its responses/notifications are relayed
back to stdout.

This mode exists solely to satisfy the ACP registry's auth-check validation
and allow IDEs (Zed, JetBrains, etc.) to launch kiro-gateway as a native
ACP agent.  The existing HTTP gateway functionality is completely unchanged.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import signal
import sys
from typing import TextIO

from loguru import logger

from kiro.config import settings, APP_VERSION


def _write_jsonrpc(stream: TextIO, obj: dict) -> None:
    """Write a JSON-RPC message (newline-delimited) to a stream."""
    line = json.dumps(obj, separators=(",", ":"))
    stream.write(line + "\n")
    stream.flush()


def _make_initialize_response(request_id: int | str) -> dict:
    """Build the initialize response with authMethods for the registry check.

    kiro-gateway delegates all authentication to ``kiro-cli login``, which is
    an interactive terminal-based flow.  We advertise a single ``terminal``
    auth method so the ACP registry validator accepts us.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": 1,
            "agentInfo": {
                "name": "kiro-gateway",
                "version": APP_VERSION,
            },
            "agentCapabilities": {
                "promptCapabilities": {
                    "image": True,
                    "audio": False,
                    "embeddedContext": False,
                },
            },
            "authMethods": [
                {
                    "id": "kiro-cli-login",
                    "name": "Kiro CLI Login",
                    "description": "Authenticate via kiro-cli login (interactive terminal)",
                    "type": "terminal",
                    "args": ["login"],
                    "env": {},
                },
            ],
        },
    }


async def _run_stdio_proxy() -> None:
    """Main loop: read JSON-RPC from stdin, proxy to kiro-cli acp."""
    # Resolve kiro-cli command and build args.
    cli_path = settings.KIRO_CLI_PATH
    cmd_parts = [cli_path, "acp"]

    # Apply the same spawn flags as the HTTP gateway (main.py lifespan).
    if settings.ACP_ENGINE:
        cmd_parts.extend(["--agent-engine", settings.ACP_ENGINE])
    if settings.ACP_AGENT:
        cmd_parts.extend(["--agent", settings.ACP_AGENT])
    if settings.ACP_MODEL:
        cmd_parts.extend(["--model", settings.ACP_MODEL])
    if settings.ACP_EFFORT:
        cmd_parts.extend(["--effort", settings.ACP_EFFORT])
    if settings.ACP_EXTRA_ARGS:
        try:
            cmd_parts.extend(shlex.split(settings.ACP_EXTRA_ARGS))
        except ValueError:
            pass

    logger.info(f"ACP stdio proxy starting: {' '.join(cmd_parts)}")

    # Start kiro-cli acp subprocess.
    proc = await asyncio.create_subprocess_exec(
        *cmd_parts,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    initialized = False

    async def _relay_stderr() -> None:
        """Forward kiro-cli stderr to our stderr for diagnostics."""
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            sys.stderr.write(line.decode(errors="replace"))
            sys.stderr.flush()

    async def _relay_stdout() -> None:
        """Forward kiro-cli stdout to our stdout."""
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    async def _read_stdin() -> None:
        """Read JSON-RPC from stdin and either handle locally or forward."""
        nonlocal initialized
        loop = asyncio.get_event_loop()

        while True:
            # Read a line from stdin (blocking I/O wrapped in executor).
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                # EOF — client disconnected.
                break

            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(f"Non-JSON input ignored: {line[:100]}")
                continue

            method = msg.get("method", "")
            msg_id = msg.get("id")

            # Handle initialize locally — inject our authMethods.
            if method == "initialize" and not initialized:
                initialized = True
                response = _make_initialize_response(msg_id)
                _write_jsonrpc(sys.stdout, response)

                # Also send the same initialize to kiro-cli so it sets up.
                assert proc.stdin is not None
                proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
                await proc.stdin.drain()

                # Consume kiro-cli's own initialize response (we don't relay it).
                assert proc.stdout is not None
                _kiro_resp = await proc.stdout.readline()
                continue

            # Everything else: forward to kiro-cli.
            assert proc.stdin is not None
            proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
            await proc.stdin.drain()

    # Run all three tasks concurrently.
    stderr_task = asyncio.create_task(_relay_stderr())
    stdout_task = asyncio.create_task(_relay_stdout())
    stdin_task = asyncio.create_task(_read_stdin())

    # Wait until stdin closes (client disconnects) or kiro-cli exits.
    done, pending = await asyncio.wait(
        [stdin_task, stdout_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Cleanup.
    for task in pending:
        task.cancel()
    stderr_task.cancel()

    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()


def run_acp_stdio() -> None:
    """Entry point for the ACP stdio mode.

    Runs the async proxy loop until stdin closes or kiro-cli exits.
    """
    # Suppress loguru output on stdout (ACP uses stdout for JSON-RPC).
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=False)

    # Load .env for config parity with the HTTP gateway.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    try:
        asyncio.run(_run_stdio_proxy())
    except KeyboardInterrupt:
        pass
