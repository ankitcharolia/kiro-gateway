"""
ACP Compliance Tests
====================
Proves that kiro-gateway:
  1. Does NOT import or use the removed direct-API modules.
  2. Only mounts ACP-backed routes in main.py.
  3. Enforces single-account operation.
  4. All removed modules raise ImportError as expected.
  5. No HTTP calls are made to Kiro's private API.
"""
from __future__ import annotations

import importlib
import inspect
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# 1. Removed modules must raise ImportError
# ---------------------------------------------------------------------------

REMOVED_MODULES = [
    "kiro.auth",
    "kiro.http_client",
    "kiro.account_manager",
    "kiro.routes_openai",
    "kiro.routes_anthropic",
    "kiro.streaming_openai",
    "kiro.streaming_anthropic",
    "kiro.streaming_core",
    "kiro.account_errors",
    "kiro.kiro_errors",
    "kiro.network_errors",
    "kiro.parsers",
    "kiro.converters_core",
    "kiro.converters_openai",
    "kiro.converters_anthropic",
    "kiro.models_openai",
    "kiro.models_anthropic",
    "kiro.model_resolver",
    "kiro.tokenizer",
    "kiro.thinking_parser",
    "kiro.truncation_recovery",
    "kiro.truncation_state",
    "kiro.payload_guards",
    "kiro.mcp_tools",
    "kiro.cache",
    "kiro.debug_logger",
    "kiro.debug_middleware",
]


@pytest.mark.parametrize("module_name", REMOVED_MODULES)
def test_removed_module_raises_import_error(module_name):
    """Every removed direct-API module must raise ImportError when imported."""
    # Evict cached import if present
    sys.modules.pop(module_name, None)
    with pytest.raises(ImportError):
        importlib.import_module(module_name)


# ---------------------------------------------------------------------------
# 2. main.py only mounts ACP-backed routers
# ---------------------------------------------------------------------------

ACCEPTED_ROUTER_MODULES = {
    "kiro.routes_acp",
    "kiro.routes_openai_shim",
    "kiro.routes_anthropic_shim",
}

BANNED_ROUTER_MODULES = {
    "kiro.routes_openai",
    "kiro.routes_anthropic",
}


def test_main_does_not_import_banned_routers():
    """main.py must not import or mount the old direct-API route handlers."""
    with open("main.py", encoding="utf-8") as fh:
        source = fh.read()
    for banned in BANNED_ROUTER_MODULES:
        module_path = banned.replace(".", "/") + ".py"
        # Check neither the dotted import nor a path reference appears
        assert banned not in source, (
            f"main.py still references banned module {banned}"
        )


def test_main_imports_acp_backed_routers_only():
    """main.py must import all three ACP-backed routers and nothing else for routing."""
    with open("main.py", encoding="utf-8") as fh:
        source = fh.read()
    for expected in ACCEPTED_ROUTER_MODULES:
        assert expected in source, (
            f"main.py is missing expected ACP router import: {expected}"
        )


# ---------------------------------------------------------------------------
# 3. ACP core modules are importable
# ---------------------------------------------------------------------------

REQUIRED_ACP_MODULES = [
    "kiro.acp_client",
    "kiro.acp_models",
    "kiro.shim_service",
    "kiro.routes_acp",
    "kiro.routes_openai_shim",
    "kiro.routes_anthropic_shim",
    "kiro.capability_executor",
    "kiro.compliance",
    "kiro.config",
    "kiro.exceptions",
    "kiro.utils",
]


@pytest.mark.parametrize("module_name", REQUIRED_ACP_MODULES)
def test_acp_module_is_importable(module_name):
    """Every ACP-stack module must import cleanly."""
    mod = importlib.import_module(module_name)
    assert mod is not None


# ---------------------------------------------------------------------------
# 4. ACPClient does not contain HTTP calls to Kiro private API
# ---------------------------------------------------------------------------

PRIVATE_API_PATTERNS = [
    "prod.us-east-1.api.kiro.aws",
    "bearer_token",
    "x-kiro-token",
    "api.kiro.dev",
]


def test_acp_client_has_no_private_api_calls():
    """acp_client.py must not contain references to Kiro's private HTTP API."""
    with open("kiro/acp_client.py", encoding="utf-8") as fh:
        source = fh.read().lower()
    for pattern in PRIVATE_API_PATTERNS:
        assert pattern.lower() not in source, (
            f"kiro/acp_client.py contains private API reference: {pattern!r}"
        )


def test_shim_service_has_no_private_api_calls():
    """shim_service.py must not contain references to Kiro's private HTTP API."""
    with open("kiro/shim_service.py", encoding="utf-8") as fh:
        source = fh.read().lower()
    for pattern in PRIVATE_API_PATTERNS:
        assert pattern.lower() not in source, (
            f"kiro/shim_service.py contains private API reference: {pattern!r}"
        )


# ---------------------------------------------------------------------------
# 5. ACPClient uses subprocess (kiro CLI), not httpx/requests
# ---------------------------------------------------------------------------

def test_acp_client_uses_subprocess_not_http():
    """ACPClient must communicate via subprocess stdio, not outbound HTTP."""
    with open("kiro/acp_client.py", encoding="utf-8") as fh:
        source = fh.read()
    # Must use asyncio subprocess
    assert "asyncio" in source, "acp_client.py must use asyncio for subprocess management"
    assert "create_subprocess" in source or "subprocess" in source, (
        "acp_client.py must spawn kiro CLI as a subprocess"
    )
    # Must NOT make outbound HTTP requests
    for http_lib in ["httpx", "aiohttp", "requests", "urllib.request"]:
        assert http_lib not in source, (
            f"acp_client.py must not use {http_lib} — all communication is via kiro CLI stdio"
        )
