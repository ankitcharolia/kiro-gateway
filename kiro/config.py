"""Central configuration — all values read from environment variables."""
from __future__ import annotations
import os

APP_VERSION: str = os.environ.get("APP_VERSION", "2.1.0")
PROXY_API_KEY: str = os.environ.get("PROXY_API_KEY", "test-proxy-key")
KIRO_CLI_PATH: str = os.environ.get("KIRO_CLI_PATH", "kiro")
KIRO_ACP_TIMEOUT: int = int(os.environ.get("KIRO_ACP_TIMEOUT", "120"))
KIRO_SESSION_TIMEOUT: int = int(os.environ.get("KIRO_SESSION_TIMEOUT", "600"))
COMPLIANCE_MODE: bool = os.environ.get("COMPLIANCE_MODE", "true").lower() != "false"
ACCOUNT_SYSTEM: bool = os.environ.get("ACCOUNT_SYSTEM", "false").lower() == "true"
WEB_SEARCH_ENABLED: bool = os.environ.get("WEB_SEARCH_ENABLED", "false").lower() == "true"
DEBUG_MODE: bool = os.environ.get("DEBUG_MODE", "false").lower() == "true"
TRUNCATION_RECOVERY: bool = os.environ.get("TRUNCATION_RECOVERY", "true").lower() != "false"
HOST: str = os.environ.get("HOST", "0.0.0.0")
PORT: int = int(os.environ.get("PORT", "8000"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "info")
DEFAULT_MODEL: str = os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-5")
HIDDEN_MODELS: list[str] = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-opus-4",
    "claude-sonnet-4",
]
