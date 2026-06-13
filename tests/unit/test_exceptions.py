"""Unit tests for kiro.exceptions — ACP-mode exception hierarchy."""
from __future__ import annotations

import pytest

from kiro.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ComplianceError,
    KiroGatewayError,
    RateLimitError,
    TimeoutError,
    UpstreamError,
    ValidationError,
)


def test_kiro_gateway_error_is_exception():
    err = KiroGatewayError("oops")
    assert isinstance(err, Exception)
    assert err.message == "oops"
    assert err.status_code == 500


def test_kiro_gateway_error_custom_status():
    err = KiroGatewayError("bad", status_code=503)
    assert err.status_code == 503


def test_authentication_error_status():
    err = AuthenticationError("no key")
    assert err.status_code == 401
    assert isinstance(err, KiroGatewayError)


def test_authorization_error_status():
    err = AuthorizationError("forbidden")
    assert err.status_code == 403


def test_validation_error_status():
    err = ValidationError("invalid")
    assert err.status_code == 422


def test_rate_limit_error_status():
    err = RateLimitError("slow down")
    assert err.status_code == 429


def test_upstream_error_status():
    err = UpstreamError("bad gateway")
    assert err.status_code == 502


def test_timeout_error_status():
    err = TimeoutError("timed out")
    assert err.status_code == 504


def test_compliance_error_status():
    err = ComplianceError("single account only")
    assert err.status_code == 403
    assert isinstance(err, KiroGatewayError)


def test_exceptions_are_catchable_as_base():
    with pytest.raises(KiroGatewayError):
        raise AuthenticationError("test")
