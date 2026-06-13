"""
test_account_manager.py

kiro.account_manager is a minimal single-account manager in ACP compliance mode.
Multi-account failover is prohibited; the gateway enforces a single authenticated
kiro CLI session.
"""
from __future__ import annotations

from kiro.account_manager import AccountManager


def test_account_manager_is_importable():
    """AccountManager can be imported (single-account ACP mode)."""
    assert AccountManager is not None


def test_account_manager_is_ready():
    """AccountManager.is_ready() returns True by default."""
    mgr = AccountManager()
    assert mgr.is_ready() is True


def test_account_manager_set_and_get_models():
    """AccountManager stores and returns model lists."""
    mgr = AccountManager()
    mgr.set_available_models(["claude-sonnet-4-5", "claude-haiku-3-5"])
    models = mgr.get_all_available_models()
    assert "claude-sonnet-4-5" in models
    assert "claude-haiku-3-5" in models


def test_account_manager_empty_by_default():
    """AccountManager starts with an empty model list."""
    mgr = AccountManager()
    assert mgr.get_all_available_models() == []
