"""
test_account_manager.py — REMOVED

kiro.account_manager (AccountManager / multi-account failover) was
deleted as part of the ACP compliance refactor.  Multi-account
quota-bypass is prohibited; the gateway now enforces a single
authenticated kiro CLI session.

This file is kept as a tombstone so git history stays readable.

See: kiro/compliance.py, COMPLIANCE.md
"""

import pytest


def test_account_manager_removed_notice() -> None:
    """Confirm multi-account support has been intentionally removed."""
    with pytest.raises((ImportError, ModuleNotFoundError)):
        from kiro.account_manager import AccountManager  # noqa: F401
