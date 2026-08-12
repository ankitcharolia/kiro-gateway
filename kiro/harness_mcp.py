"""Discover a *harness's own* MCP servers and forward them to kiro-cli.

Why this exists (issue #75)
---------------------------
A coding harness (Claude Code, OpenCode, Oh My Pi, Kilo Code, Cursor, …) lets
the user register MCP servers in its **own** config. Those servers never reach
the gateway over the wire: the OpenAI and Anthropic APIs have no MCP channel, so
the harness connects to MCP **itself** and flattens the resulting tools into the
request's ``tools`` array. Verified against live captures:

* **Claude Code** ``POST /v1/messages`` body keys are ``model``, ``messages``,
  ``system``, ``tools``, ``thinking``, … — **no** ``mcp_servers`` field and no
  MCP header. Its own MCP client performs ``initialize`` / ``tools/list``
  directly against the server.
* **OpenCode** ``POST /v1/chat/completions`` sends its MCP tool as an ordinary
  function: ``{"type": "function", "function": {"name":
  "probe75_kiro_probe_magic", …}}``.

Client-declared ``tools`` are ignored by kiro-cli over ACP (issue #31), so those
tools are simply unavailable — an OpenCode session whose MCP server is
configured answered ``TOOL_NOT_VISIBLE`` through the gateway.

The fix
-------
kiro-cli **does** honour MCP servers registered on ``session/new``, including
**stdio** servers. Verified against a live kiro-cli 2.17.0 probe: an entry of
``{"name", "command", "args", "env": []}`` produced an
``_kiro.dev/mcp/server_initialized`` notification, and both ``tools/list`` and
``tools/call`` reached the server process (the tool's marker came back in the
answer). This matters because most harness-configured MCP servers are stdio
(``npx -y some-mcp@latest``).

So instead of bridging tools back to the harness (which would require holding a
turn open across HTTP requests and make the gateway stateful), the gateway
**reads the harness's MCP config from disk** and registers the *same* servers on
``session/new``. kiro-cli then connects to them itself and executes the tools —
so **compliance is preserved** (the gateway never runs a tool) and the design
stays stateless.

Discovery is anchored on the per-request workspace already resolved by
:mod:`kiro.workspace` (``X-Kiro-Workspace`` header → ``filesystem_roots`` → the
prompt's ``<env>`` ``Working directory:`` line), so a harness running in a
project directory gets that project's MCP servers.

Security
--------
Discovery causes kiro-cli to **connect to servers, and spawn processes,** named
by a config file. It is **on by default** (``MCP_DISCOVERY=all``) so a harness's
MCP tools work with no configuration — the same servers the harness itself
already runs on the user's behalf. Set ``MCP_DISCOVERY`` only to narrow that:

* ``all`` (default) — user-level configs **and** workspace-level files.
* ``user`` — user-level configs under ``$HOME`` only
  (``~/.claude/settings.json``, ``~/.config/opencode/opencode.json``,
  ``~/.omp/agent/mcp.json``, …). Prefer this when harnesses open **untrusted
  repositories**: a workspace file such as ``<ws>/.mcp.json`` is controlled by
  whoever wrote the repo, so it can name a server kiro-cli will then launch.
* ``off`` — no discovery; only ``KIRO_MCP_SERVERS`` and kiro-cli's own config.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, List, Optional

from loguru import logger

from kiro.config import _normalize_mcp_entry, parse_mcp_servers, settings

# Recognised values for the ``MCP_DISCOVERY`` setting.
DISCOVERY_OFF = "off"
DISCOVERY_USER = "user"
DISCOVERY_ALL = "all"
_VALID_SCOPES = (DISCOVERY_OFF, DISCOVERY_USER, DISCOVERY_ALL)

# Discovery is enabled out of the box: a harness's own MCP servers should work
# without the operator configuring anything.
DISCOVERY_DEFAULT = DISCOVERY_ALL

# ``${VAR}``, ``${env:VAR}`` and ``$VAR`` placeholders used by harness configs
# (OpenCode writes ``"${PLAYWRIGHT_MCP_EXTENSION_TOKEN}"``; VS Code-style files
# use ``${env:TOKEN}``).
_ENV_PLACEHOLDER = re.compile(r"\$\{(?:env:)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)")

# Comment / trailing-comma tolerance for ``.jsonc`` style configs.
_LINE_COMMENT = re.compile(r"(?<![:\"'\\])//[^\n\"]*$", re.MULTILINE)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def normalize_scope(value: object) -> str:
    """Normalise a raw ``MCP_DISCOVERY`` value to a supported scope.

    Discovery is **on by default**, so an empty/unset value resolves to
    :data:`DISCOVERY_ALL`. Disabling is explicit (``off``/``false``/``0``/
    ``no``), and an unrecognised value falls back to the default rather than
    silently turning the feature off.

    Args:
        value: The raw configured value (any type; typically a string).

    Returns:
        One of ``"off"``, ``"user"`` or ``"all"``.
    """
    scope = str(value or "").strip().lower()
    if scope in _VALID_SCOPES:
        return scope
    if scope in ("false", "0", "no", "none", "disabled"):
        return DISCOVERY_OFF
    if scope in ("", "true", "1", "yes", "on"):
        return DISCOVERY_DEFAULT
    logger.warning(
        f"Unrecognised MCP_DISCOVERY value {value!r}; using default "
        f"'{DISCOVERY_DEFAULT}' (expected one of {', '.join(_VALID_SCOPES)})"
    )
    return DISCOVERY_DEFAULT


def _expand_env(value: str) -> str:
    """Expand ``${VAR}`` / ``${env:VAR}`` / ``$VAR`` from the gateway environment.

    Harness configs commonly store secrets as placeholders rather than literals.
    The harness expands them from its own environment; the gateway does the same
    so a forwarded server is usable. An unset variable expands to an empty
    string (matching shell semantics) rather than leaving the literal text.

    Args:
        value: A raw string that may contain placeholders.

    Returns:
        The string with any placeholders substituted.
    """
    def _sub(match: re.Match[str]) -> str:
        name = match.group("name") or match.group("bare")
        return os.environ.get(name, "")

    return _ENV_PLACEHOLDER.sub(_sub, value)


def _expand_tree(value: object) -> object:
    """Recursively expand env placeholders in every string of a JSON value.

    Args:
        value: Any JSON-decoded value.

    Returns:
        The same structure with string leaves expanded.
    """
    if isinstance(value, str):
        return _expand_env(value)
    if isinstance(value, list):
        return [_expand_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_tree(item) for key, item in value.items()}
    return value


def _load_json_tolerant(path: str) -> Optional[dict]:
    """Load a JSON/JSONC config file, tolerating comments and trailing commas.

    Args:
        path: Absolute path to the candidate config file.

    Returns:
        The decoded object, or ``None`` when the file is missing, unreadable,
        not valid JSON, or not a JSON object. Never raises — a broken harness
        config must not fail the request.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug(f"MCP discovery: cannot read {path}: {exc}")
        return None

    for attempt in (raw, _strip_jsonc(raw)):
        try:
            parsed = json.loads(attempt)
        except (ValueError, TypeError):
            continue
        return parsed if isinstance(parsed, dict) else None

    logger.debug(f"MCP discovery: {path} is not valid JSON; skipped")
    return None


