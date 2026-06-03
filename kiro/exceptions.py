"""Application-level exception hierarchy."""
from __future__ import annotations


class KiroGatewayError(Exception):
    """Base for all gateway exceptions."""
    status_code: int = 500

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class AuthenticationError(KiroGatewayError):
    status_code = 401


class AuthorizationError(KiroGatewayError):
    status_code = 403


class ValidationError(KiroGatewayError):
    status_code = 422


class RateLimitError(KiroGatewayError):
    status_code = 429


class UpstreamError(KiroGatewayError):
    status_code = 502


class TimeoutError(KiroGatewayError):  # noqa: A001
    status_code = 504


class ComplianceError(KiroGatewayError):
    """Raised when a request violates the single-account compliance policy."""
    status_code = 403
