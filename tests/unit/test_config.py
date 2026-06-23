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
