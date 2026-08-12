"""Unit tests for :mod:`kiro.harness_mcp` (harness MCP server discovery).

A coding harness never sends its own MCP configuration over the OpenAI/Anthropic
wire — verified against live captures, Claude Code's ``/v1/messages`` body and
OpenCode's ``/v1/chat/completions`` body carry **no** MCP field, and OpenCode
flattens its MCP tool into an ordinary ``tools`` function entry, which kiro-cli
ignores (issue #31). The gateway therefore reads the harness's own config from
disk and registers the same servers on ``session/new``, where kiro-cli connects
to them and runs the tools itself (issue #75).

Every test isolates ``$HOME`` to a temporary directory so the developer's real
harness configuration is never read.
"""
from __future__ import annotations

import json

import pytest

from kiro.harness_mcp import (
    DISCOVERY_ALL,
    DISCOVERY_DEFAULT,
    DISCOVERY_OFF,
    DISCOVERY_USER,
    discover_harness_mcp_servers,
    merge_mcp_servers,
    normalize_scope,
    resolve_session_mcp_servers,
    workspace_from_roots,
)


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """Isolate ``$HOME`` so discovery cannot read the real user config.

    Args:
        tmp_path: pytest temporary directory.
        monkeypatch: pytest monkeypatch fixture.

    Returns:
        The temporary home directory path.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture()
def workspace(tmp_path):
    """Create an empty workspace directory for workspace-scoped configs.

    Args:
        tmp_path: pytest temporary directory.

    Returns:
        The workspace directory path.
    """
    ws = tmp_path / "project"
    ws.mkdir()
    return ws


def _write(path, payload) -> None:
    """Write ``payload`` as JSON (or raw text) to ``path``, creating parents.

    Args:
        path: Destination file path.
        payload: A JSON-serialisable object, or a ``str`` written verbatim.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")


def _names(servers) -> list:
    """Extract server names from a discovery result.

    Args:
        servers: The list returned by discovery.

    Returns:
        The list of ``name`` values.
    """
    return [s.get("name") for s in servers]


def _by_name(servers, name):
    """Find one server entry by name.

    Args:
        servers: The list returned by discovery.
        name: The server name to find.

    Returns:
        The matching dict, or ``None``.
    """
    return next((s for s in servers if s.get("name") == name), None)


# ---------------------------------------------------------------------------
# Scope handling
# ---------------------------------------------------------------------------

class TestNormalizeScopeSuccess:
    """Discovery is on by default; disabling is explicit."""

    def test_unset_enables_discovery_by_default(self):
        assert normalize_scope("") == DISCOVERY_DEFAULT
        assert normalize_scope(None) == DISCOVERY_DEFAULT

    def test_default_scope_is_all(self):
        assert DISCOVERY_DEFAULT == DISCOVERY_ALL

    @pytest.mark.parametrize("value", ["off", "false", "0", "no", "none", "disabled"])
    def test_explicit_disable_spellings(self, value):
        assert normalize_scope(value) == DISCOVERY_OFF

    @pytest.mark.parametrize("value", ["true", "1", "yes", "on"])
    def test_boolean_true_spellings_enable_default(self, value):
        assert normalize_scope(value) == DISCOVERY_DEFAULT

    @pytest.mark.parametrize("value", ["ALL", " user ", "Off"])
    def test_case_and_whitespace_insensitive(self, value):
        assert normalize_scope(value) in (DISCOVERY_ALL, DISCOVERY_USER, DISCOVERY_OFF)


class TestNormalizeScopeEdgeCases:
    """An unrecognised value falls back to the default rather than failing."""

    def test_unknown_value_falls_back_to_default(self):
        assert normalize_scope("bogus-value") == DISCOVERY_DEFAULT

    def test_non_string_value_does_not_raise(self):
        assert normalize_scope(42) == DISCOVERY_DEFAULT
        assert normalize_scope(object()) == DISCOVERY_DEFAULT


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------

