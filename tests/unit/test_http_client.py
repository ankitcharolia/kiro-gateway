# -*- coding: utf-8 -*-

"""
test_http_client.py — STUB (module removed for ACP compliance)

KiroHttpClient (kiro/http_client.py) has been permanently removed from
kiro-gateway.  All inference traffic now flows through the ACP path:

    routes_openai_shim / routes_anthropic_shim
        ↓
    shim_service.py  (orchestration + tool-call round-trips)
        ↓
    acp_client.py    (JSON-RPC 2.0 over stdio)
        ↓
    kiro CLI         (official, authenticated)
        ↓
    Kiro Backend

Tests for the ACP transport layer live in tests/unit/test_acp_client.py.
Tests for orchestration live in tests/unit/test_shim_service.py.

This file is intentionally kept (as a skip-stub) so that any future
attempt to re-introduce http_client.py will be caught immediately by CI.
"""

import pytest


@pytest.mark.skip(
    reason=(
        "KiroHttpClient has been removed. "
        "Direct Kiro API access is not ACP-compliant. "
        "See kiro/acp_client.py for the correct transport layer."
    )
)
def test_http_client_removed() -> None:
    """Placeholder: documents that KiroHttpClient no longer exists."""
    # This test is always skipped; it exists only to make the removal
    # explicit in the test suite and to block accidental re-introduction.
    pass