def _strip_jsonc(raw: str) -> str:
    """Remove ``//`` and ``/* */`` comments plus trailing commas from JSON text.

    Args:
        raw: The raw file contents.

    Returns:
        A best-effort strict-JSON version of the input.
    """
    without = _BLOCK_COMMENT.sub("", raw)
    without = _LINE_COMMENT.sub("", without)
    return _TRAILING_COMMA.sub(r"\1", without)


def _is_disabled(cfg: dict) -> bool:
    """Report whether a harness marked this MCP server as disabled.

    Harnesses spell this differently: OpenCode uses ``enabled: false``, while
    Claude Code / ``mcp.json`` style configs use ``disabled: true``.

    Args:
        cfg: A single server config dict.

    Returns:
        ``True`` when the entry should be skipped.
    """
    if cfg.get("enabled") is False:
        return True
    return bool(cfg.get("disabled"))


def _entry_from_standard(name: str, cfg: dict) -> Optional[dict]:
    """Convert a standard ``mcp.json``-style entry to the ACP server shape.

    Covers Claude Code (``~/.claude/settings.json``, ``<ws>/.mcp.json``),
    Oh My Pi (``mcp.json`` / ``.mcp.json``) and the VS Code / Cursor variants:
    ``{"command": "npx", "args": [...], "env": {...}}`` for stdio, or
    ``{"type": "http", "url": ..., "headers": {...}}`` for remote.

    Args:
        name: The server's name (the config map key).
        cfg: The server's config object.

    Returns:
        A server dict ready for :func:`kiro.config._normalize_mcp_entry`, or
        ``None`` when the entry is disabled or carries neither a command nor a
        URL.
    """
    if not isinstance(cfg, dict) or _is_disabled(cfg):
        return None

    url = cfg.get("url") or cfg.get("serverUrl") or cfg.get("endpoint")
    if url:
        entry: dict = {"name": name, "url": str(url)}
        declared = str(cfg.get("type") or "").strip().lower()
        # kiro-cli advertises mcpCapabilities {http: true, sse: false}; keep an
        # explicit sse/http type and let config normalisation coerce the rest.
        if declared in ("http", "sse"):
            entry["type"] = declared
        if cfg.get("headers") is not None:
            entry["headers"] = cfg["headers"]
        return entry

    command = cfg.get("command")
    if command:
        # A few configs put the whole argv in ``command`` as a list.
        if isinstance(command, list):
            if not command:
                return None
            argv = [str(part) for part in command]
            entry = {"name": name, "command": argv[0], "args": argv[1:]}
        else:
            entry = {"name": name, "command": str(command)}
            args = cfg.get("args")
            if isinstance(args, list):
                entry["args"] = [str(a) for a in args]
        if isinstance(cfg.get("env"), dict):
            entry["env"] = cfg["env"]
        return entry

    return None


