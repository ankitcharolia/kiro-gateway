# -*- coding: utf-8 -*-
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Gateway version — single source of truth
    APP_VERSION: str = "1.0.0"

    # Security
    PROXY_API_KEY: str = "change-me"

    # Kiro CLI
    KIRO_CLI_COMMAND: str = "kiro"

    # AWS region used for the Kiro/CodeWhisperer endpoint
    REGION: str = "us-east-1"

    # Comma-separated list of model IDs to hide from the /models listing.
    # Example: "claude-3-haiku,claude-instant-1"
    HIDDEN_MODELS: str = ""

    # Feature toggles
    ACP_ENABLED: bool = True
    OPENAI_SHIM_ENABLED: bool = True
    ANTHROPIC_SHIM_ENABLED: bool = True

    # Compliance — when True, multi-account failover is rejected at startup
    COMPLIANCE_MODE: bool = True

    # Server
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# ---------------------------------------------------------------------------
# Flat module-level aliases
# Imported by kiro/__init__.py and referenced directly in tests / source files
# as:  from kiro.config import APP_VERSION
# ---------------------------------------------------------------------------
APP_VERSION: str = settings.APP_VERSION
PROXY_API_KEY: str = settings.PROXY_API_KEY
REGION: str = settings.REGION
HIDDEN_MODELS: str = settings.HIDDEN_MODELS
COMPLIANCE_MODE: bool = settings.COMPLIANCE_MODE
KIRO_CLI_COMMAND: str = settings.KIRO_CLI_COMMAND
SERVER_HOST: str = settings.SERVER_HOST
SERVER_PORT: int = settings.SERVER_PORT
ACP_ENABLED: bool = settings.ACP_ENABLED
OPENAI_SHIM_ENABLED: bool = settings.OPENAI_SHIM_ENABLED
ANTHROPIC_SHIM_ENABLED: bool = settings.ANTHROPIC_SHIM_ENABLED
