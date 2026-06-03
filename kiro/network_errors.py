"""Network-level error helpers."""
from __future__ import annotations

import httpx


class NetworkError(Exception):
    """Transient network failure."""


class VpnChangeError(NetworkError):
    """Network interface changed (VPN reconnect)."""


def is_transient(exc: Exception) -> bool:
    """Return True for errors that may succeed on retry."""
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            NetworkError,
        ),
    )
