"""kiro-gateway compliance enforcement."""
from __future__ import annotations

from loguru import logger


class ComplianceError(RuntimeError):
    """Raised when a compliance policy is violated."""


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


def validate_single_account_compliance(session_count: int = 1) -> None:
    """
    Validate that at most one Kiro CLI session is in use.

    Args:
        session_count: Number of simultaneous active sessions / accounts.

    Raises:
        ComplianceError: If session_count > 1.
    """
    if session_count > 1:
        raise ComplianceError(
            f"Compliance violation: {session_count} simultaneous sessions detected. "
            "Only a single Kiro account/session is permitted. "
            "Multi-account credential pooling circumvents quota enforcement and "
            "violates the AWS Acceptable Use Policy and Kiro ToS. "
            "See README.md for details."
        )
    logger.debug(f"Compliance check passed: session_count={session_count}")


def log_compliance_banner() -> None:
    """Logs the compliance mode banner at startup."""
    for line in COMPLIANCE_BANNER.strip().split("\n"):
        logger.info(line)
