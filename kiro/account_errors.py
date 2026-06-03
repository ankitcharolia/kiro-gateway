"""Account-system error types."""
from __future__ import annotations


class AccountNotAvailableError(Exception):
    """Raised when no account is available to serve a request."""


class AccountQuotaExceededError(Exception):
    """Raised when the account quota is exhausted."""


class MultiAccountDisabledError(RuntimeError):
    """Raised when multi-account mode is attempted in compliance mode."""