class TestClaudeCodeDiscovery:
    """Claude Code stores servers under ``mcpServers`` in several locations."""

    def test_user_settings_stdio_server(self, fake_home):
        _write(fake_home / ".claude" / "settings.json", {
            "mcpServers": {
                "ctx": {"command": "npx", "args": ["-y", "ctx-mcp"],
                        "env": {"TOKEN": "abc"}}
            }
        })
        servers = discover_harness_mcp_servers(None, DISCOVERY_USER)
        entry = _by_name(servers, "ctx")
        assert entry is not None
        assert entry["command"] == "npx"
        assert entry["args"] == ["-y", "ctx-mcp"]
        # env is normalised to the ACP [{"name","value"}] array shape.
        assert entry["env"] == [{"name": "TOKEN", "value": "abc"}]

    def test_user_settings_http_server_gets_type_and_headers_array(self, fake_home):
        _write(fake_home / ".claude" / "settings.json", {
            "mcpServers": {
                "remote": {"type": "http", "url": "http://127.0.0.1:9000/mcp",
                           "headers": {"Authorization": "Bearer t"}}
            }
        })
        entry = _by_name(discover_harness_mcp_servers(None, DISCOVERY_USER), "remote")
        assert entry["type"] == "http"
        assert entry["url"] == "http://127.0.0.1:9000/mcp"
        assert entry["headers"] == [{"name": "Authorization", "value": "Bearer t"}]

    def test_workspace_mcp_json(self, fake_home, workspace):
        _write(workspace / ".mcp.json", {
            "mcpServers": {"proj": {"type": "http", "url": "http://localhost:1/mcp"}}
        })
        servers = discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL)
        assert "proj" in _names(servers)

    def test_project_scoped_servers_in_claude_json(self, fake_home, workspace):
        _write(fake_home / ".claude.json", {
            "projects": {
                str(workspace): {
                    "mcpServers": {"scoped": {"command": "scoped-mcp"}}
                },
                "/some/other/project": {
                    "mcpServers": {"other": {"command": "other-mcp"}}
                },
            }
        })
        names = _names(discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL))
        assert "scoped" in names
        # A different project's servers must not leak into this session.
        assert "other" not in names


# ---------------------------------------------------------------------------
# OpenCode
# ---------------------------------------------------------------------------

class TestOpenCodeDiscovery:
    """OpenCode uses an ``mcp`` block with ``local``/``remote`` entry types."""

    def test_local_command_array_is_split_into_command_and_args(self, fake_home):
        _write(fake_home / ".config" / "opencode" / "opencode.json", {
            "mcp": {
                "cdp": {"type": "local",
                        "command": ["npx", "-y", "chrome-devtools-mcp@latest"],
                        "enabled": True}
            }
        })
        entry = _by_name(discover_harness_mcp_servers(None, DISCOVERY_USER), "cdp")
        assert entry["command"] == "npx"
        assert entry["args"] == ["-y", "chrome-devtools-mcp@latest"]

    def test_remote_entry_becomes_http(self, fake_home):
        _write(fake_home / ".config" / "opencode" / "opencode.json", {
            "mcp": {"api": {"type": "remote", "url": "http://127.0.0.1:9911/mcp",
                            "enabled": True}}
        })
        entry = _by_name(discover_harness_mcp_servers(None, DISCOVERY_USER), "api")
        assert entry["type"] == "http"
        assert entry["headers"] == []

    def test_disabled_entry_is_skipped(self, fake_home):
        _write(fake_home / ".config" / "opencode" / "opencode.json", {
            "mcp": {
                "on": {"type": "local", "command": ["a"], "enabled": True},
                "off": {"type": "local", "command": ["b"], "enabled": False},
            }
        })
        names = _names(discover_harness_mcp_servers(None, DISCOVERY_USER))
        assert "on" in names
        assert "off" not in names


# ---------------------------------------------------------------------------
# Oh My Pi and other harnesses
# ---------------------------------------------------------------------------

class TestOtherHarnessDiscovery:
    """Oh My Pi and VS Code / Cursor style configs are recognised."""

    def test_omp_user_mcp_json(self, fake_home):
        _write(fake_home / ".omp" / "agent" / "mcp.json", {
            "mcpServers": {"omp-srv": {"command": "omp-mcp"}}
        })
        assert "omp-srv" in _names(
            discover_harness_mcp_servers(None, DISCOVERY_USER)
        )

    def test_omp_workspace_mcp_json(self, fake_home, workspace):
        _write(workspace / ".omp" / "mcp.json", {
            "mcpServers": {"ws-omp": {"command": "ws-mcp"}}
        })
        assert "ws-omp" in _names(
            discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL)
        )

    def test_vscode_servers_key(self, fake_home, workspace):
        _write(workspace / ".vscode" / "mcp.json", {
            "servers": {"code-srv": {"command": "code-mcp"}}
        })
        assert "code-srv" in _names(
            discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL)
        )

    def test_disabled_flag_variant_is_skipped(self, fake_home, workspace):
        _write(workspace / ".mcp.json", {
            "mcpServers": {"dead": {"command": "x", "disabled": True}}
        })
        assert _names(
            discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL)
        ) == []


# ---------------------------------------------------------------------------
# Scope enforcement and precedence
# ---------------------------------------------------------------------------

