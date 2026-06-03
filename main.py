# -*- coding: utf-8 -*-
"""
Kiro Gateway — ACP-compliant entrypoint.

All AI completions route through `kiro-cli` via ACP (Agent Client Protocol),
the officially approved integration path. This gateway never touches Kiro
credentials or internal APIs directly.

Architecture:
    Cursor / Cline / Claude Code / Zed / JetBrains
            ↓  OpenAI / Anthropic / ACP native
        kiro-gateway  (this file)
            ↓  ACP JSON-RPC over stdio
        kiro-cli  (official Kiro client)
            ↓
        Kiro Backend

See COMPLIANCE.md and README_ACP.md for details.
"""

from contextlib import asynccontextmanager
import argparse
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from kiro.acp_client import ACPClient
from kiro.config import settings
from kiro.routes_acp import router as acp_router
from kiro.routes_openai_shim import router as openai_shim_router
from kiro.routes_anthropic_shim import router as anthropic_shim_router
from kiro.shim_service import ShimService


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger.remove()
logger.add(
    sys.stderr,
    level=settings.LOG_LEVEL,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Starts kiro-cli ACP subprocess on startup; tears it down on shutdown.
    The gateway never reads or writes Kiro credentials — that is entirely
    managed by kiro-cli.
    """
    logger.info("Starting Kiro Gateway (ACP mode)...")
    logger.info(f"kiro-cli command: {settings.KIRO_CLI_COMMAND}")

    acp_client = ACPClient(command=settings.KIRO_CLI_COMMAND)
    await acp_client.start()
    await acp_client.initialize()

    app.state.acp_client = acp_client
    app.state.shim_service = ShimService(acp_client)

    logger.info("ACP session manager ready. Gateway is serving requests.")
    yield

    logger.info("Shutting down gateway...")
    await acp_client.stop()
    logger.info("kiro-cli subprocess stopped.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Kiro Gateway",
    description=(
        "ACP-compliant gateway for Kiro CLI.\n\n"
        "Routes all completions through `kiro-cli` via the Agent Client Protocol (ACP). "
        "Optional OpenAI and Anthropic shims allow tools that cannot speak ACP natively "
        "to use their familiar APIs."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Feature-flagged routers — disable any shim you don't need in .env
if settings.ACP_ENABLED:
    app.include_router(acp_router)
if settings.OPENAI_SHIM_ENABLED:
    app.include_router(openai_shim_router)
if settings.ANTHROPIC_SHIM_ENABLED:
    app.include_router(anthropic_shim_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health():
    """Returns gateway health and operating mode."""
    return {"status": "ok", "mode": "acp-cli-bridge", "version": "2.0.0"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kiro Gateway — ACP-compliant proxy for kiro-cli",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # defaults: 0.0.0.0:8000
  python main.py --port 9000
  python main.py --host 127.0.0.1 --port 9000
  uvicorn main:app --port 9000      # via uvicorn directly
        """
    )
    parser.add_argument("-H", "--host", default=None, metavar="HOST",
                        help=f"Bind address (default: {settings.SERVER_HOST}, env: SERVER_HOST)")
    parser.add_argument("-p", "--port", type=int, default=None, metavar="PORT",
                        help=f"Listen port (default: {settings.SERVER_PORT}, env: SERVER_PORT)")
    parser.add_argument("-v", "--version", action="version", version="%(prog)s 2.0.0")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    host = args.host or settings.SERVER_HOST
    port = args.port or settings.SERVER_PORT

    print()
    print(f"  \033[1m\033[97m👻 Kiro Gateway v2.0.0 (ACP mode)\033[0m")
    print(f"  \033[2mAll completions route through kiro-cli — ToS compliant.\033[0m")
    print()
    print(f"  \033[97mServer: \033[92m\033[1mhttp://{'localhost' if host == '0.0.0.0' else host}:{port}\033[0m")
    print(f"  \033[2mDocs:   http://{'localhost' if host == '0.0.0.0' else host}:{port}/docs\033[0m")
    print()

    uvicorn.run("main:app", host=host, port=port, reload=False)
