"""Network-level error classification with detailed diagnostics."""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx


class NetworkError(Exception):
    """Transient network failure."""


class VpnChangeError(NetworkError):
    """Network interface changed (VPN reconnect)."""


class ErrorCategory(str, Enum):
    DNS_RESOLUTION = "dns_resolution"
    CONNECTION_REFUSED = "connection_refused"
    CONNECTION_RESET = "connection_reset"
    CONNECTION_TIMEOUT = "connection_timeout"
    NETWORK_UNREACHABLE = "network_unreachable"
    SSL_ERROR = "ssl_error"
    PROXY_ERROR = "proxy_error"
    TRANSIENT = "transient"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    FATAL = "fatal"
    UNKNOWN = "unknown"


@dataclass
class NetworkErrorInfo:
    category: ErrorCategory
    user_message: str
    technical_details: str
    is_retryable: bool
    suggested_http_code: int = 502
    troubleshooting_steps: list[str] = field(default_factory=list)
    original: Optional[Exception] = None

    @property
    def message(self) -> str:
        return self.user_message

    @property
    def retryable(self) -> bool:
        return self.is_retryable


def _tech(exc: Exception) -> str:
    return str(exc)


def classify_network_error(exc: Exception) -> NetworkErrorInfo:  # noqa: C901
    msg = str(exc).lower()

    if isinstance(exc, httpx.ConnectError):
        cause = exc.__cause__
        if isinstance(cause, socket.gaierror):
            errno_val = cause.args[0] if cause.args else 0
            return NetworkErrorInfo(
                category=ErrorCategory.DNS_RESOLUTION,
                user_message=(
                    f"DNS resolution failed: cannot resolve the server hostname. "
                    f"(errno {errno_val})"
                ),
                technical_details=f"socket.gaierror errno={errno_val}: {cause}",
                is_retryable=True,
                suggested_http_code=502,
                troubleshooting_steps=[
                    "Check your DNS settings (try 8.8.8.8 or 1.1.1.1).",
                    "Verify the hostname is correct.",
                    "Disable VPN temporarily and retry.",
                    "Check firewall / antivirus settings.",
                    f"Technical detail: errno {errno_val}",
                ],
                original=exc,
            )

        if "connection refused" in msg or "econnrefused" in msg:
            return NetworkErrorInfo(
                category=ErrorCategory.CONNECTION_REFUSED,
                user_message="Connection refused — the server is not accepting connections.",
                technical_details=_tech(exc),
                is_retryable=True,
                suggested_http_code=502,
                troubleshooting_steps=[
                    "Verify the kiro CLI is running.",
                    "Check the port is correct.",
                    "Inspect firewall rules.",
                ],
                original=exc,
            )

        if "connection reset" in msg or "econnreset" in msg:
            return NetworkErrorInfo(
                category=ErrorCategory.CONNECTION_RESET,
                user_message="Connection reset — the server closed the connection unexpectedly.",
                technical_details=_tech(exc),
                is_retryable=True,
                suggested_http_code=502,
                troubleshooting_steps=[
                    "Retry the request.",
                    "Check server-side logs for crashes.",
                ],
                original=exc,
            )

        if "network is unreachable" in msg or "no route to host" in msg or "enetunreach" in msg:
            return NetworkErrorInfo(
                category=ErrorCategory.NETWORK_UNREACHABLE,
                user_message="Network unreachable — no route to the server.",
                technical_details=_tech(exc),
                is_retryable=True,
                suggested_http_code=502,
                troubleshooting_steps=[
                    "Check your network connection.",
                    "Try pinging the server.",
                    "Check VPN/proxy settings.",
                ],
                original=exc,
            )

    if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout)):
        timeout_type = type(exc).__name__
        return NetworkErrorInfo(
            category=ErrorCategory.CONNECTION_TIMEOUT,
            user_message=f"Request timed out ({timeout_type}).",
            technical_details=_tech(exc),
            is_retryable=True,
            suggested_http_code=504,
            troubleshooting_steps=[
                "Increase the request timeout.",
                "Check network latency.",
                "Retry with a shorter prompt.",
            ],
            original=exc,
        )

    if isinstance(exc, httpx.RemoteProtocolError):
        return NetworkErrorInfo(
            category=ErrorCategory.TRANSIENT,
            user_message="Remote protocol error — unexpected response from server.",
            technical_details=_tech(exc),
            is_retryable=True,
            suggested_http_code=502,
            original=exc,
        )

    if isinstance(exc, VpnChangeError):
        return NetworkErrorInfo(
            category=ErrorCategory.TRANSIENT,
            user_message="Network interface changed (VPN reconnect). Retrying…",
            technical_details=_tech(exc),
            is_retryable=True,
            suggested_http_code=502,
            original=exc,
        )

    if isinstance(exc, NetworkError):
        return NetworkErrorInfo(
            category=ErrorCategory.TRANSIENT,
            user_message=str(exc),
            technical_details=_tech(exc),
            is_retryable=True,
            suggested_http_code=502,
            original=exc,
        )

    return NetworkErrorInfo(
        category=ErrorCategory.UNKNOWN,
        user_message=f"Unexpected network error: {exc}",
        technical_details=_tech(exc),
        is_retryable=False,
        suggested_http_code=502,
        original=exc,
    )


def format_error_for_user(info: NetworkErrorInfo) -> str:
    return f"[{info.category.value}] {info.user_message}"


def get_short_error_message(exc: Exception) -> str:
    return str(exc).split("\n")[0][:120]


def is_transient(exc: Exception) -> bool:
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
