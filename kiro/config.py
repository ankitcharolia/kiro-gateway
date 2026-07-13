"""Gateway configuration — all settings read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Version — sourced from package metadata which hatch-vcs populates from the
# most recent git tag (e.g. v1.2.0 → "1.2.0").  Falls back to "dev" when
# running directly from source without an installed package.
# ---------------------------------------------------------------------------
try:
    from importlib.metadata import version as _pkg_version
    APP_VERSION: str = _pkg_version("kiro-gateway")
except Exception:
    APP_VERSION = "dev"

# ---------------------------------------------------------------------------
# Auth / API-key
# ---------------------------------------------------------------------------
# KIRO_GATEWAY_API_KEY is the client auth secret clients must send as
# Bearer (OpenAI) or x-api-key (Anthropic).
KIRO_GATEWAY_API_KEY: str = os.environ.get("KIRO_GATEWAY_API_KEY", "test-proxy-key")

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

# Fallback model list advertised by ``GET /v1/models`` before a live list has
# been discovered from ``session/new``. kiro-cli reports the authoritative list
# (with dotted version IDs such as ``claude-sonnet-4.6``) on every session; that
# live list supersedes this fallback at runtime. Override with the KIRO_MODELS
# env var (comma-separated) if you need to pin a different default set.
_models_raw: str = os.environ.get(
    "KIRO_MODELS", "auto,claude-opus-4.8,claude-sonnet-4.6"
)
DEFAULT_KIRO_MODELS: List[str] = [m.strip() for m in _models_raw.split(",") if m.strip()]

# How to handle a requested model that is not in the live kiro-cli catalogue
# (issue #42). kiro-cli does not validate the model id on session/set_model — an
# unknown id silently leaves the session on its default model. To avoid silent
# wrong-model execution the gateway validates the requested id against the live
# ``availableModels`` catalogue:
#   * ``warn``   (default) — log a WARNING and fall back to the session default
#                (non-silent; never breaks an existing harness that sends a
#                non-matching default like ``gpt-4o``).
#   * ``strict`` — reject an unknown model with a 404 in the API's native error
#                shape.
#   * ``off``    — legacy behaviour: forward the id and stay silent.
# Validation is skipped when the catalogue has not been discovered yet (before
# the first session) since there is nothing to validate against.
_model_validation_raw: str = os.environ.get("MODEL_VALIDATION", "warn").lower()
MODEL_VALIDATION: str = (
    _model_validation_raw if _model_validation_raw in ("off", "warn", "strict") else "warn"
)

# Optional model-id aliases so a harness that hardcodes a foreign id (e.g.
# ``gpt-4o``) can be mapped to a real kiro-cli model instead of falling back to
# the session default. Format: comma-separated ``alias=target`` pairs, e.g.
# ``MODEL_ALIASES="gpt-4o=claude-sonnet-4.6,claude-3-5-sonnet=claude-sonnet-4.6"``.
# The alias is resolved before model validation and session/set_model. Empty by
# default (no aliasing). See issue #42 follow-up.
def _parse_model_aliases(raw: str) -> dict:
    aliases: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        alias, _, target = pair.partition("=")
        alias, target = alias.strip(), target.strip()
        if alias and target:
            aliases[alias] = target
    return aliases


MODEL_ALIASES: dict = _parse_model_aliases(os.environ.get("MODEL_ALIASES", ""))

# Whether the gateway enforces ``max_tokens`` itself by capping the output
# stream (kiro-cli does not honor it over ACP). Default false to preserve the
# historical "no cap" behaviour — set true to make max_tokens actually limit
# output (stops generation early; finish_reason=length). ``stop`` sequences are
# always enforced when a client supplies them (no flag needed). See issue #32.
ENFORCE_MAX_TOKENS: bool = os.environ.get("ENFORCE_MAX_TOKENS", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
# Accept both the canonical names (HOST/PORT) and the names used in .env /
# Docker artifacts (SERVER_HOST/SERVER_PORT). The SERVER_* names take
# precedence so a value set in docker-compose.yml / .env actually applies.
HOST: str = os.environ.get("SERVER_HOST") or os.environ.get("HOST") or "0.0.0.0"
PORT: int = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or "8000")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "info").lower()
DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Kiro / ACP
#
# KIRO_CLI_PATH is the canonical env var for the Kiro CLI binary. The
# KIRO_CLI_COMMAND alias is also accepted (used by the Docker image /
# docker-compose.yml). Set either to the binary name ("kiro-cli") or an
# absolute path ("/usr/local/bin/kiro-cli") when it is not on $PATH.
# ---------------------------------------------------------------------------
KIRO_CLI_PATH: str = (
    os.environ.get("KIRO_CLI_PATH")
    or os.environ.get("KIRO_CLI_COMMAND")
    or "kiro-cli"
)
ACP_TIMEOUT: int = int(os.environ.get("ACP_TIMEOUT", "120"))

# Maximum size (in bytes) of a single JSON-RPC line read from kiro-cli's
# stdout. ACP messages carry tool outputs and assistant text, which can be
# large during long agent turns (big file reads, diffs, long completions).
# asyncio's default StreamReader limit is only 64 KiB; an oversized line would
# make ``readline()`` raise and the message would be dropped, truncating or
# hanging the turn. Raise it generously. Override via ACP_STDIO_MAX_BYTES.
ACP_STDIO_MAX_BYTES: int = int(
    os.environ.get("ACP_STDIO_MAX_BYTES", str(16 * 1024 * 1024))
)

# When the kiro-cli agent requests permission to run a built-in tool
# (file edits, command execution, etc.) the gateway auto-approves a single
# invocation when this is true, otherwise it rejects the request. Disable
# (ACP_TRUST_TOOLS=false) to run the agent in a read/answer-only posture.
ACP_TRUST_TOOLS: bool = os.environ.get("ACP_TRUST_TOOLS", "true").lower() != "false"

# Whether to surface kiro-cli's OWN built-in tool activity (web search, file
# edits, command execution, …) to the OpenAI/Anthropic shims as executable
# ``tool_calls`` / ``tool_use`` blocks. Default false: kiro-cli is an
# autonomous agent that runs these tools itself and streams the final answer,
# so emitting them as client-executable tool calls breaks harnesses that
# validate tool names against their own registry ("unavailable tool") or that
# loop on ``finish_reason=tool_calls``. With this false the shims behave like a
# clean text endpoint and work with every harness; set true only for ACP-aware
# UIs that merely display tool activity. The ACP-native route (/acp/chat)
# always surfaces tool activity regardless, per the ACP contract.
ACP_SURFACE_TOOL_CALLS: bool = (
    os.environ.get("ACP_SURFACE_TOOL_CALLS", "false").lower() == "true"
)

# Whether to surface kiro-cli's reasoning/"thinking" output on the
# OpenAI/Anthropic shims in each API's native reasoning shape (OpenAI
# ``reasoning_content`` / Responses ``reasoning`` items; Anthropic ``thinking``
# content blocks). Default true: reasoning is additive (it never changes the
# final answer text) and lets reasoning-aware harnesses display it. Set false
# to drop reasoning and emit only the final answer. The ACP-native route always
# surfaces thinking as an ``acp_thinking`` event regardless.
ACP_SURFACE_THINKING: bool = (
    os.environ.get("ACP_SURFACE_THINKING", "true").lower() != "false"
)

# MCP servers registered on every ACP session via ``session/new``'s
# ``mcpServers`` field. This is the ONLY external-tool channel kiro-cli honors
# over ACP: it advertises ``mcpCapabilities.http: true`` and executes the MCP
# tools itself (the gateway never runs them — compliance is preserved). Verified
# against a live kiro-cli 2.12.1 probe: ``session/new`` accepts and processes a
# non-empty ``mcpServers`` list (an empty list returns instantly; a populated
# one drives kiro-cli's MCP setup), so the field is honored — the gateway must
# forward operator-configured servers instead of the hardcoded ``[]``.
#
# Two sources (checked in order; first non-empty wins):
#   * ``KIRO_MCP_SERVERS`` — inline JSON.
#   * ``KIRO_MCP_CONFIG``  — path to a JSON file.
# Each accepts either an ACP ``mcpServers`` array (used verbatim) or the common
# ``mcp.json`` object form (``{"mcpServers": {"<name>": {...}}}`` or a bare
# ``{"<name>": {...}}`` map), which is normalised to the array shape with the
# key injected as each entry's ``name``. Empty (default) leaves sessions with
# no MCP servers — behaviour is unchanged unless configured.
#
# HTTP transport is expected (``mcpCapabilities.http: true``, ``sse: false``);
# an HTTP entry looks like ``{"type": "http", "name": "...", "url": "...",
# "headers": [{"name": "...", "value": "..."}]}``. Entries are forwarded
# verbatim (faithful translation) — the gateway does not validate transport
# semantics; a misconfigured/unreachable server can make ``session/new`` block
# up to ``ACP_TIMEOUT``, so only configure reachable servers.
def _normalize_mcp_headers(headers: object) -> List[dict]:
    """Coerce MCP ``headers`` into the ACP ``[{"name","value"}]`` array shape.

    Verified against a live kiro-cli 2.12.1 probe: an HTTP MCP entry MUST carry
    ``headers`` as an **array** — omitting it, or sending the ``mcp.json`` object
    form (``{"Authorization": "Bearer …"}``), makes kiro-cli's ``session/new``
    silently **block** (deserialize failure, no error) up to the session
    timeout. Normalising here means an operator's object-style headers actually
    work instead of hanging.

    Args:
        headers: ``None``, a mapping (name→value), or an already-ACP array.

    Returns:
        A list of ``{"name", "value"}`` dicts (possibly empty).
    """
    if isinstance(headers, dict):
        return [{"name": str(k), "value": str(v)} for k, v in headers.items()]
    if isinstance(headers, list):
        out: List[dict] = []
        for item in headers:
            if isinstance(item, dict) and "name" in item:
                out.append({"name": str(item["name"]), "value": str(item.get("value", ""))})
        return out
    return []


def _normalize_mcp_entry(entry: dict) -> dict:
    """Normalise one MCP server entry into the shape kiro-cli accepts.

    A remote (``url``) entry is coerced to the ACP HTTP shape kiro-cli's
    ``session/new`` requires: ``type`` defaults to ``"http"`` (kiro-cli
    advertises ``mcpCapabilities.http: true``, ``sse: false``) and ``headers``
    is coerced to an ACP array (see :func:`_normalize_mcp_headers`) — both are
    mandatory or ``session/new`` blocks. A stdio (``command``) entry has its
    ``env`` map coerced to the ACP ``[{"name","value"}]`` array and ``args``
    defaulted; it is otherwise left intact (forward-compatible, though kiro-cli
    advertises no stdio transport today).

    Args:
        entry: A single server-config dict (already carries ``name``).

    Returns:
        The normalised entry.
    """
    normalized = dict(entry)
    if normalized.get("url"):
        transport = str(normalized.get("type") or "http").strip().lower()
        normalized["type"] = transport if transport in ("http", "sse") else "http"
        normalized["headers"] = _normalize_mcp_headers(normalized.get("headers"))
    elif normalized.get("command"):
        env = normalized.get("env")
        if isinstance(env, dict):
            normalized["env"] = [
                {"name": str(k), "value": str(v)} for k, v in env.items()
            ]
        elif not isinstance(env, list):
            normalized["env"] = []
        if not isinstance(normalized.get("args"), list):
            normalized["args"] = []
    return normalized


def _normalize_mcp_servers(parsed: object) -> List[dict]:
    """Normalise a parsed MCP config into an ACP ``mcpServers`` array.

    Args:
        parsed: The JSON-decoded config: an array of server dicts, an object
            with a top-level ``mcpServers`` key (array or name→config map), or a
            bare name→config map.

    Returns:
        A list of server-config dicts (each guaranteed to carry a ``name`` and
        the transport-specific fields kiro-cli requires), skipping malformed
        entries.
    """
    # Unwrap a {"mcpServers": ...} wrapper if present.
    if isinstance(parsed, dict) and "mcpServers" in parsed:
        parsed = parsed["mcpServers"]

    raw: List[dict] = []
    if isinstance(parsed, list):
        for entry in parsed:
            if isinstance(entry, dict) and entry.get("name"):
                raw.append(dict(entry))
    elif isinstance(parsed, dict):
        # name -> config map (mcp.json style).
        for name, cfg in parsed.items():
            if isinstance(cfg, dict):
                raw.append({"name": str(name), **cfg})
    return [_normalize_mcp_entry(entry) for entry in raw]


def _load_mcp_servers() -> List[dict]:
    """Load and normalise MCP server configs from env (inline JSON or a file).

    ``KIRO_MCP_SERVERS`` (inline JSON) takes precedence over ``KIRO_MCP_CONFIG``
    (a path to a JSON file). A parse/IO error is logged-safe (returns an empty
    list) so a bad config never prevents the gateway from starting.

    Returns:
        The normalised ``mcpServers`` array (possibly empty).
    """
    import json as _json

    inline = os.environ.get("KIRO_MCP_SERVERS", "").strip()
    if inline:
        try:
            return _normalize_mcp_servers(_json.loads(inline))
        except (ValueError, TypeError):
            return []

    path = os.environ.get("KIRO_MCP_CONFIG", "").strip()
    if path:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return _normalize_mcp_servers(_json.load(handle))
        except (OSError, ValueError, TypeError):
            return []

    return []


MCP_SERVERS: List[dict] = _load_mcp_servers()

# Bounded timeout (seconds) for ``session/new`` **when MCP servers are
# registered**. Verified against a live kiro-cli 2.12.1 probe: a correctly
# shaped, reachable MCP server makes ``session/new`` return in well under a
# second, but a malformed entry or an unreachable/slow server makes it **block**
# with no error. Since the gateway opens a fresh session per request, that would
# otherwise stall every request for the full ``ACP_TIMEOUT`` (default 120s).
# This shorter, dedicated cap makes a bad MCP setup fail fast with a clear
# timeout error instead. Sessions without MCP servers keep using ``ACP_TIMEOUT``
# unchanged. Raise it if a legitimate remote MCP server needs longer to
# initialise.
MCP_INIT_TIMEOUT: int = int(os.environ.get("MCP_INIT_TIMEOUT", "30"))

# Default working directory for ACP sessions. Coding agents may override this
# per-request via filesystem_roots; otherwise the gateway process cwd is used.
ACP_WORKSPACE_DIR: str = os.environ.get("ACP_WORKSPACE_DIR", os.getcwd())

# Optional ACP session "mode" (agent persona) to select on every session via
# session/set_mode. kiro-cli reports the available modes on session/new (e.g.
# ``kiro_default``, ``code``, ``kiro_planner``, ``kiro_guide``); a mode is the
# agent that answers the turn. Empty (default) leaves the session on kiro-cli's
# own default mode — behaviour is unchanged unless this is set. An unknown mode
# is accepted silently by kiro-cli (the session keeps its default), so a
# mis-set value never fails the turn.
ACP_MODE: str = os.environ.get("KIRO_ACP_MODE", "").strip()

# ---------------------------------------------------------------------------
# ACP subprocess spawn arguments (issue #53)
#
# ``kiro-cli acp`` accepts flags that let the caller pick the agent, initial
# model, thinking effort, and agent engine at launch. The gateway exposes each
# as an env knob and builds the argv deterministically in ACPClient.start().
# All are optional and additive: with nothing set the gateway spawns the same
# process as before, except the engine is pinned explicitly (see below).
#
# NOTE: KIRO_ACP_MODEL (this ``--model`` spawn flag, the *initial* session
# model) is distinct from KIRO_ACP_MODE (the agent persona selected per session
# via session/set_mode). The per-request model still overrides this default.
# ---------------------------------------------------------------------------
# --agent: name of a (custom) agent config to use for the first session.
ACP_AGENT: str = os.environ.get("KIRO_ACP_AGENT", "").strip()
# --model: model id to select when starting the first session.
ACP_MODEL: str = os.environ.get("KIRO_ACP_MODEL", "").strip()
# --effort: initial thinking effort level (low | medium | high | xhigh | max).
ACP_EFFORT: str = os.environ.get("KIRO_ACP_EFFORT", "").strip()
# --agent-engine: "v1" | "v2" | "v3". Pinned explicitly to v2 (the current
# kiro-cli default) so a future flip of the default engine cannot silently
# change the gateway's behaviour. v3 currently requires host-mediated auth
# that the gateway does not implement (see issue #52) — accepted syntactically
# but not usable yet.
_ACP_ENGINE_CHOICES = ("v1", "v2", "v3")
_acp_engine_raw = os.environ.get("KIRO_ACP_ENGINE", "v2").strip().lower()
ACP_ENGINE: str = _acp_engine_raw if _acp_engine_raw in _ACP_ENGINE_CHOICES else "v2"
# Escape hatch: extra raw args appended verbatim to the acp argv, parsed with
# shell-style quoting (e.g. KIRO_ACP_EXTRA_ARGS='--verbose --trust-tools fs_read').
ACP_EXTRA_ARGS: str = os.environ.get("KIRO_ACP_EXTRA_ARGS", "").strip()


# ---------------------------------------------------------------------------
# Settings object — exposes every constant as an attribute so callers can
# use either the module-level names (legacy) or `settings.<name>` (new style).
# ---------------------------------------------------------------------------
@dataclass
class _Settings:
    # Auth
    KIRO_GATEWAY_API_KEY: str = field(default_factory=lambda: KIRO_GATEWAY_API_KEY)

    # Compliance
    COMPLIANCE_MODE: bool = field(default_factory=lambda: COMPLIANCE_MODE)

    # Model
    DEFAULT_MODEL: str = field(default_factory=lambda: DEFAULT_MODEL)
    DEFAULT_MAX_TOKENS: int = field(default_factory=lambda: DEFAULT_MAX_TOKENS)
    DEFAULT_MAX_INPUT_TOKENS: int = field(default_factory=lambda: DEFAULT_MAX_INPUT_TOKENS)
    HIDDEN_MODELS: List[str] = field(default_factory=lambda: HIDDEN_MODELS)
    DEFAULT_KIRO_MODELS: List[str] = field(default_factory=lambda: DEFAULT_KIRO_MODELS)
    MODEL_VALIDATION: str = field(default_factory=lambda: MODEL_VALIDATION)
    MODEL_ALIASES: dict = field(default_factory=lambda: dict(MODEL_ALIASES))
    ENFORCE_MAX_TOKENS: bool = field(default_factory=lambda: ENFORCE_MAX_TOKENS)

    # Server
    HOST: str = field(default_factory=lambda: HOST)
    PORT: int = field(default_factory=lambda: PORT)
    SERVER_HOST: str = field(default_factory=lambda: HOST)
    SERVER_PORT: int = field(default_factory=lambda: PORT)
    LOG_LEVEL: str = field(default_factory=lambda: LOG_LEVEL)
    DEBUG: bool = field(default_factory=lambda: DEBUG)

    # Kiro / ACP
    KIRO_CLI_PATH: str = field(default_factory=lambda: KIRO_CLI_PATH)
    # Alias: some callers/tests refer to the CLI binary as KIRO_CLI_COMMAND.
    KIRO_CLI_COMMAND: str = field(default_factory=lambda: KIRO_CLI_PATH)
    ACP_TIMEOUT: int = field(default_factory=lambda: ACP_TIMEOUT)
    ACP_STDIO_MAX_BYTES: int = field(default_factory=lambda: ACP_STDIO_MAX_BYTES)
    ACP_TRUST_TOOLS: bool = field(default_factory=lambda: ACP_TRUST_TOOLS)
    ACP_SURFACE_TOOL_CALLS: bool = field(default_factory=lambda: ACP_SURFACE_TOOL_CALLS)
    ACP_SURFACE_THINKING: bool = field(default_factory=lambda: ACP_SURFACE_THINKING)
    MCP_SERVERS: List[dict] = field(default_factory=lambda: [dict(s) for s in MCP_SERVERS])
    MCP_INIT_TIMEOUT: int = field(default_factory=lambda: MCP_INIT_TIMEOUT)
    ACP_WORKSPACE_DIR: str = field(default_factory=lambda: ACP_WORKSPACE_DIR)
    ACP_MODE: str = field(default_factory=lambda: ACP_MODE)
    ACP_AGENT: str = field(default_factory=lambda: ACP_AGENT)
    ACP_MODEL: str = field(default_factory=lambda: ACP_MODEL)
    ACP_EFFORT: str = field(default_factory=lambda: ACP_EFFORT)
    ACP_ENGINE: str = field(default_factory=lambda: ACP_ENGINE)
    ACP_EXTRA_ARGS: str = field(default_factory=lambda: ACP_EXTRA_ARGS)

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

    # App version (from git tag via importlib.metadata)
    APP_VERSION: str = field(default_factory=lambda: APP_VERSION)


settings = _Settings()
