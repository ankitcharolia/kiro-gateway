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
import shlex
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# Load .env before importing kiro.config so Option-A (bare metal) deployments
# that configure the gateway via a .env file are honoured. Existing environment
# variables always take precedence over .env values.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass

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
    logger.info(f"tool auto-approval: {'on' if settings.ACP_TRUST_TOOLS else 'off'}")
    if settings.ACP_MODE:
        logger.info(f"ACP mode (agent): {settings.ACP_MODE}")

    # Parse the optional raw-args escape hatch with shell-style quoting.
    try:
        extra_args = shlex.split(settings.ACP_EXTRA_ARGS) if settings.ACP_EXTRA_ARGS else []
    except ValueError as exc:
        logger.warning(
            f"KIRO_ACP_EXTRA_ARGS could not be parsed ({exc}); ignoring it."
        )
        extra_args = []

    logger.info(f"ACP engine: {settings.ACP_ENGINE}")
    if settings.ACP_ENGINE == "v3":
        logger.warning(
            "KIRO_ACP_ENGINE=v3 selected: the v3 engine requires host-mediated "
            "auth (_kiro/auth/getAccessToken) that the gateway does not "
            "implement, so generation will fail. See issue #52. Use v2."
        )
    if settings.ACP_AGENT:
        logger.info(f"ACP spawn agent: {settings.ACP_AGENT}")
    if settings.ACP_MODEL:
        logger.info(f"ACP initial model: {settings.ACP_MODEL}")
    if settings.ACP_EFFORT:
        logger.info(f"ACP initial effort: {settings.ACP_EFFORT}")
    if extra_args:
        logger.info(f"ACP extra args: {extra_args}")

    acp_client = ACPClient(
        command=settings.KIRO_CLI_PATH,
        trust_tools=settings.ACP_TRUST_TOOLS,
        mode=settings.ACP_MODE or None,
        agent=settings.ACP_AGENT or None,
        initial_model=settings.ACP_MODEL or None,
        effort=settings.ACP_EFFORT or None,
        engine=settings.ACP_ENGINE,
        extra_args=extra_args,
    )
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
    # Mount the Anthropic shim under every common base-URL convention so a
    # client works whether it treats the gateway root, "/v1", "/anthropic" or
    # "/anthropic/v1" as its base URL (and whether it appends "/messages" or
    # "/v1/messages"). The router itself declares relative paths.
    # Included after the OpenAI shim so the OpenAI "/v1/models" handler keeps
    # precedence on that shared path.
    for _anthropic_prefix in ("/v1", "", "/anthropic/v1", "/anthropic"):
        app.include_router(anthropic_shim_router, prefix=_anthropic_prefix)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "mode": "acp-cli-bridge", "version": APP_VERSION}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kiro Gateway — ACP-compliant proxy for kiro-cli")
    parser.add_argument(
        "-H", "--host", default=None, metavar="HOST",
        help=f"Bind address (default: SERVER_HOST env or {settings.SERVER_HOST})",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=None, metavar="PORT",
        help=f"Bind port (default: SERVER_PORT env or {settings.SERVER_PORT})",
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {APP_VERSION}")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    host = args.host or settings.SERVER_HOST
    port = args.port or settings.SERVER_PORT
    uvicorn.run("main:app", host=host, port=port, reload=False)
