"""Anthropic-compatible shim router with auth helper."""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from .config import PROXY_API_KEY

try:
    from kiro.routes_anthropic_shim import router  # noqa: F401
except Exception:  # pragma: no cover
    from fastapi import APIRouter
    router = APIRouter()


async def verify_anthropic_api_key(
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
    authorization: Optional[str] = Header(None),
) -> bool:
    """FastAPI dependency that validates the Anthropic API key header.

    Accepts the key either as ``x-api-key`` or as a Bearer token in
    ``Authorization``.

    Raises :class:`fastapi.HTTPException` 401 when no valid key is present.
    """
    # Extract bearer token from Authorization header if present
    bearer: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[len("bearer "):].strip()

    provided = x_api_key or bearer

    if not provided:
        raise HTTPException(status_code=401, detail="Missing API key")

    if PROXY_API_KEY and provided != PROXY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True


__all__ = ["router", "verify_anthropic_api_key"]
