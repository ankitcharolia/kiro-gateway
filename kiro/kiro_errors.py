"""Error classification for Kiro backend responses."""
from __future__ import annotations


class KiroError(Exception):
    """Base class for all Kiro-originated errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class KiroAuthError(KiroError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class KiroRateLimitError(KiroError):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, status_code=429)


class KiroQuotaError(KiroError):
    def __init__(self, message: str = "Quota exceeded") -> None:
        super().__init__(message, status_code=402)


class KiroContextLengthError(KiroError):
    def __init__(self, message: str = "Context length exceeded") -> None:
        super().__init__(message, status_code=400)


class KiroServerError(KiroError):
    def __init__(self, message: str = "Kiro server error") -> None:
        super().__init__(message, status_code=500)


def classify_error(status_code: int, body: str) -> KiroError:
    """Map an HTTP status code to the appropriate KiroError subclass."""
    if status_code == 401:
        return KiroAuthError(body)
    if status_code == 429:
        return KiroRateLimitError(body)
    if status_code == 402:
        return KiroQuotaError(body)
    if status_code == 400 and "context" in body.lower():
        return KiroContextLengthError(body)
    return KiroServerError(body)
