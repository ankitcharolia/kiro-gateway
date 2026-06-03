# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/ankitcharolia/kiro-gateway
# Fork of https://github.com/jwadow/kiro-gateway by Jwadow
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Kiro Gateway - OpenAI-compatible interface for Kiro API.

SINGLE-ACCOUNT COMPLIANCE MODE
-------------------------------
This gateway enforces single-account personal use:
  - Only one credential source is permitted.
  - Rate-limit (429/402/403) errors are surfaced to the caller.
  - Multi-account failover is disabled.

Usage:
    # Using default settings (host: 0.0.0.0, port: 8000)
    python main.py

    # With CLI arguments (highest priority)
    python main.py --port 9000
    python main.py --host 127.0.0.1 --port 9000

    # With environment variables (medium priority)
    SERVER_PORT=9000 python main.py

    # Using uvicorn directly
    uvicorn main:app --host 0.0.0.0 --port 8000

Priority: CLI args > Environment variables > Default values
"""

import argparse
import asyncio
import json
import logging
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from kiro.config import (
    APP_TITLE,
    APP_DESCRIPTION,
    APP_VERSION,
    REFRESH_TOKEN,
    PROFILE_ARN,
    REGION,
    KIRO_CREDS_FILE,
    KIRO_CLI_DB_FILE,
    PROXY_API_KEY,
    LOG_LEVEL,
    SERVER_HOST,
    SERVER_PORT,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    STREAMING_READ_TIMEOUT,
    HIDDEN_MODELS,
    MODEL_ALIASES,
    HIDDEN_FROM_LIST,
    FALLBACK_MODELS,
    VPN_PROXY_URL,
    ACCOUNT_SYSTEM,
    ACCOUNTS_CONFIG_FILE,
    ACCOUNTS_STATE_FILE,
    _warn_timeout_configuration,
)
from kiro.auth import KiroAuthManager
from kiro.cache import ModelInfoCache
from kiro.model_resolver import ModelResolver
from kiro.account_manager import AccountManager
from kiro.routes_openai import router as openai_router
from kiro.routes_anthropic import router as anthropic_router
from kiro.exceptions import validation_exception_handler
from kiro.debug_middleware import DebugLoggerMiddleware
from kiro.compliance import validate_single_account_compliance, log_compliance_banner


# --- Loguru Configuration ---
logger.remove()
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


class InterceptHandler(logging.Handler):
    """
    Intercepts logs from standard logging and redirects them to loguru.

    Also filters out noisy shutdown-related exceptions (CancelledError, KeyboardInterrupt)
    that are normal during Ctrl+C but uvicorn logs as ERROR.
    """

    SHUTDOWN_EXCEPTIONS = (
        "CancelledError",
        "KeyboardInterrupt",
        "asyncio.exceptions.CancelledError",
    )

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type is not None:
                exc_name = exc_type.__name__
                if exc_name in self.SHUTDOWN_EXCEPTIONS:
                    logger.info("Server shutdown in progress...")
                    return

        msg = record.getMessage()
        if any(exc in msg for exc in self.SHUTDOWN_EXCEPTIONS):
            return

        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging_intercept():
    loggers_to_intercept = [
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
    ]
    for logger_name in loggers_to_intercept:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]
        logging_logger.propagate = False


setup_logging_intercept()


# ==================================================================================================
# VPN/Proxy Configuration
# ==================================================================================================
if VPN_PROXY_URL:
    proxy_url_with_scheme = VPN_PROXY_URL if "://" in VPN_PROXY_URL else f"http://{VPN_PROXY_URL}"
    os.environ['HTTP_PROXY'] = proxy_url_with_scheme
    os.environ['HTTPS_PROXY'] = proxy_url_with_scheme
    os.environ['ALL_PROXY'] = proxy_url_with_scheme
    no_proxy_hosts = os.environ.get("NO_PROXY", "")
    local_hosts = "127.0.0.1,localhost"
    if no_proxy_hosts:
        os.environ["NO_PROXY"] = f"{no_proxy_hosts},{local_hosts}"
    else:
        os.environ["NO_PROXY"] = local_hosts
    logger.info(f"Proxy configured: {proxy_url_with_scheme}")
    logger.debug(f"NO_PROXY: {os.environ['NO_PROXY']}")


# --- Configuration Validation ---
def validate_configuration() -> None:
    """
    Validates that required configuration is present and compliant.

    Single-account compliance is enforced here:
    - credentials.json must contain at most ONE account entry.
    - ACCOUNT_SYSTEM multi-account mode is blocked.

    Raises:
        SystemExit: If critical configuration is missing.
        RuntimeError: If compliance rules are violated.
    """
    # --- Compliance: block multi-account credentials.json ---
    validate_single_account_compliance(ACCOUNTS_CONFIG_FILE)

    # --- Block ACCOUNT_SYSTEM=true (multi-account mode) ---
    if ACCOUNT_SYSTEM:
        logger.error("")
        logger.error("=" * 64)
        logger.error("  COMPLIANCE ERROR: ACCOUNT_SYSTEM=true is disabled")
        logger.error("=" * 64)
        logger.error("")
        logger.error("  Multi-account mode (ACCOUNT_SYSTEM=true) has been disabled")
        logger.error("  in this fork to comply with AWS/Kiro terms of service.")
        logger.error("")
        logger.error("  kiro-gateway is for single-account personal use only.")
        logger.error("  Remove ACCOUNT_SYSTEM from your .env or set it to false.")
        logger.error("")
        logger.error("=" * 64)
        raise RuntimeError(
            "Compliance: ACCOUNT_SYSTEM=true is not permitted. "
            "This gateway supports single-account use only."
        )

    from kiro.config import ACCOUNTS_CONFIG_FILE
    creds_json_path = Path(ACCOUNTS_CONFIG_FILE)

    if creds_json_path.exists():
        logger.debug(f"Found {ACCOUNTS_CONFIG_FILE}, skipping legacy .env validation")
        return

    errors = []
    env_file = Path(".env")

    has_refresh_token = bool(REFRESH_TOKEN)
    has_creds_file = bool(KIRO_CREDS_FILE)
    has_cli_db = bool(KIRO_CLI_DB_FILE)

    if KIRO_CREDS_FILE:
        creds_path = Path(KIRO_CREDS_FILE).expanduser()
        if not creds_path.exists():
            has_creds_file = False
            logger.warning(f"KIRO_CREDS_FILE not found: {KIRO_CREDS_FILE}")

    if KIRO_CLI_DB_FILE:
        cli_db_path = Path(KIRO_CLI_DB_FILE).expanduser()
        if not cli_db_path.exists():
            has_cli_db = False
            logger.warning(f"KIRO_CLI_DB_FILE not found: {KIRO_CLI_DB_FILE}")

    if not has_refresh_token and not has_creds_file and not has_cli_db:
        if not env_file.exists():
            errors.append(
                "No Kiro credentials configured!\n"
                "\n"
                "To get started:\n"
                "1. Create .env file:\n"
                "   cp .env.example .env\n"
                "\n"
                "2. Edit .env and configure your credentials:\n"
                "   2.1. Set a secure password as PROXY_API_KEY\n"
                "   2.2. Set your Kiro credentials (one of):\n"
                "      - KIRO_CREDS_FILE=~/.aws/sso/cache/kiro-auth-token.json\n"
                "      - REFRESH_TOKEN=your_refresh_token\n"
                "      - KIRO_CLI_DB_FILE=~/.local/share/kiro-cli/data.sqlite3\n"
                "\n"
                "See README.md for detailed instructions."
            )
        else:
            errors.append(
                "No Kiro credentials configured!\n"
                "\n"
                "   Configure ONE of the following in your .env file:\n"
                "\n"
                "   PROXY_API_KEY=\"my-super-secret-password-123\"\n"
                "\n"
                "   Option 1 (Recommended): JSON credentials file\n"
                "      KIRO_CREDS_FILE=\"~/.aws/sso/cache/kiro-auth-token.json\"\n"
                "\n"
                "   Option 2: Refresh token\n"
                "      REFRESH_TOKEN=\"your_refresh_token_here\"\n"
                "\n"
                "   Option 3: kiro-cli SQLite database\n"
                "      KIRO_CLI_DB_FILE=\"~/.local/share/kiro-cli/data.sqlite3\"\n"
                "\n"
                "   See README.md for how to obtain credentials."
            )

    if errors:
        logger.error("")
        logger.error("=" * 60)
        logger.error("  CONFIGURATION ERROR")
        logger.error("=" * 60)
        for error in errors:
            for line in error.split('\n'):
                logger.error(f"  {line}")
        logger.error("=" * 60)
        logger.error("")
        raise RuntimeError("Configuration validation failed")


# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application lifecycle.

    Single-account compliance is enforced here: if credentials.json
    was modified to contain multiple accounts after startup validation,
    a final check is run before any requests are served.
    """
    logger.info("Starting application... Creating state managers.")

    # Final compliance guard before serving requests
    validate_single_account_compliance(ACCOUNTS_CONFIG_FILE)
    log_compliance_banner()

    limits = httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20,
        keepalive_expiry=30.0
    )
    timeout = httpx.Timeout(
        connect=30.0,
        read=STREAMING_READ_TIMEOUT,
        write=30.0,
        pool=30.0
    )
    app.state.http_client = httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        follow_redirects=True
    )
    logger.info("Shared HTTP client created with connection pooling")

    # ==============================================================================
    # Build credentials.json from .env (single-entry, legacy mode always)
    # ACCOUNT_SYSTEM=true is blocked by validate_configuration().
    # We always recreate credentials.json from the single .env credential.
    # ==============================================================================
    creds_path = Path(ACCOUNTS_CONFIG_FILE)

    has_refresh_token = bool(REFRESH_TOKEN)
    has_creds_file = bool(KIRO_CREDS_FILE) and Path(KIRO_CREDS_FILE).expanduser().exists()
    has_cli_db = bool(KIRO_CLI_DB_FILE) and Path(KIRO_CLI_DB_FILE).expanduser().exists()

    def _add_env_overrides(entry: dict) -> None:
        profile_arn = os.getenv("PROFILE_ARN")
        if profile_arn:
            entry["profile_arn"] = profile_arn
        region = os.getenv("KIRO_REGION")
        if region:
            entry["region"] = region
        api_region = os.getenv("KIRO_API_REGION")
        if api_region:
            entry["api_region"] = api_region

    if has_refresh_token or has_creds_file or has_cli_db:
        logger.debug("Rebuilding credentials.json from single .env credential")
        credentials = []

        # Priority: SQLite DB > JSON file > refresh token (single entry only)
        if has_cli_db:
            entry = {"type": "sqlite", "path": KIRO_CLI_DB_FILE}
            _add_env_overrides(entry)
            credentials.append(entry)
        elif has_creds_file:
            entry = {"type": "json", "path": KIRO_CREDS_FILE}
            _add_env_overrides(entry)
            credentials.append(entry)
        elif has_refresh_token:
            entry = {"type": "refresh_token", "refresh_token": REFRESH_TOKEN}
            _add_env_overrides(entry)
            credentials.append(entry)

        # Safety: enforce single-entry before writing
        if len(credentials) > 1:
            credentials = credentials[:1]
            logger.warning("Compliance: truncated credentials to single entry.")

        with open(creds_path, 'w', encoding='utf-8') as f:
            json.dump(credentials, f, indent=2, ensure_ascii=False)

        logger.debug("credentials.json written (single account, compliant mode)")

    # ==============================================================================
    # Create AccountManager (single account)
    # ==============================================================================
    app.state.account_manager = AccountManager(
        credentials_file=ACCOUNTS_CONFIG_FILE,
        state_file=ACCOUNTS_STATE_FILE
    )

    await app.state.account_manager.load_credentials()
    await app.state.account_manager.load_state()

    # Compliance guard: reject if AccountManager loaded multiple accounts
    all_accounts = list(app.state.account_manager._accounts.keys())
    if len(all_accounts) > 1:
        raise RuntimeError(
            f"Compliance: AccountManager loaded {len(all_accounts)} accounts. "
            "Only 1 account is permitted. Check credentials.json."
        )

    app.state.account_system = False  # Multi-account system always disabled

    if not all_accounts:
        logger.error("No accounts configured in credentials.json")
        raise RuntimeError("No accounts configured in credentials.json")

    account_id = all_accounts[0]
    logger.info(f"Initializing single account: {account_id}")

    success = await app.state.account_manager._initialize_account(account_id)
    if not success:
        logger.error(f"Failed to initialize account: {account_id}. Check your credentials.")
        raise RuntimeError("Failed to initialize account")

    logger.info(f"Account initialized successfully: {account_id}")

    await app.state.account_manager._save_state()

    save_task = asyncio.create_task(
        app.state.account_manager.save_state_periodically()
    )

    logger.info("Gateway started in single-account compliance mode.")

    yield

    logger.info("Shutting down application...")

    save_task.cancel()
    try:
        await save_task
    except asyncio.CancelledError:
        pass

    await app.state.account_manager._save_state()
    logger.info("Final state saved")

    try:
        await app.state.http_client.aclose()
        logger.info("Shared HTTP client closed")
    except Exception as e:
        logger.warning(f"Error closing shared HTTP client: {e}")