def _entry_from_opencode(name: str, cfg: dict) -> Optional[dict]:
    """Convert an OpenCode ``mcp`` block entry to the ACP server shape.

    OpenCode uses its own shape (verified from a live config):
    ``{"type": "local", "command": ["npx", "-y", "pkg"], "env": {...},
    "enabled": true}`` or ``{"type": "remote", "url": "...", "enabled": true}``.

    Args:
        name: The server's name (the ``mcp`` map key).
        cfg: The server's config object.

    Returns:
        A server dict ready for normalisation, or ``None`` when disabled or
        unrecognised.
    """
    if not isinstance(cfg, dict) or _is_disabled(cfg):
        return None

    kind = str(cfg.get("type") or "").strip().lower()
    if kind == "remote" or cfg.get("url"):
        url = cfg.get("url")
        if not url:
            return None
        entry: dict = {"name": name, "url": str(url)}
        if cfg.get("headers") is not None:
            entry["headers"] = cfg["headers"]
        return entry

    # ``local`` (stdio): command is an argv array.
    return _entry_from_standard(name, cfg)


def _collect(
    servers: dict,
    seen: set,
    source: str,
    mapping: object,
    converter: Callable[[str, dict], Optional[dict]],
) -> None:
    """Merge one config's server map into the accumulator, first-wins by name.

    Args:
        servers: Accumulator mapping name → server dict (mutated).
        seen: Names already claimed by a higher-precedence source (mutated).
        source: Human-readable origin, for logging.
        mapping: The raw ``name → config`` map from the file (validated here).
        converter: Shape-specific converter for this harness.
    """
    if not isinstance(mapping, dict):
        return
    for name, cfg in mapping.items():
        key = str(name)
        if not key or key in seen:
            continue
        entry = converter(key, cfg if isinstance(cfg, dict) else {})
        if entry is None:
            continue
        servers[key] = entry
        seen.add(key)
        logger.debug(f"MCP discovery: found '{key}' in {source}")


def _user_home() -> str:
    """Return the current user's home directory.

    Returns:
        The expanded home directory path (``~``).
    """
    return os.path.expanduser("~")


