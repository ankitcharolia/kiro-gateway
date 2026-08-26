# -*- coding: utf-8 -*-
"""
Unit tests for kiro.kiro_auth — the v3 ``_kiro/auth/getAccessToken`` resolver.

The resolver relays a short-lived access token obtained from kiro-cli to
kiro-cli's own agent server (issue #52). These tests pin the parts that matter
for compliance and security: the covenant-key filter, the fact that failures
never leak token material, and that the bridge is inert on v1/v2.

No real kiro-cli process is spawned: the subprocess is mocked throughout.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from kiro.kiro_auth import (
    AUTH_CALLBACK_ERROR_CODE,
    AUTH_CALLBACK_METHOD,
    KiroAuthError,
    KiroAuthResolver,
    build_resolver,
    parse_token_output,
)

TOKEN = "fake-access-token-value"
EXPIRY = "2026-08-14T11:30:00.031719222Z"
ARN = "arn:aws:codewhisperer:us-east-1:111122223333:profile/ABCDEF"


def _token_line(**overrides) -> bytes:
    """Build a ``kiro-cli chat _ get-kas-token`` style stdout line."""
    data = {
        "accessToken": TOKEN,
        "expiresAt": EXPIRY,
        "profileArn": ARN,
        "provider": "Enterprise",
    }
    data.update(overrides)
    return (json.dumps({"kind": "getKasToken", "data": data}) + "\n").encode()


class TestParseTokenOutputSuccess:
    """A well-formed token line becomes the ACP callback result."""

    def test_covenant_keys_forwarded(self):
        result = parse_token_output(_token_line(), b"")

        assert result == {
            "accessToken": TOKEN,
            "expiresAt": EXPIRY,
            "profileArn": ARN,
            "provider": "Enterprise",
        }

    def test_unknown_fields_are_not_forwarded(self):
        """Only covenant keys reach the wire, so new CLI fields can't leak."""
        raw = json.dumps({
            "kind": "getKasToken",
            "data": {"accessToken": TOKEN, "expiresAt": EXPIRY,
                     "refreshToken": "MUST-NOT-BE-FORWARDED",
                     "someFutureField": "x"},
        }).encode()

        result = parse_token_output(raw, b"")

        assert set(result) == {"accessToken", "expiresAt"}
        assert "refreshToken" not in result
        assert "someFutureField" not in result

    def test_optional_keys_omitted_when_absent(self):
        result = parse_token_output(
            json.dumps({"kind": "getKasToken",
                        "data": {"accessToken": TOKEN, "expiresAt": EXPIRY}}).encode(),
            b"",
        )

        assert result == {"accessToken": TOKEN, "expiresAt": EXPIRY}

    def test_leading_log_line_is_tolerated(self):
        """Only the last stdout line is parsed."""
        raw = b"[INFO] some kiro-cli log noise\n" + _token_line()

        assert parse_token_output(raw, b"")["accessToken"] == TOKEN


class TestParseTokenOutputErrors:
    """Failures raise a fixed, token-free message."""

    def test_empty_output_names_the_remedy(self):
        with pytest.raises(KiroAuthError) as excinfo:
            parse_token_output(b"", b"")

        assert "kiro-cli login" in str(excinfo.value)

    def test_error_kind_does_not_echo_upstream_message(self):
        """kiro-cli's own message is untrusted and must not be surfaced."""
        raw = json.dumps({
            "kind": "error",
            "data": {"message": f"boom {TOKEN} leaked"},
        }).encode()

        with pytest.raises(KiroAuthError) as excinfo:
            parse_token_output(raw, b"")

        assert TOKEN not in str(excinfo.value)
        assert "kiro-cli login" in str(excinfo.value)

    def test_unparseable_line_is_not_echoed(self):
        """A malformed line could itself be a live token — never repeat it."""
        with pytest.raises(KiroAuthError) as excinfo:
            parse_token_output(f"{TOKEN} trailing junk".encode(), b"")

        assert TOKEN not in str(excinfo.value)

    def test_stderr_is_never_surfaced(self):
        with pytest.raises(KiroAuthError) as excinfo:
            parse_token_output(b"", f"stderr with {TOKEN}".encode())

        assert TOKEN not in str(excinfo.value)

    @pytest.mark.parametrize("payload", [
        {"kind": "getKasToken"},                                  # no data
        {"kind": "getKasToken", "data": []},                      # data not a dict
        {"kind": "somethingElse", "data": {"accessToken": TOKEN}},  # wrong kind
        {"kind": "getKasToken", "data": {"expiresAt": EXPIRY}},    # no token
        {"kind": "getKasToken", "data": {"accessToken": TOKEN}},   # no expiry
    ])
    def test_malformed_payloads_raise(self, payload):
        with pytest.raises(KiroAuthError):
            parse_token_output(json.dumps(payload).encode(), b"")

    def test_non_object_json_raises(self):
        with pytest.raises(KiroAuthError):
            parse_token_output(b'["not", "an", "object"]', b"")


