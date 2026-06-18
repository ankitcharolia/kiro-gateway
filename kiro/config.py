"""Gateway configuration — all settings read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Version — sourced from package metadata which hatch-vcs populates from the
# most recent git tag (e.g. v1.2.0 → "1.2.0").  Falls back to "dev" when
# running directly from source without an installed package.
# ---------------------------------------------------------------------------
try:
    from importlib.metadata import version as _pkg_version
    APP_VERSION: str = _pkg_version("kiro-gateway")
except Exception:
    APP_VERSION = "dev"

# ---------------------------------------------------------------------------
# Auth / API-key
# ---------------------------------------------------------------------------
PROXY_API_KEY: str = (
    os.environ.get("PROXY_API_KEY")
    or os.environ.get("GATEWAY_API_KEY")
    or "test-proxy-key"
)

# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------
COMPLIANCE_MODE: bool = os.environ.get("COMPLIANCE_MODE", "true").lower() != "false"

# ---------------------------------------------------------------------------
# Model settings
# ---------------------------------------------------------------------------
DEFAULT_MODEL: str = os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-5")
DEFAULT_MAX_TOKENS: int = int(os.environ.get("DEFAULT_MAX_TOKENS", "16384"))
DEFAULT_MAX_INPUT_TOKENS: int = int(os.environ.get("DEFAULT_MAX_INPUT_TOKENS", "180000"))

_hidden_raw: str = os.environ.get("HIDDEN_MODELS", "")
HIDDEN_MODELS: List[str] = [m.strip() for m in _hidden_raw.split(",") if m.strip()]

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
# Accept both the canonical names (HOST/PORT) and the names used in .env /
# Docker artifacts (SERVER_HOST/SERVER_PORT). The SERVER_* names take
# precedence so a value set in docker-compose.yml / .env actually applies.
HOST: str = os.environ.get("SERVER_HOST") or os.environ.get("HOST") or "0.0.0.0"
PORT: int = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or "8000")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "info").lower()
DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Kiro / ACP
#
# KIRO_CLI_PATH is the canonical env var for the Kiro CLI binary. The
# KIRO_CLI_COMMAND alias is also accepted (used by the Docker image /
# docker-compose.yml). Set either to the binary name ("kiro-cli") or an
# absolute path ("/usr/local/bin/kiro-cli") when it is not on $PATH.
# ---------------------------------------------------------------------------
KIRO_CLI_PATH: str = (
    os.environ.get("KIRO_CLI_PATH")
    or os.environ.get("KIRO_CLI_COMMAND")
    or "kiro-cli"
)
ACP_TIMEOUT: int = int(os.environ.get("ACP_TIMEOUT", "120"))

# When the kiro-cli agent requests permission to run a built-in tool
# (file edits, command execution, etc.) the gateway auto-approves a single
# invocation when this is true, otherwise it rejects the request. Disable
# (ACP_TRUST_TOOLS=false) to run the agent in a read/answer-only posture.
ACP_TRUST_TOOLS: bool = os.environ.get("ACP_TRUST_TOOLS", "true").lower() != "false"

# Default working directory for ACP sessions. Coding agents may override this
# per-request via filesystem_roots; otherwise the gateway process cwd is used.
ACP_WORKSPACE_DIR: str = os.environ.get("ACP_WORKSPACE_DIR", os.getcwd())


# ---------------------------------------------------------------------------
# Settings object — exposes every constant as an attribute so callers can
# use either the module-level names (legacy) or `settings.<name>` (new style).
# ---------------------------------------------------------------------------
@dataclass
class _Settings:
    # Auth
    PROXY_API_KEY: str = field(default_factory=lambda: PROXY_API_KEY)
    GATEWAY_API_KEY: str = field(default_factory=lambda: PROXY_API_KEY)

    # Compliance
    COMPLIANCE_MODE: bool = field(default_factory=lambda: COMPLIANCE_MODE)

    # Model
    DEFAULT_MODEL: str = field(default_factory=lambda: DEFAULT_MODEL)
    DEFAULT_MAX_TOKENS: int = field(default_factory=lambda: DEFAULT_MAX_TOKENS)
    DEFAULT_MAX_INPUT_TOKENS: int = field(default_factory=lambda: DEFAULT_MAX_INPUT_TOKENS)
    HIDDEN_MODELS: List[str] = field(default_factory=lambda: HIDDEN_MODELS)

    # Server
    HOST: str = field(default_factory=lambda: HOST)
    PORT: int = field(default_factory=lambda: PORT)
    SERVER_HOST: str = field(default_factory=lambda: HOST)
    SERVER_PORT: int = field(default_factory=lambda: PORT)
    LOG_LEVEL: str = field(default_factory=lambda: LOG_LEVEL)
    DEBUG: bool = field(default_factory=lambda: DEBUG)

    # Kiro / ACP
    KIRO_CLI_PATH: str = field(default_factory=lambda: KIRO_CLI_PATH)
    # Alias: some callers/tests refer to the CLI binary as KIRO_CLI_COMMAND.
    KIRO_CLI_COMMAND: str = field(default_factory=lambda: KIRO_CLI_PATH)
    ACP_TIMEOUT: int = field(default_factory=lambda: ACP_TIMEOUT)
    ACP_TRUST_TOOLS: bool = field(default_factory=lambda: ACP_TRUST_TOOLS)
    ACP_WORKSPACE_DIR: str = field(default_factory=lambda: ACP_WORKSPACE_DIR)

    # Feature flags (default enabled; override via env)
    ACP_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("ACP_ENABLED", "true").lower() != "false"
    )
    OPENAI_SHIM_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("OPENAI_SHIM_ENABLED", "true").lower() != "false"
    )
    ANTHROPIC_SHIM_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_SHIM_ENABLED", "true").lower() != "false"
    )

    # App version (from git tag via importlib.metadata)
    APP_VERSION: str = field(default_factory=lambda: APP_VERSION)


settings = _Settings()
