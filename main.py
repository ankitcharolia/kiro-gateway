# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kiro.acp_client import ACPClient
from kiro.config import settings
from kiro.routes_acp import router as acp_router
from kiro.routes_openai_shim import router as openai_shim_router
from kiro.routes_anthropic_shim import router as anthropic_shim_router
from kiro.shim_service import ShimService


@asynccontextmanager
async def lifespan(app: FastAPI):
    acp_client = ACPClient(command=settings.KIRO_CLI_COMMAND)
    await acp_client.start()
    await acp_client.initialize()
    app.state.acp_client = acp_client
    app.state.shim_service = ShimService(acp_client)
    yield
    await acp_client.stop()


app = FastAPI(
    title="Kiro Gateway",
    description="ACP-compliant gateway for Kiro CLI with optional OpenAI and Anthropic shims",
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

if settings.ACP_ENABLED:
    app.include_router(acp_router)
if settings.OPENAI_SHIM_ENABLED:
    app.include_router(openai_shim_router)
if settings.ANTHROPIC_SHIM_ENABLED:
    app.include_router(anthropic_shim_router)


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "acp-cli-bridge"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.SERVER_HOST, port=settings.SERVER_PORT, reload=False)
