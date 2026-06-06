"""Anthropic-compatible shim router."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


async def verify_anthropic_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> str:
    """Validate the Bearer token on Anthropic-compatible endpoints.

    Returns the raw token string on success.
    Raises 401 if no / invalid credentials are provided.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Anthropic API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


try:
    from kiro.routes_anthropic_shim import router  # noqa: F401
except Exception:  # pragma: no cover
    router = APIRouter()

__all__ = ["router", "verify_anthropic_api_key"]
