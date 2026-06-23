"""OpenAI-compatible shim router — compat re-export.

All actual request handling flows through ``routes_openai_shim``.
This module re-exports router + provides verify_api_key so legacy
imports (``from kiro.routes_openai import router, verify_api_key``)
continue to work for both application code and tests.
"""
from __future__ import annotations
from typing import Optional

from fastapi import Header, HTTPException, APIRouter

from kiro.config import APP_VERSION, KIRO_GATEWAY_API_KEY, HIDDEN_MODELS
from kiro.http_client import KiroHttpClient  # noqa: F401  (re-exported for tests)

try:
    from kiro.routes_openai_shim import router  # noqa: F401
except Exception:  # pragma: no cover
    router = APIRouter()


async def verify_api_key(
    authorization: Optional[str] = Header(default=None),
) -> bool:
    """Validate ``Authorization: Bearer <key>`` header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    token = parts[1]
    if not token or token != KIRO_GATEWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True


__all__ = ["router", "verify_api_key", "KiroHttpClient"]
