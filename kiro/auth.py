"""Authentication utilities and FastAPI dependencies for the gateway.

Clients authenticate with the single gateway secret ``KIRO_GATEWAY_API_KEY``:

* OpenAI-style routes send it as ``Authorization: Bearer <key>``.
* Anthropic-style routes send it as ``x-api-key: <key>``.

The dependencies defined here are attached to the live shim completion routes
so a wrong or absent key is rejected with ``401`` before any work is done.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from kiro import config


def extract_bearer(authorization: Optional[str]) -> Optional[str]:
    """Return the token from an ``Authorization: Bearer <token>`` header.

    Args:
        authorization: Raw ``Authorization`` header value, or ``None``.

    Returns:
        The bearer token when the header is well-formed, otherwise ``None``.
    """
    if not authorization:
        return None
    parts = authorization.split(" ")
    if len(parts) == 2 and parts[0] == "Bearer":
        return parts[1]
    return None


def validate_proxy_key(token: Optional[str]) -> None:
    """Validate a presented gateway key against ``KIRO_GATEWAY_API_KEY``.

    The expected key is read from :mod:`kiro.config` at call time so runtime
    overrides (and test monkeypatching) are honoured.

    Args:
        token: The API key extracted from the request, or ``None``.

    Raises:
        HTTPException: ``401`` when the token is missing or does not match.
    """
    if not token or token != config.KIRO_GATEWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")


async def verify_openai_key(
    authorization: Optional[str] = Header(default=None),
) -> bool:
    """FastAPI dependency enforcing Bearer auth for OpenAI-style routes.

    Args:
        authorization: ``Authorization: Bearer <key>`` header value.

    Returns:
        ``True`` when the key is valid.

    Raises:
        HTTPException: ``401`` when the Bearer token is missing or invalid.
    """
    validate_proxy_key(extract_bearer(authorization))
    return True


async def verify_anthropic_key(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> bool:
    """FastAPI dependency enforcing ``x-api-key`` auth for Anthropic routes.

    Anthropic clients authenticate with the ``x-api-key`` header. An
    ``Authorization: Bearer`` header is accepted as a fallback so tools that
    only send Bearer tokens still work against the Anthropic shim.

    Args:
        x_api_key: ``x-api-key`` header value (preferred).
        authorization: ``Authorization: Bearer <key>`` header (fallback).

    Returns:
        ``True`` when the key is valid.

    Raises:
        HTTPException: ``401`` when no valid key is presented.
    """
    token = x_api_key or extract_bearer(authorization)
    validate_proxy_key(token)
    return True