def _discover_user_level(servers: dict, seen: set) -> None:
    """Collect MCP servers from user-level harness configs under ``$HOME``.

    Args:
        servers: Accumulator mapping name → server dict (mutated).
        seen: Names already claimed (mutated).
    """
    home = _user_home()

    # Claude Code — global settings.
    claude_settings = os.path.join(home, ".claude", "settings.json")
    data = _load_json_tolerant(claude_settings)
    if data:
        _collect(servers, seen, claude_settings, data.get("mcpServers"),
                 _entry_from_standard)

    # Oh My Pi — user agent config.
    omp_mcp = os.path.join(home, ".omp", "agent", "mcp.json")
    data = _load_json_tolerant(omp_mcp)
    if data:
        _collect(servers, seen, omp_mcp,
                 data.get("mcpServers", data if "mcpServers" not in data else None),
                 _entry_from_standard)

    # OpenCode — global config (json and jsonc variants).
    for filename in ("opencode.json", "opencode.jsonc"):
        oc = os.path.join(home, ".config", "opencode", filename)
        data = _load_json_tolerant(oc)
        if data:
            _collect(servers, seen, oc, data.get("mcp"), _entry_from_opencode)

    # Generic user-level mcp.json (Kilo Code and others follow this).
    for rel in (
        os.path.join(".config", "kilo", "mcp.json"),
        os.path.join(".cursor", "mcp.json"),
    ):
        path = os.path.join(home, rel)
        data = _load_json_tolerant(path)
        if data:
            _collect(servers, seen, path, data.get("mcpServers", data),
                     _entry_from_standard)


def _discover_workspace_level(servers: dict, seen: set, workspace: str) -> None:
    """Collect MCP servers from workspace-level harness configs.

    Args:
        servers: Accumulator mapping name → server dict (mutated).
        seen: Names already claimed (mutated).
        workspace: Absolute path to the resolved harness workspace.
    """
    # Claude Code project config keyed by absolute path (``~/.claude.json``).
    claude_json = os.path.join(_user_home(), ".claude.json")
    data = _load_json_tolerant(claude_json)
    if data:
        projects = data.get("projects")
        if isinstance(projects, dict):
            project = projects.get(workspace)
            if isinstance(project, dict):
                _collect(servers, seen, f"{claude_json}:{workspace}",
                         project.get("mcpServers"), _entry_from_standard)
        _collect(servers, seen, claude_json, data.get("mcpServers"),
                 _entry_from_standard)

    # OpenCode project config.
    for filename in ("opencode.json", "opencode.jsonc"):
        path = os.path.join(workspace, filename)
        data = _load_json_tolerant(path)
        if data:
            _collect(servers, seen, path, data.get("mcp"), _entry_from_opencode)

    # Standard / Oh My Pi / VS Code / Cursor workspace files.
    for rel in (
        ".mcp.json",
        "mcp.json",
        os.path.join(".omp", "mcp.json"),
        os.path.join(".vscode", "mcp.json"),
        os.path.join(".cursor", "mcp.json"),
    ):
        path = os.path.join(workspace, rel)
        data = _load_json_tolerant(path)
        if not data:
            continue
        # VS Code uses "servers"; everything else uses "mcpServers" (or bare).
        mapping = data.get("mcpServers")
        if mapping is None:
            mapping = data.get("servers")
        if mapping is None:
            mapping = data
        _collect(servers, seen, path, mapping, _entry_from_standard)


def discover_harness_mcp_servers(
    workspace: Optional[str],
    scope: str = DISCOVERY_DEFAULT,
) -> List[dict]:
    """Discover the harness's own MCP servers for this request.

    Reads the MCP configs of the harnesses the gateway supports and returns them
    in the ACP ``session/new`` ``mcpServers`` shape, so kiro-cli connects to the
    **same** servers the harness uses. Entries are de-duplicated by name with
    workspace-level configs taking precedence over user-level ones.

    Args:
        workspace: The resolved absolute workspace directory for this request
            (from :mod:`kiro.workspace`), or ``None`` when unknown. Required for
            workspace-level discovery; user-level discovery works without it.
        scope: Discovery scope — ``"off"``, ``"user"`` or ``"all"``. See the
            module docstring for the security rationale.

    Returns:
        A list of normalised MCP server dicts (possibly empty). Never raises: a
        malformed or unreadable harness config is logged and skipped so a
        request is never failed by someone else's config file.
    """
    resolved_scope = normalize_scope(scope)
    if resolved_scope == DISCOVERY_OFF:
        return []

    servers: dict = {}
    seen: set = set()

    # Workspace-level first so a project config wins over a user-level one.
    if resolved_scope == DISCOVERY_ALL and workspace and os.path.isdir(workspace):
        try:
            _discover_workspace_level(servers, seen, workspace)
        except OSError as exc:
            logger.warning(f"MCP discovery: workspace scan failed for {workspace}: {exc}")

    try:
        _discover_user_level(servers, seen)
    except OSError as exc:
        logger.warning(f"MCP discovery: user-level scan failed: {exc}")

    if not servers:
        return []

    # Expand env placeholders, then apply the same normalisation the operator
    # config path uses (headers/env map → ACP arrays, type defaulting).
    normalized: List[dict] = []
    for entry in servers.values():
        expanded = _expand_tree(entry)
        if isinstance(expanded, dict):
            normalized.append(_normalize_mcp_entry(expanded))

    logger.info(
        f"MCP discovery ({resolved_scope}): forwarding "
        f"{len(normalized)} harness MCP server(s): "
        f"{[s.get('name') for s in normalized]}"
    )
    return normalized