class TestResolveSubprocess:
    """resolve() shells out to kiro-cli without a shell and honours a timeout."""

    @pytest.mark.asyncio
    async def test_resolve_returns_payload_and_uses_argv_list(self):
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(_token_line(), b""))

        with patch("asyncio.create_subprocess_exec",
                   AsyncMock(return_value=proc)) as spawn:
            resolver = KiroAuthResolver(cli_path="/usr/bin/kiro-cli")
            result = await resolver.resolve()

        assert result["accessToken"] == TOKEN
        # argv list (no shell string) => no command-injection surface.
        assert spawn.await_args.args == (
            "/usr/bin/kiro-cli", "chat", "_", "get-kas-token",
        )

    @pytest.mark.asyncio
    async def test_resolve_is_not_cached(self):
        """Each callback re-runs the command; no token is retained."""
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(_token_line(), b""))

        with patch("asyncio.create_subprocess_exec",
                   AsyncMock(return_value=proc)) as spawn:
            resolver = KiroAuthResolver()
            await resolver.resolve()
            await resolver.resolve()

        assert spawn.await_count == 2
        assert not any("token" in str(v).lower() and TOKEN in str(v)
                       for v in vars(resolver).values())

    @pytest.mark.asyncio
    async def test_spawn_failure_raises_auth_error(self):
        with patch("asyncio.create_subprocess_exec",
                   AsyncMock(side_effect=OSError("no such file"))):
            with pytest.raises(KiroAuthError) as excinfo:
                await KiroAuthResolver().resolve()

        assert "could not launch kiro-cli" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_timeout_kills_process_and_raises(self):
        proc = AsyncMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        proc.wait = AsyncMock()
        proc.kill = lambda: setattr(proc, "killed", True)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            with pytest.raises(KiroAuthError) as excinfo:
                await KiroAuthResolver(timeout=0.01).resolve()

        assert "timed out" in str(excinfo.value)
        assert getattr(proc, "killed", False) is True

    @pytest.mark.asyncio
    async def test_cancellation_kills_process_and_propagates(self):
        """Teardown must not leave a credential subprocess running detached."""
        proc = AsyncMock()
        proc.communicate = AsyncMock(side_effect=asyncio.CancelledError)
        proc.kill = lambda: setattr(proc, "killed", True)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            with pytest.raises(asyncio.CancelledError):
                await KiroAuthResolver().resolve()

        assert getattr(proc, "killed", False) is True


class TestBuildResolver:
    """The bridge only exists for v3, and only when enabled."""

    @pytest.mark.parametrize("engine", ["v1", "v2", "V2", "", None])
    def test_non_v3_engines_get_no_resolver(self, engine):
        assert build_resolver("kiro-cli", engine, True) is None

    def test_v3_enabled_builds_resolver(self):
        assert isinstance(build_resolver("kiro-cli", "v3", True), KiroAuthResolver)

    def test_v3_case_insensitive(self):
        assert isinstance(build_resolver("kiro-cli", "V3", True), KiroAuthResolver)

    def test_v3_disabled_fails_closed(self):
        """ACP_AUTH_BRIDGE=false must not relay a credential."""
        assert build_resolver("kiro-cli", "v3", False) is None


class TestConstants:
    """The wire-level constants match the live v3 protocol."""

    def test_method_name(self):
        assert AUTH_CALLBACK_METHOD == "_kiro/auth/getAccessToken"

    def test_error_code_in_server_range(self):
        assert AUTH_CALLBACK_ERROR_CODE == -32000
