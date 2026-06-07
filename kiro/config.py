"""Gateway configuration — all settings read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
APP_VERSION: str = "2.1.0"

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
HOST: str = os.environ.get("HOST", "0.0.0.0")
PORT: int = int(os.environ.get("PORT", "8000"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "info").lower()
DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Kiro / ACP
# ---------------------------------------------------------------------------
KIRO_CLI_PATH: str = os.environ.get("KIRO_CLI_PATH", "kiro")
ACP_TIMEOUT: int = int(os.environ.get("ACP_TIMEOUT", "120"))


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
    KIRO_CLI_COMMAND: str = field(default_factory=lambda: KIRO_CLI_PATH)
    ACP_TIMEOUT: int = field(default_factory=lambda: ACP_TIMEOUT)

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

    # App version
    APP_VERSION: str = field(default_factory=lambda: APP_VERSION)


settings = _Settings()