def merge_mcp_servers(*groups: Optional[List[dict]]) -> List[dict]:
    """Merge MCP server lists, de-duplicating by name (earlier groups win).

    Used to combine the per-request list (header / body field), the discovered
    harness servers, and the operator-configured defaults into the single
    ``mcpServers`` array ``session/new`` accepts.

    Args:
        *groups: Server lists in descending precedence order. ``None`` and
            non-dict entries are ignored.

    Returns:
        The merged list, preserving first-seen order.
    """
    merged: List[dict] = []
    seen: set = set()
    for group in groups:
        for entry in group or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            merged.append(entry)
    return merged


def workspace_from_roots(filesystem_roots: object) -> Optional[str]:
    """Extract the resolved workspace directory from a request's roots.

    :func:`kiro.workspace.build_filesystem_roots` has already applied the
    ``X-Kiro-Workspace`` header → body ``filesystem_roots`` → prompt ``<env>``
    precedence, so its first entry is the request's workspace.

    Args:
        filesystem_roots: The list built for this request (``FilesystemRoot``
            models or plain dicts), or ``None``.

    Returns:
        The absolute directory path, or ``None`` when no root is present.
    """
    for root in filesystem_roots or []:
        path = getattr(root, "path", None)
        if path is None and isinstance(root, dict):
            path = root.get("path")
        if isinstance(path, str) and path:
            return path
    return None


def resolve_session_mcp_servers(
    header_value: Optional[str],
    body_value: object,
    filesystem_roots: object = None,
    scope: Optional[str] = None,
    operator_defaults: Optional[List[dict]] = None,
) -> Optional[List[dict]]:
    """Build the ``session/new`` ``mcpServers`` list for one request.

    Combines, in descending precedence:

    1. The per-request list — ``X-Kiro-MCP-Servers`` header or the request
       body's ``mcp_servers`` field (issue #75).
    2. The harness's **own** discovered MCP servers (``MCP_DISCOVERY``).
    3. The operator-configured defaults (``KIRO_MCP_SERVERS`` /
       ``KIRO_MCP_CONFIG``).

    Returns ``None`` when neither a per-request list nor a discovered server is
    present, which leaves :meth:`ACPClient.new_session` on its configured
    default — keeping behaviour byte-for-byte identical to before this feature
    whenever discovery is ``off`` and no header/body field is sent.

    Args:
        header_value: Raw ``X-Kiro-MCP-Servers`` header value, or ``None``.
        body_value: The request body's ``mcp_servers`` field, or ``None``.
        filesystem_roots: The request's resolved filesystem roots, used to
            anchor workspace-level discovery.
        scope: Discovery scope override; defaults to ``settings.MCP_DISCOVERY``.
        operator_defaults: Operator-configured servers; defaults to
            ``settings.MCP_SERVERS``.

    Returns:
        The merged server list, or ``None`` to keep the client default.
    """
    per_request = parse_mcp_servers(header_value or body_value or [])
    discovered = discover_harness_mcp_servers(
        workspace_from_roots(filesystem_roots),
        settings.MCP_DISCOVERY if scope is None else scope,
    )
    if not per_request and not discovered:
        return None
    defaults = settings.MCP_SERVERS if operator_defaults is None else operator_defaults
    return merge_mcp_servers(per_request, discovered, defaults)
