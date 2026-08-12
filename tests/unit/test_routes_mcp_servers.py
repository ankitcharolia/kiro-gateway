"""Route-level tests: per-request and discovered MCP servers reach ``session/new``.

Covers all three route families and both streaming modes, asserting the actual
``mcp_servers`` argument handed to :meth:`ACPClient.new_session` — the value that
becomes the ACP ``session/new`` ``mcpServers`` array kiro-cli acts on.

Two delivery channels exist (issue #75):

* explicit per-request — the ``X-Kiro-MCP-Servers`` header or an ``mcp_servers``
  body field, and
* **discovery** — the harness's own config read from disk, because no harness
  transmits its MCP configuration over the OpenAI/Anthropic wire.

``$HOME`` is isolated in every test so the developer's real harness config is
never read, and discovery is pinned explicitly rather than relying on the
ambient default.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from kiro.config import KIRO_GATEWAY_API_KEY
from kiro.harness_mcp import DISCOVERY_ALL, DISCOVERY_OFF

HEADERS_OAI = {"Authorization": f"Bearer {KIRO_GATEWAY_API_KEY}"}
HEADERS_ANTHROPIC = {"x-api-key": KIRO_GATEWAY_API_KEY}


@pytest.fixture()
def captured_mcp(monkeypatch, tmp_path):
    """Patch the ACP layer and capture the ``mcp_servers`` sent to session/new.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: pytest temporary directory (used to isolate ``$HOME``).

    Yields:
        A dict with a ``calls`` list collecting each ``mcp_servers`` argument.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    captured: dict = {"calls": []}

    async def _noop_start(self) -> None:
        self._proc = None
        self._reader_task = None

    async def _noop_stop(self) -> None:
        pass

    async def _noop_initialize(self, capabilities=None) -> None:
        pass

    async def _capture_new_session(self, capabilities=None, cwd=None, model=None,
                                   mode=None, mcp_servers=None) -> str:
        captured["calls"].append(mcp_servers)
        return "test-session-id"

    async def _mock_prompt(self, params) -> dict:
        return {"content": "ok", "tool_calls": [], "finish_reason": "stop",
                "usage": {}}

    async def _mock_prompt_stream(self, params):
        yield {"type": "text", "content": "ok"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    from main import app

    with (
        patch("kiro.acp_client.ACPClient.start", new=_noop_start),
        patch("kiro.acp_client.ACPClient.stop", new=_noop_stop),
        patch("kiro.acp_client.ACPClient.initialize", new=_noop_initialize),
        patch("kiro.acp_client.ACPClient.new_session", new=_capture_new_session),
        patch("kiro.acp_client.ACPClient.prompt", new=_mock_prompt),
        patch("kiro.acp_client.ACPClient.prompt_stream", new=_mock_prompt_stream),
    ):
        with TestClient(app) as client:
            captured["client"] = client
            # Drop the warm-up session's call so tests see only their request.
            captured["calls"].clear()
            yield captured


def _last(captured) -> list:
    """Return the most recent captured ``mcp_servers`` argument.

    Args:
        captured: The ``captured_mcp`` fixture value.

    Returns:
        The last captured value (list or ``None``).
    """
    assert captured["calls"], "session/new was never called"
    return captured["calls"][-1]


def _names(servers) -> list:
    """Extract server names from a captured list.

    Args:
        servers: The captured ``mcp_servers`` value.

    Returns:
        The list of names, or ``[]`` when ``None``.
    """
    return [s.get("name") for s in (servers or [])]


def _header(name: str, url: str = "http://127.0.0.1:9000/mcp") -> str:
    """Build an ``X-Kiro-MCP-Servers`` header value.

    Args:
        name: Server name.
        url: Server URL.

    Returns:
        The JSON string for the header.
    """
    return json.dumps([{"type": "http", "name": name, "url": url, "headers": []}])


def _write_workspace_config(tmp_path, name: str):
    """Create a workspace containing a Claude Code style ``.mcp.json``.

    Args:
        tmp_path: pytest temporary directory.
        name: The MCP server name to declare.

    Returns:
        The workspace directory path.
    """
    ws = tmp_path / "ws_disc"
    ws.mkdir(exist_ok=True)
    (ws / ".mcp.json").write_text(json.dumps({
        "mcpServers": {name: {"type": "http", "url": "http://127.0.0.1:9911/mcp"}}
    }), encoding="utf-8")
    return ws


# ---------------------------------------------------------------------------
# Explicit per-request MCP servers (header + body), both modes, all routes
# ---------------------------------------------------------------------------

class TestPerRequestMcpHeader:
    """The ``X-Kiro-MCP-Servers`` header reaches ``session/new`` on every route."""

    @pytest.mark.parametrize("stream", [False, True])
    def test_openai_chat_completions(self, captured_mcp, stream):
        headers = {**HEADERS_OAI, "X-Kiro-MCP-Servers": _header("oai-hdr")}
        resp = captured_mcp["client"].post("/v1/chat/completions", headers=headers,
                                           json={"model": "auto", "stream": stream,
                                                 "messages": [{"role": "user",
                                                               "content": "hi"}]})
        assert resp.status_code == 200
        assert "oai-hdr" in _names(_last(captured_mcp))

    @pytest.mark.parametrize("stream", [False, True])
    def test_anthropic_messages(self, captured_mcp, stream):
        headers = {**HEADERS_ANTHROPIC, "X-Kiro-MCP-Servers": _header("ant-hdr")}
        resp = captured_mcp["client"].post("/v1/messages", headers=headers,
                                           json={"model": "auto", "max_tokens": 64,
                                                 "stream": stream,
                                                 "messages": [{"role": "user",
                                                               "content": "hi"}]})
        assert resp.status_code == 200
        assert "ant-hdr" in _names(_last(captured_mcp))

    @pytest.mark.parametrize("stream", [False, True])
    def test_openai_responses(self, captured_mcp, stream):
        headers = {**HEADERS_OAI, "X-Kiro-MCP-Servers": _header("resp-hdr")}
        resp = captured_mcp["client"].post("/v1/responses", headers=headers,
                                           json={"model": "auto", "input": "hi",
                                                 "stream": stream})
        assert resp.status_code == 200
        assert "resp-hdr" in _names(_last(captured_mcp))

    @pytest.mark.parametrize("path", ["/acp/chat", "/acp/chat/stream"])
    def test_acp_routes(self, captured_mcp, path):
        """The native ACP route accepts MCP servers too (was missing entirely)."""
        headers = {"X-Kiro-MCP-Servers": _header("acp-hdr")}
        resp = captured_mcp["client"].post(path, headers=headers,
                                           json={"messages": [{"role": "user",
                                                               "content": "hi"}]})
        assert resp.status_code == 200
        assert "acp-hdr" in _names(_last(captured_mcp))


class TestPerRequestMcpBodyField:
    """The ``mcp_servers`` body field is honoured on every route."""

    def _body_entry(self, name: str) -> list:
        return [{"type": "http", "name": name, "url": "http://127.0.0.1:9000/mcp",
                 "headers": []}]

    def test_openai_chat_completions(self, captured_mcp):
        resp = captured_mcp["client"].post(
            "/v1/chat/completions", headers=HEADERS_OAI,
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}],
                  "mcp_servers": self._body_entry("oai-body")})
        assert resp.status_code == 200
        assert "oai-body" in _names(_last(captured_mcp))

    def test_anthropic_messages(self, captured_mcp):
        resp = captured_mcp["client"].post(
            "/v1/messages", headers=HEADERS_ANTHROPIC,
            json={"model": "auto", "max_tokens": 64,
                  "messages": [{"role": "user", "content": "hi"}],
                  "mcp_servers": self._body_entry("ant-body")})
        assert resp.status_code == 200
        assert "ant-body" in _names(_last(captured_mcp))

    def test_acp_chat(self, captured_mcp):
        resp = captured_mcp["client"].post(
            "/acp/chat",
            json={"messages": [{"role": "user", "content": "hi"}],
                  "mcp_servers": self._body_entry("acp-body")})
        assert resp.status_code == 200
        assert "acp-body" in _names(_last(captured_mcp))

    def test_header_takes_precedence_over_body(self, captured_mcp):
        headers = {**HEADERS_OAI, "X-Kiro-MCP-Servers": _header("from-header")}
        resp = captured_mcp["client"].post(
            "/v1/chat/completions", headers=headers,
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}],
                  "mcp_servers": self._body_entry("from-body")})
        assert resp.status_code == 200
        names = _names(_last(captured_mcp))
        assert "from-header" in names
        assert "from-body" not in names


