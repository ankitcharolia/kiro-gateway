"""
test_auth_manager.py — REMOVED

kiro.auth (KiroAuthManager) was deleted as part of the ACP compliance
refactor.  Authentication is now fully delegated to the official kiro
CLI subprocess via kiro/acp_client.py.

This file is kept as a tombstone so git history stays readable.
All former tests in this file have been retired.

See: kiro/acp_client.py, tests/unit/test_acp_client.py
"""

import pytest


def test_auth_removed_notice() -> None:
    """Confirm kiro.auth is intentionally absent from the package."""
    with pytest.raises(ImportError, match="kiro.auth has been removed"):
        import kiro.auth  # noqa: F401
