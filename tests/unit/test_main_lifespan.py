"""Unit tests for main.py lifespan — ACP-mode startup/shutdown."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


async def _noop(self, *args, **kwargs):
    pass


@pytest.fixture
def acp_client():
    with (
        patch("kiro.acp_client.ACPClient.start", new=_noop),
        patch("kiro.acp_client.ACPClient.stop", new=_noop),
        patch("kiro.acp_client.ACPClient.initialize", new=_noop),
    ):
        yield


def test_lifespan_starts_and_stops(acp_client):
    """Lifespan context manager starts and stops without error."""
    from main import app
    with TestClient(app):
        pass  # startup + shutdown must not raise


def test_app_state_has_acp_client(acp_client):
    """After startup, app.state.acp_client is set."""
    from main import app
    with TestClient(app) as client:
        assert hasattr(client.app.state, "acp_client")


def test_app_state_has_shim_service(acp_client):
    """After startup, app.state.shim_service is set."""
    from main import app
    with TestClient(app) as client:
        assert hasattr(client.app.state, "shim_service")


def test_health_endpoint_returns_ok(acp_client):
    """Health endpoint returns status ok after startup."""
    from main import app
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
