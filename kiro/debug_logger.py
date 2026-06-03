"""Optional structured debug logging."""
from __future__ import annotations
import json
import logging
from typing import Any

logger = logging.getLogger("kiro.debug")


def log_request(method: str, path: str, body: Any = None) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    logger.debug(json.dumps({"event": "request", "method": method, "path": path, "body": body}))


def log_response(status: int, body: Any = None) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    logger.debug(json.dumps({"event": "response", "status": status, "body": body}))


def log_acp_call(method: str, params: Any = None) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    logger.debug(json.dumps({"event": "acp", "method": method, "params": params}))