class TestScopeEnforcement:
    """``off`` disables everything; ``user`` excludes workspace files."""

    def test_off_returns_nothing_even_with_configs_present(self, fake_home, workspace):
        _write(fake_home / ".claude" / "settings.json",
               {"mcpServers": {"u": {"command": "a"}}})
        _write(workspace / ".mcp.json", {"mcpServers": {"w": {"command": "b"}}})
        assert discover_harness_mcp_servers(str(workspace), DISCOVERY_OFF) == []

    def test_user_scope_excludes_workspace_files(self, fake_home, workspace):
        _write(fake_home / ".claude" / "settings.json",
               {"mcpServers": {"u": {"command": "a"}}})
        _write(workspace / ".mcp.json", {"mcpServers": {"w": {"command": "b"}}})
        names = _names(discover_harness_mcp_servers(str(workspace), DISCOVERY_USER))
        assert names == ["u"]

    def test_all_scope_includes_both(self, fake_home, workspace):
        _write(fake_home / ".claude" / "settings.json",
               {"mcpServers": {"u": {"command": "a"}}})
        _write(workspace / ".mcp.json", {"mcpServers": {"w": {"command": "b"}}})
        names = _names(discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL))
        assert set(names) == {"u", "w"}

    def test_workspace_wins_on_name_collision(self, fake_home, workspace):
        _write(fake_home / ".claude" / "settings.json",
               {"mcpServers": {"dup": {"command": "user-level"}}})
        _write(workspace / ".mcp.json",
               {"mcpServers": {"dup": {"command": "workspace-level"}}})
        servers = discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL)
        assert len(servers) == 1
        assert servers[0]["command"] == "workspace-level"


# ---------------------------------------------------------------------------
# Parsing robustness
# ---------------------------------------------------------------------------

class TestEnvExpansion:
    """Harness configs store secrets as placeholders, not literals."""

    def test_brace_placeholder_expanded(self, fake_home, monkeypatch):
        monkeypatch.setenv("MY_MCP_TOKEN", "s3cret")
        _write(fake_home / ".claude" / "settings.json", {
            "mcpServers": {"s": {"command": "x", "env": {"T": "${MY_MCP_TOKEN}"}}}
        })
        entry = _by_name(discover_harness_mcp_servers(None, DISCOVERY_USER), "s")
        assert entry["env"] == [{"name": "T", "value": "s3cret"}]

    def test_vscode_env_prefix_placeholder_expanded(self, fake_home, monkeypatch):
        monkeypatch.setenv("VS_TOKEN", "vvv")
        _write(fake_home / ".claude" / "settings.json", {
            "mcpServers": {"s": {"command": "x", "env": {"T": "${env:VS_TOKEN}"}}}
        })
        entry = _by_name(discover_harness_mcp_servers(None, DISCOVERY_USER), "s")
        assert entry["env"] == [{"name": "T", "value": "vvv"}]

    def test_unset_placeholder_becomes_empty_string(self, fake_home, monkeypatch):
        monkeypatch.delenv("DEFINITELY_UNSET_MCP_VAR", raising=False)
        _write(fake_home / ".claude" / "settings.json", {
            "mcpServers": {"s": {"command": "x",
                                 "env": {"T": "${DEFINITELY_UNSET_MCP_VAR}"}}}
        })
        entry = _by_name(discover_harness_mcp_servers(None, DISCOVERY_USER), "s")
        assert entry["env"] == [{"name": "T", "value": ""}]


class TestParsingErrors:
    """A broken harness config is skipped, never fatal to the request."""

    def test_malformed_json_is_skipped(self, fake_home):
        _write(fake_home / ".claude" / "settings.json", "{ this is not json ")
        assert discover_harness_mcp_servers(None, DISCOVERY_USER) == []

    def test_jsonc_comments_and_trailing_commas_tolerated(self, fake_home, workspace):
        _write(workspace / ".mcp.json", """
        {
          // a line comment
          /* and a block comment */
          "mcpServers": {
            "j": { "command": "jsonc-mcp", },
          },
        }
        """)
        assert "j" in _names(
            discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL)
        )

    def test_missing_files_produce_no_servers(self, fake_home, workspace):
        assert discover_harness_mcp_servers(str(workspace), DISCOVERY_ALL) == []

    def test_nonexistent_workspace_is_ignored(self, fake_home):
        assert discover_harness_mcp_servers("/nonexistent/dir/xyz",
                                            DISCOVERY_ALL) == []

    def test_entry_without_command_or_url_is_skipped(self, fake_home):
        _write(fake_home / ".claude" / "settings.json",
               {"mcpServers": {"empty": {"description": "no transport"}}})
        assert discover_harness_mcp_servers(None, DISCOVERY_USER) == []

    def test_non_object_server_config_does_not_raise(self, fake_home):
        _write(fake_home / ".claude" / "settings.json",
               {"mcpServers": {"weird": "just-a-string", "ok": {"command": "c"}}})
        assert _names(discover_harness_mcp_servers(None, DISCOVERY_USER)) == ["ok"]


