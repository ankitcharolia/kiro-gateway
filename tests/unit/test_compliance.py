"""
Unit tests for compliance.py — single-account enforcement.
"""
from __future__ import annotations

import pytest

from kiro.compliance import validate_single_account_compliance, ComplianceError


def test_single_session_passes():
    """A single kiro CLI session passes compliance validation."""
    # Should not raise
    validate_single_account_compliance(session_count=1)


def test_zero_sessions_passes():
    """Zero sessions (not yet started) passes compliance validation."""
    validate_single_account_compliance(session_count=0)


def test_multiple_sessions_raises():
    """More than one simultaneous session raises ComplianceError."""
    with pytest.raises((ComplianceError, ValueError, RuntimeError)):
        validate_single_account_compliance(session_count=2)


def test_compliance_error_message_is_descriptive():
    """ComplianceError message explains the single-account requirement."""
    with pytest.raises(Exception) as exc_info:
        validate_single_account_compliance(session_count=3)
    msg = str(exc_info.value).lower()
    # Message should mention account, session, or compliance
    assert any(word in msg for word in ["account", "session", "compliance", "single"])
