# -*- coding: utf-8 -*-
"""
Kiro Gateway — ACP-compliant entry point.

This is the new, fully compliant main entry point that routes all
requests through kiro-cli via the ACP (Agent Client Protocol) instead
of calling Kiro's internal API directly.

Architecture:
    Editor (any ACP client or OpenAI/Anthropic-compatible tool)
        ↓
    kiro-gateway (this file)
        ↓  ACP JSON-RPC over stdio
    kiro-cli (official, authorized Kiro client)
        ↓
    Kiro backend

Requirements:
    - kiro-cli must be installed and in PATH
    - User must be logged in: `kiro-cli auth login`
    - No credential files or tokens needed in .env

Usage:
    python main_acp.py
    python main_acp.py --port 9000
    uvicorn main_acp:app --port 8000
"""

import argparse
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from kiro.acp_session_manager import ACPSessionManager
from kiro.routes_openai_acp import router as openai_acp_router
from kiro.routes_anthropic_acp import router as anthropic_acp_router
from kiro.routes_acp_native import router as acp_native_router
from kiro.compliance import log_compliance_banner

APP_VERSION = "2.0.0"
APP_TITLE = "Kiro Gateway (ACP)"
APP_DESCRIPTION = (
    "ACP-compliant OpenAI/Anthropic-compatible gateway for Kiro. "
    "All requests route through kiro-cli via the official ACP protocol."
)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000


# --- Loguru setup ---
logger.remove()
logger.add(
    sys.stderr,
    level=os.getenv("LOG_LEVEL", "INFO"),
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


for _log_name in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
    _log = logging.getLogger(_log_name)
    _log.handlers = [InterceptHandler()]
    _log.propagate = False


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan: start/stop kiro-cli ACP subprocess.

    On startup:
        1. Boot kiro-cli as ACP subprocess
        2. Perform ACP initialize handshake
        3. Store ACPSessionManager in app.state

    On shutdown:
        1. Stop kiro-cli subprocess
    """
    log_compliance_banner()

    kiro_cli_cmd = os.getenv("KIRO_CLI_CMD", "kiro-cli")
    cwd = os.getenv("KIRO_CWD", os.getcwd())

    logger.info(f"Starting kiro-cli ACP session manager (cmd={kiro_cli_cmd})")

    session_manager = ACPSessionManager(
        kiro_cli_cmd=kiro_cli_cmd,
        cwd=cwd,
    )

    try:
        await session_manager.start()
    except FileNotFoundError as e:
        logger.error("")
        logger.error("=" * 64)
        logger.error("  STARTUP ERROR: kiro-cli not found")
        logger.error("=" * 64)
        logger.error(f"  {e}")
        logger.error("")
        logger.error("  Fix:")
        logger.error("    1. Install kiro-cli from https://kiro.dev/docs/cli/")
        logger.error("    2. Log in: kiro-cli auth login")
        logger.error("    3. Restart the gateway")
        logger.error("=" * 64)
        raise
    except Exception as e:
        logger.error(f"Failed to start ACP session manager: {e}")
        raise

    app.state.acp_session_manager = session_manager
    logger.info("kiro-gateway ACP mode ready — routing all requests through kiro-cli")

    yield

    logger.info("Shutting down kiro-cli ACP subprocess...")
    try:
        await session_manager.stop()
    except Exception as e:
        logger.warning(f"Error stopping ACP session manager: {e}")
    logger.info("Shutdown complete")


# --- FastAPI app ---
app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(openai_acp_router)
app.include_router(anthropic_acp_router)
app.include_router(acp_native_router)


# --- Startup banner ---
def _print_banner(host: str, port: int) -> None:
    GREEN, CYAN, WHITE, BOLD, DIM, RESET = (
        "\033[92m", "\033[96m", "\033[97m", "\033[1m", "\033[2m", "\033[0m"
    )
    display_host = "localhost" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    print()
    print(f"  {WHITE}{BOLD}👾 {APP_TITLE} v{APP_VERSION}{RESET}")
    print(f"  {DIM}All requests route through kiro-cli via ACP{RESET}")
    print()
    print(f"  {WHITE}Server:{RESET}          {GREEN}{BOLD}{url}{RESET}")
    print(f"  {DIM}OpenAI compat:   {url}/v1/chat/completions{RESET}")
    print(f"  {DIM}Anthropic compat: {url}/v1/messages{RESET}")
    print(f"  {DIM}ACP native:       {url}/acp/{RESET}")
    print(f"  {DIM}API docs:         {url}/docs{RESET}")
    print()
    print(f"  {DIM}{'─' * 52}{RESET}")
    print(f"  {WHITE}✅ Fully ACP-compliant — uses kiro-cli only{RESET}")
    print(f"  {DIM}No credential files or tokens required.{RESET}")
    print(f"  {DIM}Login with: kiro-cli auth login{RESET}")
    print(f"  {DIM}{'─' * 52}{RESET}")
    print()


# --- Entry point ---
if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description=f"{APP_TITLE}")
    parser.add_argument("-H", "--host", default=os.getenv("SERVER_HOST", DEFAULT_HOST))
    parser.add_argument("-p", "--port", type=int, default=int(os.getenv("SERVER_PORT", DEFAULT_PORT)))
    args = parser.parse_args()

    _print_banner(args.host, args.port)
    uvicorn.run("main_acp:app", host=args.host, port=args.port, reload=False)
