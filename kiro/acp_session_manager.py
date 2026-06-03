# -*- coding: utf-8 -*-
"""
ACP Session Manager.

Manages kiro-cli ACP subprocess lifecycle and session pool for the gateway.
Provides a high-level async context manager for getting an ACP session.
"""

import asyncio
import os
from typing import Optional
from loguru import logger

from kiro.acp_client import KiroCLIProcess, DEFAULT_KIRO_CLI_CMD


class ACPSessionManager:
    """
    Manages a pool of kiro-cli ACP sessions.

    Architecture:
        - Maintains one kiro-cli subprocess (single-account compliance).
        - Sessions are created on-demand within that process.
        - The process is auto-restarted if it dies.
    """

    def __init__(
        self,
        kiro_cli_cmd: str = DEFAULT_KIRO_CLI_CMD,
        cwd: Optional[str] = None,
    ):
        self.kiro_cli_cmd = kiro_cli_cmd
        self.cwd = cwd or os.getcwd()
        self._process: Optional[KiroCLIProcess] = None
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        """Start the kiro-cli subprocess and perform ACP initialization."""
        async with self._lock:
            if self._started and self._process and self._process.is_alive:
                return
            await self._boot_process()
            self._started = True

    async def stop(self) -> None:
        """Stop the kiro-cli subprocess."""
        async with self._lock:
            if self._process:
                await self._process.stop()
                self._process = None
            self._started = False

    async def get_process(self) -> KiroCLIProcess:
        """
        Return the live kiro-cli process, restarting if needed.
        """
        if not self._process or not self._process.is_alive:
            async with self._lock:
                if not self._process or not self._process.is_alive:
                    logger.warning("kiro-cli process not alive — restarting")
                    await self._boot_process()
        return self._process

    async def new_session(self, cwd: Optional[str] = None) -> tuple[KiroCLIProcess, str]:
        """
        Create a new ACP session.

        Returns:
            (process, session_id) tuple.
        """
        proc = await self.get_process()
        session_id = await proc.session_new(cwd=cwd or self.cwd)
        return proc, session_id

    async def _boot_process(self) -> None:
        """Boot a fresh kiro-cli subprocess and initialize ACP."""
        if self._process:
            try:
                await self._process.stop()
            except Exception:
                pass

        proc = KiroCLIProcess(
            kiro_cli_cmd=self.kiro_cli_cmd,
            cwd=self.cwd,
        )
        await proc.start()
        await proc.initialize()
        self._process = proc
        logger.info("kiro-cli ACP process ready")
