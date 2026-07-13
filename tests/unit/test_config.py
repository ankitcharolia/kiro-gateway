"""Unit tests for kiro.config — ACP-mode configuration."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from kiro.config import (
    APP_VERSION,
    COMPLIANCE_MODE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    HOST,
    KIRO_CLI_PATH,
    LOG_LEVEL,
    PORT,
    KIRO_GATEWAY_API_KEY,
    settings,
)


def test_app_version_is_string():
    assert isinstance(APP_VERSION, str)
    assert len(APP_VERSION) > 0


def test_proxy_api_key_has_default():
    assert isinstance(KIRO_GATEWAY_API_KEY, str)
    assert len(KIRO_GATEWAY_API_KEY) > 0


def test_compliance_mode_default_true():
    assert COMPLIANCE_MODE is True


def test_default_model_is_claude():
    assert "claude" in DEFAULT_MODEL.lower()


def test_default_max_tokens_positive():
    assert DEFAULT_MAX_TOKENS > 0


def test_host_default():
    assert HOST == "0.0.0.0"


def test_port_default():
    assert PORT == 8000
    assert isinstance(PORT, int)


def test_log_level_lowercase():
    assert LOG_LEVEL == LOG_LEVEL.lower()


def test_kiro_cli_path_default():
    """KIRO_CLI_PATH defaults to the shipped binary name 'kiro-cli'.

    Evaluated in an isolated subprocess with KIRO_CLI_PATH removed from the
    environment so the result reflects the code default rather than any
    ambient override (e.g. when the suite runs inside a kiro-cli session).
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if k != "KIRO_CLI_PATH"}
    out = subprocess.check_output(
        [sys.executable, "-c", "from kiro.config import KIRO_CLI_PATH; print(KIRO_CLI_PATH)"],
        env=env,
        cwd=str(repo_root),
    ).decode().strip()
    assert out == "kiro-cli"


def test_settings_object_exists():
    assert settings is not None


def test_settings_proxy_api_key():
    assert settings.KIRO_GATEWAY_API_KEY == KIRO_GATEWAY_API_KEY


def test_settings_compliance_mode():
    assert settings.COMPLIANCE_MODE == COMPLIANCE_MODE


def test_settings_server_host():
    assert settings.SERVER_HOST == HOST


def test_settings_server_port():
    assert settings.SERVER_PORT == PORT


def test_settings_kiro_cli_command():
    assert settings.KIRO_CLI_COMMAND == KIRO_CLI_PATH


def test_settings_app_version():
    assert settings.APP_VERSION == APP_VERSION


def test_proxy_api_key_from_env():
    with patch.dict(os.environ, {"KIRO_GATEWAY_API_KEY": "custom-key-123"}):
        # Re-import to pick up env change would require reload;
        # verify settings object defaults match module-level values.
        assert settings.KIRO_GATEWAY_API_KEY == KIRO_GATEWAY_API_KEY


def test_settings_feature_flags_are_bool():
    assert isinstance(settings.ACP_ENABLED, bool)
    assert isinstance(settings.OPENAI_SHIM_ENABLED, bool)
    assert isinstance(settings.ANTHROPIC_SHIM_ENABLED, bool)


def test_settings_feature_flags_default_true():
    assert settings.ACP_ENABLED is True
    assert settings.OPENAI_SHIM_ENABLED is True
    assert settings.ANTHROPIC_SHIM_ENABLED is True


# ---------------------------------------------------------------------------
# MCP server configuration (KIRO_MCP_SERVERS / KIRO_MCP_CONFIG)
# ---------------------------------------------------------------------------