# --- FastAPI Application ---
app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan
)


# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Debug Logger Middleware ---
app.add_middleware(DebugLoggerMiddleware)


# --- Validation Error Handler Registration ---
app.add_exception_handler(RequestValidationError, validation_exception_handler)


# --- Route Registration ---
app.include_router(openai_router)
app.include_router(anthropic_router)


# --- Uvicorn log config ---
UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "default": {
            "class": "main.InterceptHandler",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"{APP_TITLE} - {APP_DESCRIPTION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration Priority (highest to lowest):
  1. CLI arguments (--host, --port)
  2. Environment variables (SERVER_HOST, SERVER_PORT)
  3. Default values (0.0.0.0:8000)

Examples:
  python main.py                          # Use defaults or env vars
  python main.py --port 9000              # Override port only
  python main.py --host 127.0.0.1         # Local connections only
  python main.py -H 0.0.0.0 -p 8080       # Short form

  SERVER_PORT=9000 python main.py         # Via environment
  uvicorn main:app --port 9000            # Via uvicorn directly
        """
    )

    parser.add_argument(
        "-H", "--host",
        type=str,
        default=None,
        metavar="HOST",
        help=f"Server host address (default: {DEFAULT_SERVER_HOST}, env: SERVER_HOST)"
    )

    parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        metavar="PORT",
        help=f"Server port (default: {DEFAULT_SERVER_PORT}, env: SERVER_PORT)"
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {APP_VERSION}"
    )

    return parser.parse_args()


def resolve_server_config(args: argparse.Namespace) -> tuple[str, int]:
    if args.host is not None:
        final_host = args.host
        host_source = "CLI argument"
    elif SERVER_HOST != DEFAULT_SERVER_HOST:
        final_host = SERVER_HOST
        host_source = "environment variable"
    else:
        final_host = DEFAULT_SERVER_HOST
        host_source = "default"

    if args.port is not None:
        final_port = args.port
        port_source = "CLI argument"
    elif SERVER_PORT != DEFAULT_SERVER_PORT:
        final_port = SERVER_PORT
        port_source = "environment variable"
    else:
        final_port = DEFAULT_SERVER_PORT
        port_source = "default"

    logger.debug(f"Host: {final_host} (from {host_source})")
    logger.debug(f"Port: {final_port} (from {port_source})")

    return final_host, final_port


def print_startup_banner(host: str, port: int) -> None:
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    display_host = "localhost" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"

    print()
    print(f"  {WHITE}{BOLD}👻 {APP_TITLE} v{APP_VERSION}{RESET}")
    print(f"  {DIM}Single-account compliance mode enabled{RESET}")
    print()
    print(f"  {WHITE}Server running at:{RESET}")
    print(f"  {GREEN}{BOLD}➜  {url}{RESET}")
    print()
    print(f"  {DIM}API Docs:      {url}/docs{RESET}")
    print(f"  {DIM}Health Check:  {url}/health{RESET}")
    print()
    print(f"  {DIM}{'─' * 48}{RESET}")
    print(f"  {WHITE}Requires a valid personal Kiro subscription.{RESET}")
    print(f"  {DIM}Multi-account mode is disabled for ToS compliance.{RESET}")
    print(f"  {DIM}{'─' * 48}{RESET}")
    print()


# --- Entry Point ---
if __name__ == "__main__":
    import uvicorn

    args = parse_cli_args()
    validate_configuration()
    _warn_timeout_configuration()
    final_host, final_port = resolve_server_config(args)
    print_startup_banner(final_host, final_port)

    logger.info(f"Starting Uvicorn server on {final_host}:{final_port}...")

    uvicorn.run(
        "main:app",
        host=final_host,
        port=final_port,
        log_config=UVICORN_LOG_CONFIG,
    )
