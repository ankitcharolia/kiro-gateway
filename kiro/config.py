"""Gateway configuration — all settings read from environment variables."""
from __future__ import annotations

import os
from typing import List

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
APP_VERSION: str = "2.1.0"

# ---------------------------------------------------------------------------
# Auth / API-key
# ---------------------------------------------------------------------------
# Callers (Cursor, Cline, etc.) authenticate with this key.
# Accept either env-var spelling for backwards-compat.
PROXY_API_KEY: str = (
    os.environ.get("PROXY_API_KEY")
    or os.environ.get("GATEWAY_API_KEY")
    or "test-proxy-key"
)

# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------
# When True (the default) multi-account failover is disabled and 429/402
# responses from Kiro are surfaced directly to the caller.
COMPLIANCE_MODE: bool = os.environ.get("COMPLIANCE_MODE", "true").lower() != "false"

# ---------------------------------------------------------------------------
# Model settings
# ---------------------------------------------------------------------------
DEFAULT_MODEL: str = os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-5")
DEFAULT_MAX_TOKENS: int = int(os.environ.get("DEFAULT_MAX_TOKENS", "16384"))
DEFAULT_MAX_INPUT_TOKENS: int = int(os.environ.get("DEFAULT_MAX_INPUT_TOKENS", "180000"))

# Comma-separated list of model IDs to hide from /v1/models responses.
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
