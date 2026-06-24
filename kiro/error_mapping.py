# -*- coding: utf-8 -*-
"""
Error mapping — classify ACP/upstream failures into HTTP status codes and the
OpenAI/Anthropic *native* error shapes.

Background
----------
The shims historically mapped every failure to a generic ``502`` with a bare
``{"detail": ...}`` body. That breaks harness retry/back-off logic: a transient
rate-limit (which a well-behaved client should retry with back-off) was
indistinguishable from a permanent gateway error, and the body did not match
the OpenAI/Anthropic error envelope clients parse.

This module centralises a single classification used by **both** shims in
**both** streaming and non-streaming paths, so error fidelity is consistent.

Classification
--------------
Failures reach the gateway as :class:`kiro.acp_client.ACPError` (carrying a
JSON-RPC ``code``/``message``/``data``) for non-streaming completions, or as
normalised ``{"type": "error", "message", "code", "data"}`` events for
streaming. Both carry a human-readable message from kiro-cli/upstream, so the
classification is primarily message/data based with the JSON-RPC code as a
secondary signal.

| Condition (matched in message/data) | HTTP status | OpenAI ``type`` | Anthropic ``type`` |
|--------------------------------------|-------------|-----------------|--------------------|
| rate limit / throttle / quota / 429  | 429         | rate_limit_error| rate_limit_error   |
| overloaded / unavailable / capacity  | 503         | server_error    | overloaded_error   |
| timeout / deadline                   | 504         | server_error    | api_error          |
| (default)                            | 502         | server_error    | api_error          |
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Signal patterns
# ---------------------------------------------------------------------------

_RATE_LIMIT_RE = re.compile(
    r"(rate[\s_-]?limit(?:ed|ing)?|too\s+many\s+requests|throttl(?:e|ed|ing)|"
    r"quota\s+exceeded|insufficient_quota|\b429\b)",
    re.IGNORECASE,
)

_OVERLOADED_RE = re.compile(
    r"(overloaded|service\s+unavailable|temporarily\s+unavailable|"
    r"at\s+capacity|over\s+capacity|try\s+again\s+later|\b503\b|\b529\b)",
    re.IGNORECASE,
)

_TIMEOUT_RE = re.compile(
    r"(timed?\s*out|time[\s_-]?out|deadline\s+exceeded|\b504\b|\b408\b)",
    re.IGNORECASE,
)

# Extract a Retry-After hint (seconds) from common phrasings, e.g.
# "retry after 30", "retry-after: 30", "try again in 30 seconds".
_RETRY_AFTER_RE = re.compile(
    r"(?:retry[\s_-]?after[:\s]+|try\s+again\s+in\s+)(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MappedError:
    """A classified error ready to render in either API's native shape.

    Attributes:
        status_code: The HTTP status code to return (non-streaming) or that the
            error semantically represents (streaming).
        message: The human-readable error message surfaced to the client.
        openai_type: The OpenAI error ``type`` string.
        anthropic_type: The Anthropic error ``type`` string.
        retry_after: Seconds to wait before retrying, when derivable; otherwise
            ``None``. Surfaced as the ``Retry-After`` header on non-streaming
            responses (most relevant for ``429``).
    """

    status_code: int
    message: str
    openai_type: str
    anthropic_type: str
    retry_after: Optional[int] = None

    # -- Native error envelopes --------------------------------------------

    def to_openai_error(self) -> dict[str, Any]:
        """Render the OpenAI error envelope: ``{"error": {...}}``."""
        return {
            "error": {
                "message": self.message,
                "type": self.openai_type,
                "code": None,
                "param": None,
            }
        }

    def to_anthropic_error(self) -> dict[str, Any]:
        """Render the Anthropic error envelope: ``{"type": "error", "error": {...}}``."""
        return {
            "type": "error",
            "error": {
                "type": self.anthropic_type,
                "message": self.message,
            },
        }

    def headers(self) -> dict[str, str]:
        """Return HTTP headers for the error (e.g. ``Retry-After`` on 429/503)."""
        if self.retry_after is not None:
            return {"Retry-After": str(self.retry_after)}
        return {}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_error(
    message: str,
    code: Optional[int] = None,
    data: Any = None,
) -> MappedError:
    """Classify a raw ACP/upstream error into a :class:`MappedError`.

    The classification inspects the error message and any structured ``data``
    for rate-limit / overloaded / timeout signals. The JSON-RPC ``code`` is
    accepted for context/forward-compatibility but the message is the primary
    signal (kiro-cli surfaces upstream conditions as text).

    Args:
        message: The error message from kiro-cli/upstream.
        code: Optional JSON-RPC error code accompanying the failure.
        data: Optional structured error data (dict/str) to also scan.

    Returns:
        A :class:`MappedError` with the resolved status code, native error
        ``type`` strings and an optional ``Retry-After`` hint.
    """
    text = message or ""
    if data is not None:
        text = f"{text} {data!r}"

    retry_after = _extract_retry_after(text)

    if _RATE_LIMIT_RE.search(text):
        return MappedError(
            status_code=429,
            message=message or "Rate limit exceeded",
            openai_type="rate_limit_error",
            anthropic_type="rate_limit_error",
            retry_after=retry_after,
        )

    if _OVERLOADED_RE.search(text):
        return MappedError(
            status_code=503,
            message=message or "Service temporarily overloaded",
            openai_type="server_error",
            anthropic_type="overloaded_error",
            retry_after=retry_after,
        )

    if _TIMEOUT_RE.search(text):
        return MappedError(
            status_code=504,
            message=message or "Upstream request timed out",
            openai_type="server_error",
            anthropic_type="api_error",
            retry_after=retry_after,
        )

    return MappedError(
        status_code=502,
        message=message or "Upstream error",
        openai_type="server_error",
        anthropic_type="api_error",
        retry_after=retry_after,
    )


def classify_exception(exc: BaseException) -> MappedError:
    """Classify an exception (typically :class:`ACPError`) into a MappedError.

    Reads ``code``/``data`` attributes when present (as on
    :class:`kiro.acp_client.ACPError`) and falls back to ``str(exc)`` for the
    message.

    Args:
        exc: The raised exception to classify.

    Returns:
        The corresponding :class:`MappedError`.
    """
    code = getattr(exc, "code", None)
    data = getattr(exc, "data", None)
    return classify_error(str(exc), code=code, data=data)


def classify_event(event: dict[str, Any]) -> MappedError:
    """Classify a normalised streaming ``error`` event into a MappedError.

    Args:
        event: A dict with at least ``message`` and optionally ``code``/``data``
            (see :mod:`kiro.acp_client`).

    Returns:
        The corresponding :class:`MappedError`.
    """
    return classify_error(
        event.get("message") or event.get("error") or "Unknown error",
        code=event.get("code"),
        data=event.get("data"),
    )


def _extract_retry_after(text: str) -> Optional[int]:
    """Pull a Retry-After value (seconds) out of an error string, if present.

    Args:
        text: The combined error message/data text to scan.

    Returns:
        The parsed integer seconds, or ``None`` when no hint is found.
    """
    match = _RETRY_AFTER_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):  # pragma: no cover - regex guarantees digits
        return None
