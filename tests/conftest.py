"""
Shared pytest fixtures for kiro-gateway ACP test suite.
All fixtures mock kiro-cli so tests run without a real Kiro subscription.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Minimal stub ACPClient that never spawns a subprocess
# ---------------------------------------------------------------------------

class StubACPClient:
    """Drop-in ACPClient replacement for unit tests."""

    def __init__(self):
        self.started = False
        self.initialized = False
        self._sessions: dict[str, asyncio.Queue] = {}

    async def start(self):
        self.started = True

    async def initialize(self):
        self.initialized = True

    async def stop(self):
        self.started = False

    async def create_session(self) -> str:
        sid = "test-session-001"
        self._sessions[sid] = asyncio.Queue()
        return sid

    async def prompt(self, session_id: str, messages, **kwargs) -> dict:
        return {
            "session_id": session_id,
            "content": "Hello from stub ACP",
            "finish_reason": "stop",
            "tool_calls": [],
        }

    async def prompt_stream(self, session_id: str, messages, **kwargs):
        events = [
            {"type": "text", "content": "Hello "},
            {"type": "text", "content": "world"},
            {"type": "done", "finish_reason": "stop"},
        ]
        for event in events:
            yield event

    async def close_session(self, session_id: str):
        self._sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# App fixture wired to StubACPClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def stub_acp_client() -> StubACPClient:
    return StubACPClient()


@pytest.fixture()
def app_with_stub(stub_acp_client):
    """FastAPI app with lifespan bypassed, state pre-seeded."""
    from kiro.shim_service import ShimService
    from kiro.routes_acp import router as acp_router
    from kiro.routes_openai_shim import router as openai_router
    from kiro.routes_anthropic_shim import router as anthropic_router
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(acp_router)
    app.include_router(openai_router)
    app.include_router(anthropic_router)

    shim = ShimService(stub_acp_client)
    app.state.acp_client = stub_acp_client
    app.state.shim_service = shim

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": "acp-cli-bridge", "version": "2.0.0"}

    return app


@pytest.fixture()
def sync_client(app_with_stub):
    with TestClient(app_with_stub, raise_server_exceptions=True) as c:
        yield c


@pytest_asyncio.fixture()
async def async_client(app_with_stub) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_stub), base_url="http://test"
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

PROXY_KEY = "test-proxy-key"


@pytest.fixture()
def openai_headers():
    return {"Authorization": f"Bearer {PROXY_KEY}", "Content-Type": "application/json"}


@pytest.fixture()
def anthropic_headers():
    return {"x-api-key": PROXY_KEY, "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"}
