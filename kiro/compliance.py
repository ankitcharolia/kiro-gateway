# -*- coding: utf-8 -*-
"""
kiro-gateway compliance enforcement.

This module enforces single-account usage to ensure kiro-gateway
operates within the spirit of the Kiro / AWS ToS:

  - Only ONE credential source is permitted at a time.
  - Multi-account failover is disabled: rate limit errors (429, 402, 403)
    are surfaced directly to the caller, not retried on another account.
  - This gateway is intended for personal, single-subscription use only.

See: https://aws.amazon.com/aup/ and https://kiro.dev/terms
"""

import json
from pathlib import Path
from loguru import logger


COMPLIANCE_BANNER = """
╔══════════════════════════════════════════════════════════════╗
║              KIRO GATEWAY — COMPLIANCE MODE                  ║
║                                                              ║
║  ✅ Single-account mode enforced                             ║
║  ✅ Rate-limit errors surfaced to caller (no failover)        ║
║  ✅ Requires a valid personal Kiro subscription               ║
║                                                              ║
║  This gateway is a personal API compatibility shim.          ║
║  Multi-account credential pooling is NOT supported.          ║
║  See README.md for usage requirements.                       ║
╚══════════════════════════════════════════════════════════════╝
"""


def validate_single_account_compliance(credentials_file: str) -> None:
    """
    Validates that credentials.json contains exactly ONE account entry.

    Multi-account configurations are blocked because cycling through accounts
    on rate-limit errors (429/402) circumvents AWS/Kiro quota enforcement,
    which violates the Acceptable Use Policy.

    Args:
        credentials_file: Path to credentials.json

    Raises:
        RuntimeError: If more than one account entry is found.
    """
    creds_path = Path(credentials_file)
    if not creds_path.exists():
        return  # No file yet — will be created from .env, single-entry by design

    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not read {credentials_file} for compliance check: {e}")
        return

    if not isinstance(data, list):
        return  # Unexpected format — let AccountManager handle it

    if len(data) > 1:
        logger.error("")
        logger.error("=" * 64)
        logger.error("  COMPLIANCE ERROR: Multi-account mode is disabled")
        logger.error("=" * 64)
        logger.error("")
        logger.error(f"  Found {len(data)} account entries in {credentials_file}.")
        logger.error("")
        logger.error("  kiro-gateway is designed for SINGLE-ACCOUNT personal use only.")
        logger.error("  Cycling through multiple accounts to bypass rate limits")
        logger.error("  violates the AWS Acceptable Use Policy and Kiro ToS.")
        logger.error("")
        logger.error("  Fix: Keep only ONE entry in credentials.json.")
        logger.error("")
        logger.error("=" * 64)
        raise RuntimeError(
            "Compliance violation: credentials.json contains multiple accounts. "
            "Only a single account entry is permitted. "
            "See README.md for details."
        )

    logger.debug("Compliance check passed: single account entry confirmed.")


def log_compliance_banner() -> None:
    """Logs the compliance mode banner at startup."""
    for line in COMPLIANCE_BANNER.strip().split("\n"):
        logger.info(line)
