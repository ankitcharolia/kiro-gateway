"""
test_account_system_flow.py — REMOVED

The multi-account system flow tests were removed together with
kiro.account_manager during the ACP compliance refactor.

Multi-account failover is prohibited because it is designed to
circumvent per-subscription rate limits.  The gateway now uses a
single authenticated kiro CLI session and surfaces 429 / 402 errors
directly to the caller without retrying on another account.

This file is kept as a tombstone so git history stays readable.

See: kiro/compliance.py, COMPLIANCE.md, kiro/acp_client.py
"""

import pytest


def test_account_system_flow_removed_notice() -> None:
    """Confirm the multi-account system has been intentionally removed."""
    with pytest.raises((ImportError, ModuleNotFoundError)):
        from kiro.account_manager import AccountManager  # noqa: F401
