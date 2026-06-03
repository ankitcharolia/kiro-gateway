"""
test_account_errors.py — REMOVED

kiro.account_errors was part of the multi-account subsystem removed
during the ACP compliance refactor.  Single-account enforcement means
these error-classification helpers are no longer needed.

This file is kept as a tombstone so git history stays readable.

See: kiro/compliance.py
"""

import pytest


def test_account_errors_removed_notice() -> None:
    """Confirm account_errors module has been intentionally removed."""
    with pytest.raises((ImportError, ModuleNotFoundError)):
        from kiro.account_errors import classify_error  # noqa: F401
