"""Error classification for Kiro backend responses."""
from __future__ import annotations
from dataclasses import dataclass


class KiroError(Exception):
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
    if status_code == 401:
        return KiroAuthError(body)
    if status_code == 429:
        return KiroRateLimitError(body)
    if status_code == 402:
        return KiroQuotaError(body)
    if status_code == 400 and "context" in body.lower():
        return KiroContextLengthError(body)
    return KiroServerError(body)


@dataclass
class KiroErrorInfo:
    error: KiroError
    category: str
    retryable: bool
    user_message: str
    status_code: int = 500


def enhance_kiro_error(error: KiroError) -> KiroErrorInfo:
    retryable = isinstance(error, (KiroRateLimitError, KiroServerError))
    return KiroErrorInfo(
        error=error,
        category=type(error).__name__,
        retryable=retryable,
        user_message=error.message,
        status_code=error.status_code,
    )
