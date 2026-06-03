"""Authentication utilities."""
from __future__ import annotations
from typing import Optional
from fastapi import HTTPException
from kiro.config import PROXY_API_KEY


def extract_bearer(authorization: Optional[str]) -> Optional[str]:
    """Return the token from 'Bearer <token>', or None."""
    if not authorization:
        return None
    parts = authorization.split(" ")
    if len(parts) == 2 and parts[0] == "Bearer":
        return parts[1]
    return None


def validate_proxy_key(token: Optional[str]) -> None:
    """Raise 401 if token is invalid."""
    if not token or token != PROXY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