# ---------------------------------------------------------------------------
# Discovered harness MCP servers (issue #75, the reported bug)
# ---------------------------------------------------------------------------

class TestDiscoveredHarnessMcp:
    """A harness's own MCP config is forwarded without any client cooperation."""

    def _env_prompt(self, workspace) -> str:
        """Mimic the ``<env>`` block harnesses embed to convey their cwd."""
        return (f"You are an agent.\n<env>\n  Working directory: {workspace}\n"
                f"</env>\n")

    @pytest.mark.parametrize("stream", [False, True])
    def test_openai_discovers_workspace_config(self, captured_mcp, tmp_path, stream):
        ws = _write_workspace_config(tmp_path, "disc-oai")
        with patch("kiro.harness_mcp.settings.MCP_DISCOVERY", DISCOVERY_ALL):
            resp = captured_mcp["client"].post(
                "/v1/chat/completions", headers=HEADERS_OAI,
                json={"model": "auto", "stream": stream, "messages": [
                    {"role": "system", "content": self._env_prompt(ws)},
                    {"role": "user", "content": "hi"}]})
        assert resp.status_code == 200
        assert "disc-oai" in _names(_last(captured_mcp))

    @pytest.mark.parametrize("stream", [False, True])
    def test_anthropic_discovers_workspace_config(self, captured_mcp, tmp_path,
                                                  stream):
        ws = _write_workspace_config(tmp_path, "disc-ant")
        with patch("kiro.harness_mcp.settings.MCP_DISCOVERY", DISCOVERY_ALL):
            resp = captured_mcp["client"].post(
                "/v1/messages", headers=HEADERS_ANTHROPIC,
                json={"model": "auto", "max_tokens": 64, "stream": stream,
                      "system": self._env_prompt(ws),
                      "messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 200
        assert "disc-ant" in _names(_last(captured_mcp))

    def test_workspace_header_anchors_discovery(self, captured_mcp, tmp_path):
        """``X-Kiro-Workspace`` pins the directory discovery reads from."""
        ws = _write_workspace_config(tmp_path, "disc-hdr")
        headers = {**HEADERS_OAI, "X-Kiro-Workspace": str(ws)}
        with patch("kiro.harness_mcp.settings.MCP_DISCOVERY", DISCOVERY_ALL):
            resp = captured_mcp["client"].post(
                "/v1/chat/completions", headers=headers,
                json={"model": "auto",
                      "messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 200
        assert "disc-hdr" in _names(_last(captured_mcp))

    def test_discovery_off_forwards_nothing(self, captured_mcp, tmp_path):
        """With discovery off the pre-existing behaviour is preserved exactly."""
        ws = _write_workspace_config(tmp_path, "should-not-appear")
        headers = {**HEADERS_OAI, "X-Kiro-Workspace": str(ws)}
        with patch("kiro.harness_mcp.settings.MCP_DISCOVERY", DISCOVERY_OFF):
            resp = captured_mcp["client"].post(
                "/v1/chat/completions", headers=headers,
                json={"model": "auto",
                      "messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 200
        # None means "use the client's configured default" (operator config).
        assert _last(captured_mcp) is None

    def test_per_request_and_discovered_are_combined(self, captured_mcp, tmp_path):
        ws = _write_workspace_config(tmp_path, "disc-both")
        headers = {**HEADERS_OAI, "X-Kiro-Workspace": str(ws),
                   "X-Kiro-MCP-Servers": _header("req-both")}
        with patch("kiro.harness_mcp.settings.MCP_DISCOVERY", DISCOVERY_ALL):
            resp = captured_mcp["client"].post(
                "/v1/chat/completions", headers=headers,
                json={"model": "auto",
                      "messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 200
        names = _names(_last(captured_mcp))
        assert "req-both" in names and "disc-both" in names
        # Per-request entries come first (higher precedence).
        assert names.index("req-both") < names.index("disc-both")

    @pytest.mark.parametrize("path", ["/acp/chat", "/acp/chat/stream"])
    def test_acp_routes_discover_from_filesystem_roots(self, captured_mcp, tmp_path,
                                                       path):
        ws = _write_workspace_config(tmp_path, "disc-acp")
        with patch("kiro.harness_mcp.settings.MCP_DISCOVERY", DISCOVERY_ALL):
            resp = captured_mcp["client"].post(
                path, json={"messages": [{"role": "user", "content": "hi"}],
                            "filesystem_roots": [{"path": str(ws)}]})
        assert resp.status_code == 200
        assert "disc-acp" in _names(_last(captured_mcp))


class TestMcpErrorHandling:
    """Malformed per-request input degrades gracefully instead of erroring."""

    def test_malformed_header_json_does_not_fail_request(self, captured_mcp):
        headers = {**HEADERS_OAI, "X-Kiro-MCP-Servers": "{not valid json"}
        with patch("kiro.harness_mcp.settings.MCP_DISCOVERY", DISCOVERY_OFF):
            resp = captured_mcp["client"].post(
                "/v1/chat/completions", headers=headers,
                json={"model": "auto",
                      "messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 200
        assert _last(captured_mcp) is None

    def test_empty_header_is_ignored(self, captured_mcp):
        headers = {**HEADERS_OAI, "X-Kiro-MCP-Servers": ""}
        with patch("kiro.harness_mcp.settings.MCP_DISCOVERY", DISCOVERY_OFF):
            resp = captured_mcp["client"].post(
                "/v1/chat/completions", headers=headers,
                json={"model": "auto",
                      "messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 200
        assert _last(captured_mcp) is None
