"""Anthropic-compatible shim router (re-export)."""
from __future__ import annotations

try:
    from kiro.routes_anthropic_shim import router  # noqa: F401
except Exception:  # pragma: no cover
    from fastapi import APIRouter
    router = APIRouter()

__all__ = ["router"]
