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

See COMPLIANCE.md for details.
"""

from contextlib import asynccontextmanager
import argparse
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from kiro.acp_client import ACPClient
from kiro.config import settings, APP_VERSION
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
    level="INFO",
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Kiro Gateway v{APP_VERSION} (ACP mode)...")
    logger.info(f"kiro-cli path: {settings.KIRO_CLI_PATH}")

    acp_client = ACPClient(command=settings.KIRO_CLI_PATH)
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

if settings.ACP_ENABLED:
    app.include_router(acp_router)
if settings.OPENAI_SHIM_ENABLED:
    app.include_router(openai_shim_router)
if settings.ANTHROPIC_SHIM_ENABLED:
    app.include_router(anthropic_shim_router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "mode": "acp-cli-bridge", "version": APP_VERSION}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kiro Gateway — ACP-compliant proxy for kiro-cli")
    parser.add_argument("-H", "--host", default=None, metavar="HOST")
    parser.add_argument("-p", "--port", type=int, default=None, metavar="PORT")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {APP_VERSION}")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    host = args.host or settings.SERVER_HOST
    port = args.port or settings.SERVER_PORT
    uvicorn.run("main:app", host=host, port=port, reload=False)
