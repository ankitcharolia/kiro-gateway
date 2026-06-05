"""Gateway configuration — single source of truth for all settings."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compliance guard — enforced at import time if COMPLIANCE_MODE is set
# ---------------------------------------------------------------------------

def _enforce_compliance() -> None:
    """
    When COMPLIANCE_MODE=true (the default), verify that the gateway is
    configured for single-account use only.

    Raises RuntimeError if multiple accounts are detected.
    """
    mode = os.environ.get("COMPLIANCE_MODE", "true").lower()
    if mode not in ("1", "true", "yes"):
        return

    # Check for legacy multi-account credential files
    cred_file = Path(os.environ.get("KIRO_CREDENTIALS_FILE", "credentials.json"))
    if cred_file.exists():
        import json
        try:
            data = json.loads(cred_file.read_text())
            accounts = data if isinstance(data, list) else []
            if len(accounts) > 1:
                raise RuntimeError(
                    "COMPLIANCE_MODE is enabled but credentials.json contains "
                    f"{len(accounts)} accounts. "
                    "kiro-gateway is designed for single-account personal use only. "
                    "Remove extra entries from credentials.json or set "
                    "COMPLIANCE_MODE=false to suppress this check."
                )
        except json.JSONDecodeError:
            pass

    # Check for explicit multi-account env flag
    if os.environ.get("ACCOUNT_SYSTEM", "").lower() in ("1", "true", "yes"):
        raise RuntimeError(
            "COMPLIANCE_MODE is enabled but ACCOUNT_SYSTEM=true is set. "
            "Multi-account failover is disabled in compliance mode."
        )


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------

@dataclass
class GatewaySettings:
    """All runtime settings, resolved from environment variables."""

    # Network
    host: str = field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("PORT", "8000")))

    # Kiro CLI
    kiro_binary: str = field(default_factory=lambda: os.environ.get("KIRO_BINARY", "kiro"))
    kiro_home: Path = field(
        default_factory=lambda: Path(os.environ.get("KIRO_HOME", str(Path.home() / ".kiro")))
    )

    # Models
    default_model: str = field(
        default_factory=lambda: os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-5")
    )

    # Compliance
    compliance_mode: bool = field(
        default_factory=lambda: os.environ.get("COMPLIANCE_MODE", "true").lower()
        in ("1", "true", "yes")
    )

    # Auth
    api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("GATEWAY_API_KEY") or None
    )

    # Logging
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO").upper())

    # Context window
    context_window: int = field(
        default_factory=lambda: int(os.environ.get("CONTEXT_WINDOW", "180000"))
    )
    output_reserve: int = field(
        default_factory=lambda: int(os.environ.get("OUTPUT_RESERVE", "8192"))
    )

    # MCP tools
    mcp_tools_path: Optional[str] = field(
        default_factory=lambda: os.environ.get("MCP_TOOLS_PATH") or None
    )
    inject_mcp_tools: bool = field(
        default_factory=lambda: os.environ.get("INJECT_MCP_TOOLS", "false").lower()
        in ("1", "true", "yes")
    )

    # Streaming
    stream_chunk_size: int = field(
        default_factory=lambda: int(os.environ.get("STREAM_CHUNK_SIZE", "0"))
    )

    def configure_logging(self) -> None:
        logging.basicConfig(
            level=getattr(logging, self.log_level, logging.INFO),
            format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
        )

    @classmethod
    def load(cls) -> "GatewaySettings":
        """Load settings from environment, enforcing compliance if required."""
        _enforce_compliance()
        settings = cls()
        settings.configure_logging()
        logger.info(
            "kiro-gateway starting | host=%s port=%d model=%s compliance=%s",
            settings.host, settings.port, settings.default_model, settings.compliance_mode,
        )
        return settings


# Module-level singleton — import this everywhere
settings = GatewaySettings.load()