# ---------------------------------------------------------------------------
# Merging and the per-request resolver
# ---------------------------------------------------------------------------

class TestMergeMcpServers:
    """Earlier groups win; entries are de-duplicated by name."""

    def test_earlier_group_wins(self):
        merged = merge_mcp_servers(
            [{"name": "a", "url": "first"}],
            [{"name": "a", "url": "second"}, {"name": "b", "url": "x"}],
        )
        assert merged == [{"name": "a", "url": "first"}, {"name": "b", "url": "x"}]

    def test_none_groups_and_non_dicts_ignored(self):
        merged = merge_mcp_servers(None, ["bogus", 42, {"name": "a"}], None)
        assert merged == [{"name": "a"}]

    def test_entry_without_name_skipped(self):
        assert merge_mcp_servers([{"url": "no-name"}]) == []

    def test_empty_input_returns_empty_list(self):
        assert merge_mcp_servers() == []


class TestWorkspaceFromRoots:
    """The resolved workspace is taken from the request's filesystem roots."""

    def test_reads_path_from_model(self):
        from kiro.acp_models import FilesystemRoot
        assert workspace_from_roots([FilesystemRoot(path="/tmp")]) == "/tmp"

    def test_reads_path_from_dict(self):
        assert workspace_from_roots([{"path": "/var"}]) == "/var"

    def test_empty_or_none_returns_none(self):
        assert workspace_from_roots([]) is None
        assert workspace_from_roots(None) is None

    def test_skips_entries_without_path(self):
        assert workspace_from_roots([{"nope": 1}, {"path": "/srv"}]) == "/srv"


class TestResolveSessionMcpServers:
    """Precedence: per-request > discovered harness > operator defaults."""

    def test_returns_none_when_nothing_configured(self, fake_home):
        # No header, no body field, no discoverable config -> keep the client
        # default so behaviour is unchanged from before this feature.
        assert resolve_session_mcp_servers(None, None, [], scope=DISCOVERY_ALL,
                                          operator_defaults=[]) is None

    def test_header_only(self, fake_home):
        header = json.dumps([{"type": "http", "name": "h",
                              "url": "http://x/mcp", "headers": []}])
        result = resolve_session_mcp_servers(header, None, [],
                                            scope=DISCOVERY_OFF,
                                            operator_defaults=[])
        assert _names(result) == ["h"]

    def test_body_field_only(self, fake_home):
        body = [{"type": "http", "name": "b", "url": "http://y/mcp", "headers": []}]
        result = resolve_session_mcp_servers(None, body, [],
                                            scope=DISCOVERY_OFF,
                                            operator_defaults=[])
        assert _names(result) == ["b"]

    def test_discovered_servers_included(self, fake_home, workspace):
        _write(workspace / ".mcp.json",
               {"mcpServers": {"disc": {"command": "d"}}})
        result = resolve_session_mcp_servers(
            None, None, [{"path": str(workspace)}],
            scope=DISCOVERY_ALL, operator_defaults=[],
        )
        assert _names(result) == ["disc"]

    def test_per_request_precedes_discovered_and_operator(self, fake_home, workspace):
        _write(workspace / ".mcp.json",
               {"mcpServers": {"dup": {"command": "from-workspace"}}})
        header = json.dumps([{"name": "dup", "url": "http://per-request/mcp"}])
        result = resolve_session_mcp_servers(
            header, None, [{"path": str(workspace)}],
            scope=DISCOVERY_ALL,
            operator_defaults=[{"name": "dup", "url": "http://operator/mcp"}],
        )
        assert len(result) == 1
        assert result[0]["url"] == "http://per-request/mcp"

    def test_operator_defaults_are_preserved_alongside_discovery(
        self, fake_home, workspace
    ):
        _write(workspace / ".mcp.json",
               {"mcpServers": {"disc": {"command": "d"}}})
        result = resolve_session_mcp_servers(
            None, None, [{"path": str(workspace)}],
            scope=DISCOVERY_ALL,
            operator_defaults=[{"name": "op", "url": "http://op/mcp"}],
        )
        # Discovery must not silently drop the operator's own servers.
        assert set(_names(result)) == {"disc", "op"}

    def test_discovery_off_with_no_request_list_keeps_client_default(
        self, fake_home, workspace
    ):
        _write(workspace / ".mcp.json",
               {"mcpServers": {"disc": {"command": "d"}}})
        assert resolve_session_mcp_servers(
            None, None, [{"path": str(workspace)}],
            scope=DISCOVERY_OFF,
            operator_defaults=[{"name": "op"}],
        ) is None