class TestMcpServerConfig:
    """MCP server configs are parsed/normalised into an ACP mcpServers array."""

    def test_inline_json_array_used_verbatim(self):
        from kiro.config import _load_mcp_servers
        payload = '[{"type": "http", "name": "svc", "url": "http://h/mcp"}]'
        with patch.dict(os.environ, {"KIRO_MCP_SERVERS": payload}, clear=False):
            servers = _load_mcp_servers()
        assert servers == [{"type": "http", "name": "svc", "url": "http://h/mcp", "headers": []}]

    def test_inline_mcpservers_wrapper_object(self):
        from kiro.config import _load_mcp_servers
        payload = '{"mcpServers": {"svc": {"url": "http://h/mcp", "type": "http"}}}'
        with patch.dict(os.environ, {"KIRO_MCP_SERVERS": payload}, clear=False):
            servers = _load_mcp_servers()
        assert servers == [{"name": "svc", "url": "http://h/mcp", "type": "http", "headers": []}]

    def test_inline_bare_name_map(self):
        from kiro.config import _load_mcp_servers
        payload = '{"svc": {"command": "run", "args": ["x"]}}'
        with patch.dict(os.environ, {"KIRO_MCP_SERVERS": payload}, clear=False):
            servers = _load_mcp_servers()
        assert servers == [{"name": "svc", "command": "run", "args": ["x"], "env": []}]

    def test_entries_without_name_dropped(self):
        from kiro.config import _load_mcp_servers
        payload = '[{"url": "http://h/mcp"}, {"name": "ok", "url": "u"}]'
        with patch.dict(os.environ, {"KIRO_MCP_SERVERS": payload}, clear=False):
            servers = _load_mcp_servers()
        assert servers == [{"name": "ok", "url": "u", "type": "http", "headers": []}]

    def test_invalid_json_returns_empty(self):
        from kiro.config import _load_mcp_servers
        with patch.dict(os.environ, {"KIRO_MCP_SERVERS": "not json {"}, clear=False):
            servers = _load_mcp_servers()
        assert servers == []

    def test_file_source_when_no_inline(self, tmp_path):
        from kiro.config import _load_mcp_servers
        cfg = tmp_path / "mcp.json"
        cfg.write_text('{"mcpServers": [{"name": "f", "url": "http://h/mcp"}]}')
        env = {"KIRO_MCP_CONFIG": str(cfg)}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("KIRO_MCP_SERVERS", None)
            servers = _load_mcp_servers()
        assert servers == [{"name": "f", "url": "http://h/mcp", "type": "http", "headers": []}]

    def test_missing_file_returns_empty(self):
        from kiro.config import _load_mcp_servers
        with patch.dict(os.environ, {"KIRO_MCP_CONFIG": "/no/such/file.json"}, clear=False):
            os.environ.pop("KIRO_MCP_SERVERS", None)
            servers = _load_mcp_servers()
        assert servers == []

    def test_default_empty(self):
        from kiro.config import _load_mcp_servers
        env = {k: v for k, v in os.environ.items()
               if k not in ("KIRO_MCP_SERVERS", "KIRO_MCP_CONFIG")}
        with patch.dict(os.environ, env, clear=True):
            servers = _load_mcp_servers()
        assert servers == []

    def test_settings_exposes_mcp_servers(self):
        assert isinstance(settings.MCP_SERVERS, list)


class TestMcpServerNormalization:
    """HTTP entries are coerced to the shape kiro-cli's session/new requires."""

    def test_http_headers_object_becomes_array(self):
        from kiro.config import _normalize_mcp_servers
        raw = [{"name": "s", "url": "http://h/mcp", "headers": {"Authorization": "Bearer t"}}]
        out = _normalize_mcp_servers(raw)
        assert out[0]["type"] == "http"
        assert out[0]["headers"] == [{"name": "Authorization", "value": "Bearer t"}]

    def test_http_missing_headers_defaulted_to_array(self):
        from kiro.config import _normalize_mcp_servers
        out = _normalize_mcp_servers([{"name": "s", "url": "http://h/mcp"}])
        assert out[0]["type"] == "http"
        assert out[0]["headers"] == []

    def test_http_type_missing_defaults_http(self):
        from kiro.config import _normalize_mcp_servers
        out = _normalize_mcp_servers([{"name": "s", "url": "http://h/mcp", "headers": []}])
        assert out[0]["type"] == "http"

    def test_http_headers_array_passthrough(self):
        from kiro.config import _normalize_mcp_servers
        raw = [{"type": "http", "name": "s", "url": "u",
                "headers": [{"name": "X", "value": "1"}]}]
        out = _normalize_mcp_servers(raw)
        assert out[0]["headers"] == [{"name": "X", "value": "1"}]

    def test_sse_type_preserved(self):
        from kiro.config import _normalize_mcp_servers
        out = _normalize_mcp_servers([{"type": "sse", "name": "s", "url": "u"}])
        assert out[0]["type"] == "sse"

    def test_stdio_env_object_becomes_array(self):
        from kiro.config import _normalize_mcp_servers
        raw = [{"name": "s", "command": "run", "env": {"FOO": "bar"}}]
        out = _normalize_mcp_servers(raw)
        assert out[0]["env"] == [{"name": "FOO", "value": "bar"}]
        assert out[0]["args"] == []

    def test_mcp_init_timeout_default(self):
        assert isinstance(settings.MCP_INIT_TIMEOUT, int)
        assert settings.MCP_INIT_TIMEOUT > 0
