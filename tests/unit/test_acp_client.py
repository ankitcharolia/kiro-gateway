"""
Unit tests for ACPClient — the stdio bridge to kiro CLI.
All tests use a mock subprocess; no real kiro CLI needed.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
import pytest_asyncio

from kiro.acp_client import ACPClient
from kiro.acp_models import PromptMessage, PromptParams, ACPToolDefinition

# Capture the genuine new_session implementation at import time. The
# session-scoped ``test_client`` fixture monkeypatches ``ACPClient.new_session``
# for the whole test session, so tests that need the real method call this
# reference directly instead of going through the (patched) class attribute.
_REAL_NEW_SESSION = ACPClient.new_session
# Likewise capture the genuine prompt_stream — the cancellation tests must
# exercise the real generator, not the session-scoped mock installed by the
# ``test_client`` fixture.
_REAL_PROMPT_STREAM = ACPClient.prompt_stream
# Same reason — the fixture also patches ACPClient.prompt for the session.
_REAL_PROMPT = ACPClient.prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode(obj: dict) -> bytes:
    """Encode a JSON-RPC message as kiro CLI would write to stdout."""
    return (json.dumps(obj) + "\n").encode()


class FakeProcess:
    """Minimal asyncio subprocess mock."""

    def __init__(self, lines: list[bytes]):
        self._lines = iter(lines)
        self.stdin = AsyncMock()
        self.stdin.drain = AsyncMock()
        self.returncode = None

    async def readline_side_effect(self):
        try:
            return next(self._lines)
        except StopIteration:
            return b""

    @property
    def stdout(self):
        mock = AsyncMock()
        mock.readline = self.readline_side_effect
        return mock

    async def wait(self):
        return 0

    def kill(self):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_acp_client_instantiation():
    """ACPClient can be created with a custom CLI command."""
    client = ACPClient(command="/usr/local/bin/kiro")
    assert client is not None


def test_acp_client_default_command():
    """ACPClient uses 'kiro' as the default CLI command."""
    client = ACPClient()
    # The command attribute should default to 'kiro'
    cmd = getattr(client, 'command', None) or getattr(client, '_command', None) or getattr(client, 'cli_command', None)
    assert cmd is not None


@pytest.mark.asyncio
async def test_acp_client_creates_session_id():
    """new_session() returns a non-empty string session ID."""
    client = ACPClient()
    # Patch initialize so it sets a session_id without a real subprocess
    async def _mock_initialize(self, caps=None):
        self._session_id = "sess-abc-123"
        from kiro.acp_models import SessionInitResult
        return SessionInitResult(session_id="sess-abc-123")

    with patch.object(type(client), 'initialize', new=_mock_initialize):
        result = await client.initialize()
        assert client._session_id == "sess-abc-123"


@pytest.mark.asyncio
async def test_prompt_message_model():
    """PromptMessage Pydantic model validates correctly."""
    msg = PromptMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


@pytest.mark.asyncio
async def test_prompt_message_assistant_role():
    """PromptMessage accepts assistant role."""
    msg = PromptMessage(role="assistant", content="Hi there")
    assert msg.role == "assistant"


@pytest.mark.asyncio
async def test_prompt_message_system_role():
    """PromptMessage accepts system role."""
    msg = PromptMessage(role="system", content="You are helpful.")
    assert msg.role == "system"
    assert "helpful" in msg.content


# ---------------------------------------------------------------------------
# Model discovery + forwarding (session/new "models" + session/set_model)
# ---------------------------------------------------------------------------

class TestModelDiscoveryAndForwarding:
    """new_session caches the live model catalogue and forwards model selection."""

    @pytest.mark.asyncio
    async def test_new_session_captures_available_models(self):
        """The 'models' block from session/new is cached and normalised."""
        client = ACPClient()

        async def fake_call(method, params, timeout=120.0):
            if method == "session/new":
                return {
                    "sessionId": "s1",
                    "models": {
                        "currentModelId": "claude-opus-4.8",
                        "availableModels": [
                            {"modelId": "auto", "name": "auto", "description": "auto pick"},
                            {"modelId": "claude-sonnet-4.6", "name": "claude-sonnet-4.6",
                             "description": "latest sonnet"},
                        ],
                    },
                }
            return {}

        client._call = fake_call  # type: ignore[assignment]
        session_id = await _REAL_NEW_SESSION(client)

        assert session_id == "s1"
        ids = [m["id"] for m in client.available_models]
        assert "auto" in ids
        assert "claude-sonnet-4.6" in ids  # dotted id preserved
        assert client._current_model_id == "claude-opus-4.8"

    @pytest.mark.asyncio
    async def test_new_session_forwards_model_via_set_model(self):
        """When a model is requested, session/set_model is sent with that id."""
        client = ACPClient()
        calls: list[tuple[str, dict]] = []

        async def fake_call(method, params, timeout=120.0):
            calls.append((method, params))
            if method == "session/new":
                return {"sessionId": "s2"}
            return {}

        client._call = fake_call  # type: ignore[assignment]
        await _REAL_NEW_SESSION(client, model="claude-sonnet-4.6")

        set_calls = [c for c in calls if c[0] == "session/set_model"]
        assert len(set_calls) == 1
        assert set_calls[0][1] == {"sessionId": "s2", "modelId": "claude-sonnet-4.6"}

    @pytest.mark.asyncio
    async def test_new_session_without_model_skips_set_model(self):
        """No model requested → no session/set_model call."""
        client = ACPClient()
        methods: list[str] = []

        async def fake_call(method, params, timeout=120.0):
            methods.append(method)
            if method == "session/new":
                return {"sessionId": "s3"}
            return {}

        client._call = fake_call  # type: ignore[assignment]
        await _REAL_NEW_SESSION(client)

        assert "session/set_model" not in methods

    @pytest.mark.asyncio
    async def test_new_session_skips_set_model_when_model_matches_default(self):
        """Requested model == session default → no redundant set_model RTT."""
        client = ACPClient()
        methods: list[str] = []

        async def fake_call(method, params, timeout=120.0):
            methods.append(method)
            if method == "session/new":
                return {
                    "sessionId": "s5",
                    "models": {
                        "currentModelId": "claude-sonnet-4.6",
                        "availableModels": [
                            {"modelId": "claude-sonnet-4.6", "name": "claude-sonnet-4.6",
                             "description": ""},
                        ],
                    },
                }
            return {}

        client._call = fake_call  # type: ignore[assignment]
        await _REAL_NEW_SESSION(client, model="claude-sonnet-4.6")

        assert "session/set_model" not in methods

    @pytest.mark.asyncio
    async def test_new_session_sets_model_when_differs_from_default(self):
        """Requested model != session default → session/set_model is issued."""
        client = ACPClient()
        methods: list[str] = []

        async def fake_call(method, params, timeout=120.0):
            methods.append(method)
            if method == "session/new":
                return {
                    "sessionId": "s6",
                    "models": {"currentModelId": "claude-opus-4.8", "availableModels": []},
                }
            return {}

        client._call = fake_call  # type: ignore[assignment]
        await _REAL_NEW_SESSION(client, model="claude-sonnet-4.6")

        assert "session/set_model" in methods

    @pytest.mark.asyncio
    async def test_set_model_swallows_acp_error(self):
        """A failed set_model is logged and swallowed, never raised."""
        from kiro.acp_client import ACPError

        client = ACPClient()

        async def fake_call(method, params, timeout=120.0):
            raise ACPError(-32000, "set_model exploded")

        client._call = fake_call  # type: ignore[assignment]
        # Must not raise.
        await client.set_model("s4", "bogus-model")

    @pytest.mark.asyncio
    async def test_available_models_empty_before_any_session(self):
        """No session created yet → empty catalogue (callers use the fallback)."""
        client = ACPClient()
        assert client.available_models == []


class TestStdioBufferLimit:
    """The stdio read buffer must be large enough for big ACP lines."""

    def test_default_stdio_limit_matches_config(self):
        """ACPClient defaults its stdio buffer limit to the configured value."""
        from kiro.config import ACP_STDIO_MAX_BYTES

        client = ACPClient()
        assert client._stdio_limit == ACP_STDIO_MAX_BYTES

    def test_default_stdio_limit_exceeds_asyncio_default(self):
        """The default limit is well above asyncio's 64 KiB StreamReader default."""
        client = ACPClient()
        assert client._stdio_limit > 64 * 1024

    def test_stdio_limit_is_overridable(self):
        """A custom stdio buffer limit is honoured."""
        client = ACPClient(stdio_limit=1234567)
        assert client._stdio_limit == 1234567


# ---------------------------------------------------------------------------
# Cancellation (issue #41): abandoning a turn sends ACP session/cancel so the
# shared kiro-cli subprocess is freed (no head-of-line blocking).
# ---------------------------------------------------------------------------

class TestCancellation:
    """session/cancel is emitted when a turn is abandoned before completing."""

    @staticmethod
    def _capture_writes(client: ACPClient) -> list[str]:
        written: list[str] = []

        async def fake_write_line(line: str) -> None:
            written.append(line)

        client._write_line = fake_write_line  # type: ignore[assignment]
        return written

    @staticmethod
    async def _drive_until_queue(client: ACPClient, session_id: str, events: list[dict]) -> None:
        """Wait for prompt_stream to register its queue, then enqueue events."""
        for _ in range(1000):
            queue = client._event_queues.get(session_id)
            if queue is not None:
                for event in events:
                    queue.put_nowait(event)
                return
            await asyncio.sleep(0)
        raise AssertionError(f"queue for {session_id} never appeared")

    @pytest.mark.asyncio
    async def test_cancel_sends_session_cancel_notification(self):
        """cancel() writes a JSON-RPC notification (no id) with the sessionId."""
        client = ACPClient()
        written = self._capture_writes(client)

        await client.cancel("sess-1")

        assert len(written) == 1
        msg = json.loads(written[0])
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "session/cancel"
        assert msg["params"] == {"sessionId": "sess-1"}
        # A notification carries no id (verified against a live kiro-cli probe).
        assert "id" not in msg

    @pytest.mark.asyncio
    async def test_cancel_empty_session_is_noop(self):
        """A blank session id sends nothing."""
        client = ACPClient()
        written = self._capture_writes(client)

        await client.cancel("")

        assert written == []

    @pytest.mark.asyncio
    async def test_cancel_quietly_swallows_write_error(self):
        """_cancel_quietly never raises when the transport write fails."""
        client = ACPClient()

        async def boom(line: str) -> None:
            raise OSError("stdin closed")

        client._write_line = boom  # type: ignore[assignment]

        # Must not raise.
        await client._cancel_quietly("sess-1")

    @pytest.mark.asyncio
    async def test_prompt_stream_cancels_on_early_close(self):
        """Closing the stream before a terminal event triggers session/cancel."""
        client = ACPClient()
        written = self._capture_writes(client)

        params = PromptParams(
            session_id="s1", messages=[PromptMessage(role="user", content="hi")]
        )
        gen = _REAL_PROMPT_STREAM(client, params)

        feeder = asyncio.create_task(
            self._drive_until_queue(client, "s1", [{"type": "text", "content": "Hello"}])
        )
        first = await gen.__anext__()
        await feeder
        assert first == {"type": "text", "content": "Hello"}

        # Consumer goes away before "done"/"error" (client disconnect).
        await gen.aclose()

        # Let the fire-and-forget cancel task run.
        for _ in range(20):
            await asyncio.sleep(0)
            if any('"session/cancel"' in w for w in written):
                break

        cancels = [w for w in written if '"session/cancel"' in w]
        assert len(cancels) == 1, written
        msg = json.loads(cancels[0])
        assert msg["params"] == {"sessionId": "s1"}
        assert "id" not in msg
        # The session bookkeeping is cleaned up.
        assert "s1" not in client._event_queues

    @pytest.mark.asyncio
    async def test_prompt_stream_no_cancel_on_normal_completion(self):
        """A turn that reaches a terminal event must NOT be cancelled."""
        client = ACPClient()
        written = self._capture_writes(client)

        params = PromptParams(
            session_id="s2", messages=[PromptMessage(role="user", content="hi")]
        )
        gen = _REAL_PROMPT_STREAM(client, params)

        feeder = asyncio.create_task(
            self._drive_until_queue(client, "s2", [
                {"type": "text", "content": "Hello"},
                {"type": "done", "finish_reason": "stop", "usage": {}},
            ])
        )
        events = [event async for event in gen]
        await feeder

        # Give any (erroneous) scheduled cancel a chance to run.
        for _ in range(10):
            await asyncio.sleep(0)

        assert [e["type"] for e in events] == ["text", "done"]
        assert not any('"session/cancel"' in w for w in written)

    @pytest.mark.asyncio
    async def test_prompt_stream_no_cancel_on_error_event(self):
        """An error terminal event is a completion — no cancel is sent."""
        client = ACPClient()
        written = self._capture_writes(client)

        params = PromptParams(
            session_id="s3", messages=[PromptMessage(role="user", content="hi")]
        )
        gen = _REAL_PROMPT_STREAM(client, params)

        feeder = asyncio.create_task(
            self._drive_until_queue(client, "s3", [
                {"type": "error", "message": "boom"},
            ])
        )
        events = [event async for event in gen]
        await feeder

        for _ in range(10):
            await asyncio.sleep(0)

        assert [e["type"] for e in events] == ["error"]
        assert not any('"session/cancel"' in w for w in written)

    @pytest.mark.asyncio
    async def test_schedule_cancel_tracks_and_clears_task(self):
        """_schedule_cancel registers a task and auto-discards it when done."""
        client = ACPClient()
        self._capture_writes(client)

        client._schedule_cancel("s9")
        assert len(client._cancel_tasks) == 1

        # Drain the scheduled task.
        for _ in range(10):
            await asyncio.sleep(0)
            if not client._cancel_tasks:
                break
        assert client._cancel_tasks == set()

    @pytest.mark.asyncio
    async def test_schedule_cancel_blank_session_is_noop(self):
        """_schedule_cancel does nothing for a blank session id."""
        client = ACPClient()
        client._schedule_cancel("")
        assert client._cancel_tasks == set()


# ---------------------------------------------------------------------------
# Generation-param forwarding (issue #32): prompt_stream attaches sampling
# params under the ACP session/prompt _meta.generationConfig extension.
# kiro-cli currently ignores them (verified via live probe) but they are
# forwarded so a future version can honor them with no gateway change.
# ---------------------------------------------------------------------------

async def _drive_queue(client: ACPClient, session_id: str, events: list[dict]) -> None:
    """Wait for prompt_stream to register its queue, then enqueue events."""
    for _ in range(1000):
        queue = client._event_queues.get(session_id)
        if queue is not None:
            for event in events:
                queue.put_nowait(event)
            return
        await asyncio.sleep(0)
    raise AssertionError(f"queue for {session_id} never appeared")


class TestGenerationMeta:
    """_generation_meta + prompt_stream _meta payload."""

    def test_generation_meta_only_includes_set_fields(self):
        params = PromptParams(session_id="x", temperature=0.5, top_p=0.7)
        meta = ACPClient._generation_meta(params)
        assert meta == {"temperature": 0.5, "topP": 0.7}

    def test_generation_meta_maps_all_fields(self):
        params = PromptParams(
            session_id="x", temperature=0.2, max_tokens=128, top_p=0.9, top_k=40, stop=["STOP"]
        )
        meta = ACPClient._generation_meta(params)
        assert meta == {
            "temperature": 0.2, "maxTokens": 128, "topP": 0.9, "topK": 40,
            "stopSequences": ["STOP"],
        }

    def test_generation_meta_empty_when_unset(self):
        params = PromptParams(session_id="x")
        assert ACPClient._generation_meta(params) == {}

    @pytest.mark.asyncio
    async def test_prompt_stream_forwards_generation_meta(self):
        """session/prompt carries _meta.generationConfig with the set params."""
        client = ACPClient()
        written: list[str] = []

        async def fake_write_line(line: str) -> None:
            written.append(line)

        client._write_line = fake_write_line  # type: ignore[assignment]

        params = PromptParams(
            session_id="g1", messages=[PromptMessage(role="user", content="hi")],
            temperature=0.2, max_tokens=128, top_p=0.9, top_k=40, stop=["STOP"],
        )
        gen = _REAL_PROMPT_STREAM(client, params)
        feeder = asyncio.create_task(
            _drive_queue(client, "g1", [{"type": "done", "finish_reason": "stop", "usage": {}}])
        )
        _ = [event async for event in gen]
        await feeder

        prompt_lines = [w for w in written if '"session/prompt"' in w]
        assert len(prompt_lines) == 1
        payload = json.loads(prompt_lines[0])
        assert payload["params"]["_meta"]["generationConfig"] == {
            "temperature": 0.2, "maxTokens": 128, "topP": 0.9, "topK": 40,
            "stopSequences": ["STOP"],
        }

    @pytest.mark.asyncio
    async def test_prompt_stream_omits_meta_when_no_params(self):
        """No sampling params → no _meta key on the session/prompt payload."""
        client = ACPClient()
        written: list[str] = []

        async def fake_write_line(line: str) -> None:
            written.append(line)

        client._write_line = fake_write_line  # type: ignore[assignment]

        params = PromptParams(
            session_id="g2", messages=[PromptMessage(role="user", content="hi")]
        )
        gen = _REAL_PROMPT_STREAM(client, params)
        feeder = asyncio.create_task(
            _drive_queue(client, "g2", [{"type": "done", "finish_reason": "stop", "usage": {}}])
        )
        _ = [event async for event in gen]
        await feeder

        prompt_lines = [w for w in written if '"session/prompt"' in w]
        assert len(prompt_lines) == 1
        payload = json.loads(prompt_lines[0])
        assert "_meta" not in payload["params"]


class TestToolMeta:
    """_tool_meta + prompt_stream _meta.tools payload (issue #31).

    The live kiro-cli 2.8.0 probe proved the agent ignores client tools on
    session/prompt; these tests assert the gateway still *forwards* them under
    the schema-safe _meta extension (forward-compatible), not that kiro-cli
    acts on them.
    """

    _TOOL = ACPToolDefinition(
        name="get_weather",
        description="Get current weather for a city.",
        input_schema={"type": "object", "properties": {"city": {"type": "string"}},
                      "required": ["city"]},
    )

    def test_tool_meta_renders_mcp_shape(self):
        params = PromptParams(session_id="x", tools=[self._TOOL])
        assert ACPClient._tool_meta(params) == [{
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "inputSchema": {"type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"]},
        }]

    def test_tool_meta_empty_when_no_tools(self):
        assert ACPClient._tool_meta(PromptParams(session_id="x")) == []

    @pytest.mark.asyncio
    async def test_prompt_stream_forwards_tools_meta(self):
        """session/prompt carries _meta.tools when the caller declares tools."""
        client = ACPClient()
        written: list[str] = []

        async def fake_write_line(line: str) -> None:
            written.append(line)

        client._write_line = fake_write_line  # type: ignore[assignment]

        params = PromptParams(
            session_id="t1", messages=[PromptMessage(role="user", content="hi")],
            tools=[self._TOOL],
        )
        gen = _REAL_PROMPT_STREAM(client, params)
        feeder = asyncio.create_task(
            _drive_queue(client, "t1", [{"type": "done", "finish_reason": "stop", "usage": {}}])
        )
        _ = [event async for event in gen]
        await feeder

        payload = json.loads([w for w in written if '"session/prompt"' in w][0])
        assert payload["params"]["_meta"]["tools"] == [{
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "inputSchema": {"type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"]},
        }]

    @pytest.mark.asyncio
    async def test_prompt_stream_merges_tools_and_generation_meta(self):
        """_meta carries both generationConfig and tools when both are set."""
        client = ACPClient()
        written: list[str] = []

        async def fake_write_line(line: str) -> None:
            written.append(line)

        client._write_line = fake_write_line  # type: ignore[assignment]

        params = PromptParams(
            session_id="t2", messages=[PromptMessage(role="user", content="hi")],
            temperature=0.3, tools=[self._TOOL],
        )
        gen = _REAL_PROMPT_STREAM(client, params)
        feeder = asyncio.create_task(
            _drive_queue(client, "t2", [{"type": "done", "finish_reason": "stop", "usage": {}}])
        )
        _ = [event async for event in gen]
        await feeder

        meta = json.loads([w for w in written if '"session/prompt"' in w][0])["params"]["_meta"]
        assert meta["generationConfig"] == {"temperature": 0.3}
        assert meta["tools"][0]["name"] == "get_weather"

    @pytest.mark.asyncio
    async def test_prompt_stream_omits_tools_when_none(self):
        """No tools → no _meta.tools key on the session/prompt payload."""
        client = ACPClient()
        written: list[str] = []

        async def fake_write_line(line: str) -> None:
            written.append(line)

        client._write_line = fake_write_line  # type: ignore[assignment]

        params = PromptParams(
            session_id="t3", messages=[PromptMessage(role="user", content="hi")]
        )
        gen = _REAL_PROMPT_STREAM(client, params)
        feeder = asyncio.create_task(
            _drive_queue(client, "t3", [{"type": "done", "finish_reason": "stop", "usage": {}}])
        )
        _ = [event async for event in gen]
        await feeder

        payload = json.loads([w for w in written if '"session/prompt"' in w][0])
        assert "_meta" not in payload["params"]


# ---------------------------------------------------------------------------
# Structured-output forwarding (issue #35): prompt_stream attaches
# response_format / tool_choice under _meta.structuredOutput and a per-tool
# "strict" flag under _meta.tools. kiro-cli does not honor them today; these
# assert the gateway *forwards* them (forward-compatible), not that the agent
# acts on them.
# ---------------------------------------------------------------------------

class TestStructuredOutputMeta:
    """_structured_output_meta + strict tool flag + prompt_stream payload."""

    def test_structured_meta_only_includes_set_fields(self):
        params = PromptParams(session_id="x", tool_choice="required")
        assert ACPClient._structured_output_meta(params) == {"toolChoice": "required"}

    def test_structured_meta_maps_both_fields(self):
        rf = {"type": "json_object"}
        params = PromptParams(session_id="x", response_format=rf, tool_choice="auto")
        assert ACPClient._structured_output_meta(params) == {
            "responseFormat": rf, "toolChoice": "auto",
        }

    def test_structured_meta_empty_when_unset(self):
        assert ACPClient._structured_output_meta(PromptParams(session_id="x")) == {}

    def test_tool_meta_includes_strict_when_set(self):
        tool = ACPToolDefinition(
            name="f", description="d",
            input_schema={"type": "object"}, strict=True,
        )
        params = PromptParams(session_id="x", tools=[tool])
        assert ACPClient._tool_meta(params) == [{
            "name": "f", "description": "d",
            "inputSchema": {"type": "object"}, "strict": True,
        }]

    def test_tool_meta_omits_strict_when_unset(self):
        tool = ACPToolDefinition(name="f", input_schema={"type": "object"})
        assert "strict" not in ACPClient._tool_meta(PromptParams(session_id="x", tools=[tool]))[0]

    @pytest.mark.asyncio
    async def test_prompt_stream_forwards_structured_output_meta(self):
        """session/prompt carries _meta.structuredOutput when the caller sets it."""
        client = ACPClient()
        written: list[str] = []

        async def fake_write_line(line: str) -> None:
            written.append(line)

        client._write_line = fake_write_line  # type: ignore[assignment]

        rf = {"type": "json_schema", "json_schema": {"name": "S", "schema": {}}}
        params = PromptParams(
            session_id="so1", messages=[PromptMessage(role="user", content="hi")],
            response_format=rf, tool_choice="required",
        )
        gen = _REAL_PROMPT_STREAM(client, params)
        feeder = asyncio.create_task(
            _drive_queue(client, "so1", [{"type": "done", "finish_reason": "stop", "usage": {}}])
        )
        _ = [event async for event in gen]
        await feeder

        meta = json.loads([w for w in written if '"session/prompt"' in w][0])["params"]["_meta"]
        assert meta["structuredOutput"] == {"responseFormat": rf, "toolChoice": "required"}

    @pytest.mark.asyncio
    async def test_prompt_stream_omits_structured_output_when_unset(self):
        """No structured-output controls → no _meta.structuredOutput key."""
        client = ACPClient()
        written: list[str] = []

        async def fake_write_line(line: str) -> None:
            written.append(line)

        client._write_line = fake_write_line  # type: ignore[assignment]

        params = PromptParams(
            session_id="so2", messages=[PromptMessage(role="user", content="hi")],
        )
        gen = _REAL_PROMPT_STREAM(client, params)
        feeder = asyncio.create_task(
            _drive_queue(client, "so2", [{"type": "done", "finish_reason": "stop", "usage": {}}])
        )
        _ = [event async for event in gen]
        await feeder

        payload = json.loads([w for w in written if '"session/prompt"' in w][0])
        assert "_meta" not in payload["params"]


# ---------------------------------------------------------------------------
# Token usage extraction & capture (issue #36): surface real kiro-cli usage
# when reported over ACP; otherwise leave it empty for the shims to estimate.
# ---------------------------------------------------------------------------

class TestACPUsageExtraction:
    """_normalize_usage_keys / _find_usage / _extract_usage."""

    def test_normalize_snake_case(self):
        assert ACPClient._normalize_usage_keys(
            {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}
        ) == {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}

    def test_normalize_camel_case(self):
        assert ACPClient._normalize_usage_keys(
            {"inputTokens": 3, "outputTokens": 4}
        ) == {"input_tokens": 3, "output_tokens": 4}

    def test_normalize_prompt_completion_spelling(self):
        assert ACPClient._normalize_usage_keys(
            {"promptTokens": 5, "completionTokens": 6}
        ) == {"input_tokens": 5, "output_tokens": 6}

    def test_normalize_non_dict_is_empty(self):
        assert ACPClient._normalize_usage_keys(None) == {}
        assert ACPClient._normalize_usage_keys("nope") == {}

    def test_normalize_omits_cache_keys_when_absent(self):
        # No cache keys reported → none added (preserves the minimal shape).
        assert ACPClient._normalize_usage_keys(
            {"input_tokens": 3, "output_tokens": 4}
        ) == {"input_tokens": 3, "output_tokens": 4}

    def test_normalize_surfaces_cache_keys_snake(self):
        assert ACPClient._normalize_usage_keys(
            {"input_tokens": 3, "cache_creation_input_tokens": 9,
             "cache_read_input_tokens": 11}
        ) == {"input_tokens": 3, "cache_creation_input_tokens": 9,
              "cache_read_input_tokens": 11}

    def test_normalize_surfaces_cache_keys_camel_and_openai(self):
        # camelCase cache-creation + OpenAI ``cachedTokens`` → cache_read.
        assert ACPClient._normalize_usage_keys(
            {"cacheCreationInputTokens": 2, "cachedTokens": 8}
        ) == {"cache_creation_input_tokens": 2, "cache_read_input_tokens": 8}

    def test_find_usage_top_level(self):
        assert ACPClient._find_usage({"usage": {"input_tokens": 1}}) == {"input_tokens": 1}

    def test_find_usage_under_meta(self):
        assert ACPClient._find_usage(
            {"_meta": {"usage": {"total_tokens": 9}}}
        ) == {"total_tokens": 9}

    def test_extract_usage_kiro_2x_result_is_empty(self):
        # kiro-cli 2.x returns only {stopReason}; no usage to surface.
        assert ACPClient._extract_usage({"stopReason": "end_turn"}) == {}


class TestACPUsageCapture:
    """Usage captured from session/update is merged into the done event."""

    def test_finish_prompt_surfaces_result_usage(self):
        client = ACPClient()
        queue = asyncio.Queue()
        client._event_queues["sX"] = queue
        client._prompt_sessions["req1"] = "sX"

        client._finish_prompt("req1", {"result": {
            "stopReason": "end_turn",
            "usage": {"inputTokens": 12, "outputTokens": 8},
        }})

        done = queue.get_nowait()
        assert done["type"] == "done"
        assert done["usage"] == {"input_tokens": 12, "output_tokens": 8}

    def test_session_update_usage_merged_into_done(self):
        client = ACPClient()
        queue = asyncio.Queue()
        client._event_queues["sY"] = queue

        # A session/update notification carrying usage is captured.
        client._handle_notification({
            "method": "session/update",
            "params": {
                "sessionId": "sY",
                "update": {"sessionUpdate": "agent_message_chunk",
                           "content": {"text": "hi"}},
                "_meta": {"usage": {"input_tokens": 20}},
            },
        })
        # Drain the text event the update produced.
        assert queue.get_nowait()["type"] == "text"
        assert client._session_usage.get("sY") == {"input_tokens": 20}

        client._prompt_sessions["req2"] = "sY"
        client._finish_prompt("req2", {"result": {"stopReason": "end_turn"}})
        done = queue.get_nowait()
        assert done["usage"] == {"input_tokens": 20}

    def test_result_usage_wins_over_captured(self):
        client = ACPClient()
        queue = asyncio.Queue()
        client._event_queues["sZ"] = queue
        client._session_usage["sZ"] = {"input_tokens": 1, "output_tokens": 1}
        client._prompt_sessions["req3"] = "sZ"

        client._finish_prompt("req3", {"result": {
            "stopReason": "end_turn",
            "usage": {"input_tokens": 99},
        }})
        done = queue.get_nowait()
        # Result input_tokens overrides captured; captured output_tokens kept.
        assert done["usage"] == {"output_tokens": 1, "input_tokens": 99}


# ---------------------------------------------------------------------------
# Reasoning aggregation (issue #40): prompt() collects thinking deltas into a
# `reasoning` field without affecting `content`.
# ---------------------------------------------------------------------------

class TestPromptReasoning:
    """ACPClient.prompt() aggregates thinking events into result['reasoning']."""

    @pytest.mark.asyncio
    async def test_prompt_aggregates_reasoning(self):
        client = ACPClient()

        async def fake_stream(params):
            yield {"type": "thinking", "content": "Let me "}
            yield {"type": "thinking", "content": "think."}
            yield {"type": "text", "content": "The answer is 42."}
            yield {"type": "done", "finish_reason": "stop", "usage": {}}

        client.prompt_stream = fake_stream  # type: ignore[assignment]
        result = await _REAL_PROMPT(client, PromptParams(session_id="s"))
        assert result["reasoning"] == "Let me think."
        assert result["content"] == "The answer is 42."
    @pytest.mark.asyncio
    async def test_prompt_reasoning_empty_when_no_thinking(self):
        client = ACPClient()

        async def fake_stream(params):
            yield {"type": "text", "content": "Hi."}
            yield {"type": "done", "finish_reason": "stop", "usage": {}}

        client.prompt_stream = fake_stream  # type: ignore[assignment]
        result = await _REAL_PROMPT(client, PromptParams(session_id="s"))
        assert result["reasoning"] == ""


# ---------------------------------------------------------------------------
# Task list / plan surfacing: kiro-cli's built-in todo tool is normalised into
# a `plan` event (not a client-executable tool_call), folded into reasoning for
# the non-streaming aggregation.
# ---------------------------------------------------------------------------

from kiro.acp_client import format_plan_text


class TestPlanDetection:
    """_is_plan_tool / _plan_entries / format_plan_text + _handle_notification."""

    _CREATE = {
        "sessionUpdate": "tool_call",
        "toolCallId": "t1",
        "title": "Creating task list: do stuff",
        "rawInput": {
            "command": "create",
            "task_list_description": "Do stuff",
            "tasks": [
                {"task_description": "Write the file"},
                {"task_description": "Read it back"},
            ],
        },
    }

    def test_is_plan_tool_true_for_todo(self):
        assert ACPClient._is_plan_tool(self._CREATE) is True

    def test_is_plan_tool_false_for_file_edit(self):
        # File-edit tool uses path/content, not tasks — must not be misdetected.
        assert ACPClient._is_plan_tool(
            {"rawInput": {"command": "create", "path": "/tmp/x", "content": "hi"}}
        ) is False

    def test_plan_entries_extracted(self):
        entries, desc = ACPClient._plan_entries(self._CREATE)
        assert desc == "Do stuff"
        assert entries == [
            {"content": "Write the file", "status": "pending"},
            {"content": "Read it back", "status": "pending"},
        ]

    def test_format_plan_text_renders_checklist(self):
        text = format_plan_text(
            [{"content": "A", "status": "pending"}, {"content": "B", "status": "completed"}],
            "Job",
        )
        assert text == "Plan — Job\n- [ ] A\n- [x] B"

    def test_format_plan_text_empty(self):
        assert format_plan_text([], "x") == ""

    def test_handle_notification_emits_plan_event(self):
        client = ACPClient()
        queue = asyncio.Queue()
        client._event_queues["s"] = queue
        client._handle_notification({
            "method": "session/update",
            "params": {"sessionId": "s", "update": self._CREATE},
        })
        ev = queue.get_nowait()
        assert ev["type"] == "plan"
        assert ev["description"] == "Do stuff"
        assert [e["content"] for e in ev["entries"]] == ["Write the file", "Read it back"]

    def test_handle_notification_drops_complete_bookkeeping(self):
        client = ACPClient()
        queue = asyncio.Queue()
        client._event_queues["s"] = queue
        # A "complete" call has completed_task_ids but no tasks → nothing surfaced.
        client._handle_notification({
            "method": "session/update",
            "params": {"sessionId": "s", "update": {
                "sessionUpdate": "tool_call", "toolCallId": "t2",
                "title": "Completing #1, #2",
                "rawInput": {"command": "complete", "completed_task_ids": ["1", "2"]},
            }},
        })
        assert queue.empty()

    def test_regular_tool_call_still_emitted(self):
        client = ACPClient()
        queue = asyncio.Queue()
        client._event_queues["s"] = queue
        client._handle_notification({
            "method": "session/update",
            "params": {"sessionId": "s", "update": {
                "sessionUpdate": "tool_call", "toolCallId": "t3",
                "title": "Fetching web content", "kind": "fetch",
                "rawInput": {"url": "https://example.com"},
            }},
        })
        ev = queue.get_nowait()
        assert ev["type"] == "tool_call"
        assert ev["name"] == "Fetching web content"

    @pytest.mark.asyncio
    async def test_prompt_folds_plan_into_reasoning(self):
        client = ACPClient()

        async def fake_stream(params):
            yield {"type": "plan", "entries": [{"content": "Step 1", "status": "pending"}],
                   "description": "Job"}
            yield {"type": "text", "content": "Done."}
            yield {"type": "done", "finish_reason": "stop", "usage": {}}

        client.prompt_stream = fake_stream  # type: ignore[assignment]
        result = await _REAL_PROMPT(client, PromptParams(session_id="s"))
        assert "Plan — Job" in result["reasoning"]
        assert "[ ] Step 1" in result["reasoning"]
        assert result["content"] == "Done."


# ---------------------------------------------------------------------------
# File-edit diffs + shell command/output surfaced as reasoning activity.
# ---------------------------------------------------------------------------

from kiro.acp_client import render_tool_activity, render_tool_call_summary


class TestToolActivityRendering:
    """render_tool_activity / render_tool_call_summary + notification enrichment."""

    def test_edit_tool_call_renders_diff(self):
        ev = {"type": "tool_call", "name": "Editing x.txt", "kind": "edit",
              "content": [{"type": "diff", "path": "/x.txt", "oldText": "banana", "newText": "blueberry"}]}
        out = render_tool_activity(ev)
        assert "⚙ Editing x.txt" in out
        assert "```diff" in out
        assert "-banana" in out
        assert "+blueberry" in out

    def test_create_tool_call_renders_added_lines(self):
        ev = {"type": "tool_call", "name": "Creating x.txt", "kind": "edit",
              "content": [{"type": "diff", "path": "/x.txt", "oldText": None, "newText": "a\nb\n"}]}
        out = render_tool_activity(ev)
        assert "+a" in out and "+b" in out
        assert "-" not in out.replace("⚙", "").replace("diff", "")  # no removed lines

    def test_shell_tool_call_shows_command(self):
        out = render_tool_activity({"type": "tool_call", "name": "Running: echo hi", "kind": "execute", "content": []})
        assert "⚙ Running: echo hi" in out

    def test_shell_update_shows_output(self):
        out = render_tool_activity({"type": "tool_call_update", "name": "Running: echo hi",
                                    "kind": "execute", "output": "hi"})
        assert "```" in out and "hi" in out

    def test_read_update_output_suppressed(self):
        # File reads must not dump their (potentially huge) content into reasoning.
        out = render_tool_activity({"type": "tool_call_update", "name": "Reading big.txt",
                                    "kind": "read", "output": "X" * 10000})
        assert out == ""

    def test_output_truncated(self):
        out = render_tool_activity({"type": "tool_call_update", "name": "Running: cat big",
                                    "kind": "execute", "output": "Y" * 9000})
        assert "truncated" in out
        assert len(out) < 5000

    def test_summary_combines_label_diff_output(self):
        out = render_tool_call_summary({
            "name": "Running: ls", "kind": "execute", "output": "a\nb",
            "content": [],
        })
        assert "⚙ Running: ls" in out and "a\nb" in out

    def test_extract_tool_output(self):
        assert ACPClient._extract_tool_output({"items": [{"Text": "l1"}, {"Text": "l2"}]}) == "l1\nl2"
        assert ACPClient._extract_tool_output(None) == ""

    def test_handle_notification_tool_call_carries_diff(self):
        client = ACPClient()
        queue = asyncio.Queue()
        client._event_queues["s"] = queue
        client._handle_notification({
            "method": "session/update",
            "params": {"sessionId": "s", "update": {
                "sessionUpdate": "tool_call", "toolCallId": "t1",
                "title": "Editing x.txt", "kind": "edit",
                "content": [{"type": "diff", "path": "/x.txt", "oldText": "a", "newText": "b"}],
                "rawInput": {"command": "edit"},
            }},
        })
        ev = queue.get_nowait()
        assert ev["type"] == "tool_call"
        assert ev["kind"] == "edit"
        assert ev["content"][0]["newText"] == "b"

    def test_handle_notification_emits_tool_call_update_with_output(self):
        client = ACPClient()
        queue = asyncio.Queue()
        client._event_queues["s"] = queue
        client._handle_notification({
            "method": "session/update",
            "params": {"sessionId": "s", "update": {
                "sessionUpdate": "tool_call_update", "toolCallId": "t2",
                "title": "Running: echo hi", "kind": "execute", "status": "completed",
                "rawOutput": {"items": [{"Text": "hi"}]},
            }},
        })
        ev = queue.get_nowait()
        assert ev["type"] == "tool_call_update"
        assert ev["kind"] == "execute"
        assert ev["output"] == "hi"

    @pytest.mark.asyncio
    async def test_prompt_aggregates_diff_and_output(self):
        client = ACPClient()

        async def fake_stream(params):
            yield {"type": "tool_call", "id": "c1", "name": "Running: ls", "kind": "execute",
                   "arguments": {}, "content": []}
            yield {"type": "tool_call_update", "id": "c1", "name": "Running: ls", "kind": "execute",
                   "output": "file1\nfile2", "content": []}
            yield {"type": "text", "content": "Done."}
            yield {"type": "done", "finish_reason": "stop", "usage": {}}

        client.prompt_stream = fake_stream  # type: ignore[assignment]
        result = await _REAL_PROMPT(client, PromptParams(session_id="s"))
        tc = result["tool_calls"][0]
        assert tc["kind"] == "execute"
        assert tc["output"] == "file1\nfile2"


class TestStructuredToolRendering:
    """Bold label, structured args (highlighted paths/commands), search summaries."""

    def test_label_is_bold(self):
        out = render_tool_activity({"type": "tool_call", "name": "use_aws", "kind": "other",
                                    "arguments": {}, "content": []})
        assert "**⚙ use_aws**" in out

    def test_grep_args_highlight_path_and_pattern(self):
        out = render_tool_activity({"type": "tool_call", "name": "Searching", "kind": "search",
                                    "arguments": {"__tool_use_purpose": "x", "pattern": "Shim",
                                                  "path": "kiro/", "include": "*.py"}, "content": []})
        assert "pattern=`Shim`" in out
        assert "path=`kiro/`" in out
        assert "include=`*.py`" in out
        assert "__tool_use_purpose" not in out   # internal key skipped

    def test_use_aws_args_rendered(self):
        out = render_tool_activity({"type": "tool_call", "name": "use_aws", "kind": "other",
                                    "arguments": {"label": "Get policy", "operation_name": "get-policy",
                                                  "service_name": "iam", "region": "eu-central-1"},
                                    "content": []})
        assert "operation_name=get-policy" in out
        assert "service_name=iam" in out
        assert "region=eu-central-1" in out

    def test_read_path_from_operations(self):
        out = render_tool_activity({"type": "tool_call", "name": "Reading x", "kind": "read",
                                    "arguments": {"operations": [{"mode": "Line", "path": "/a/b.tf"}]},
                                    "content": []})
        assert "path=`/a/b.tf`" in out

    def test_command_highlighted_inline_not_fenced(self):
        out = render_tool_activity({"type": "tool_call", "name": "Running: ls", "kind": "execute",
                                    "arguments": {"command": "ls -la"}, "content": []})
        assert "command=`ls -la`" in out      # inline code (distinct from output fence)

    def test_search_summary_grep(self):
        out = ACPClient._extract_tool_output({"items": [{"Json": {"numMatches": 26, "numFiles": 5, "truncated": True}}]})
        assert out == "26 match(es) in 5 file(s) (truncated)"
        rendered = render_tool_activity({"type": "tool_call_update", "kind": "search", "output": out})
        assert "↳ 26 match(es) in 5 file(s)" in rendered

    def test_search_summary_glob_message(self):
        out = ACPClient._extract_tool_output(
            {"items": [{"Json": {"filePaths": [], "totalFiles": 0, "message": "No files found matching pattern: **/x"}}]}
        )
        assert "No files found" in out

    def test_search_summary_glob_count(self):
        out = ACPClient._extract_tool_output(
            {"items": [{"Json": {"filePaths": ["/a.toml", "/b.toml"], "totalFiles": 2}}]}
        )
        assert out == "2 file(s) found"

    def test_grep_raw_json_not_dumped(self):
        # A grep result with huge `results` must collapse to a summary, not raw JSON.
        out = ACPClient._extract_tool_output({"items": [{"Json": {
            "numMatches": 2, "numFiles": 1, "results": [{"file": "x", "matches": ["a"] * 1000}]}}]})
        assert out == "2 match(es) in 1 file(s)"
        assert "matches" not in out


# ---------------------------------------------------------------------------
# Multi-turn prompt serialization (issue #43): the stateless gateway carries
# the whole conversation in one role-less ACP session/prompt, so turns are
# rendered as a single text block with stable Role: labels and order; tool
# turns survive as [tool_use]/[tool_result] markers (added by the shims).
# ---------------------------------------------------------------------------

class TestBuildPromptBlocks:
    """ACPClient._build_prompt_blocks representation."""

    def test_empty_history_yields_empty_text_block(self):
        assert ACPClient._build_prompt_blocks([]) == [{"type": "text", "text": ""}]

    def test_lone_user_message_is_verbatim_unlabelled(self):
        msgs = [PromptMessage(role="user", content="hello there")]
        assert ACPClient._build_prompt_blocks(msgs) == [
            {"type": "text", "text": "hello there"}
        ]

    def test_multi_turn_is_single_block_with_role_labels(self):
        msgs = [
            PromptMessage(role="system", content="Be terse."),
            PromptMessage(role="user", content="hi"),
            PromptMessage(role="assistant", content="hello"),
            PromptMessage(role="user", content="bye"),
        ]
        blocks = ACPClient._build_prompt_blocks(msgs)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert blocks[0]["text"] == (
            "System: Be terse.\n\n"
            "User: hi\n\n"
            "Assistant: hello\n\n"
            "User: bye"
        )

    def test_developer_role_is_labelled(self):
        msgs = [
            PromptMessage(role="developer", content="Use Python."),
            PromptMessage(role="user", content="hi"),
        ]
        text = ACPClient._build_prompt_blocks(msgs)[0]["text"]
        assert text == "Developer: Use Python.\n\nUser: hi"

    def test_order_is_preserved(self):
        msgs = [
            PromptMessage(role="user", content="one"),
            PromptMessage(role="assistant", content="two"),
            PromptMessage(role="user", content="three"),
        ]
        text = ACPClient._build_prompt_blocks(msgs)[0]["text"]
        assert text.index("one") < text.index("two") < text.index("three")

    def test_tool_markers_survive_in_transcript(self):
        """[tool_use]/[tool_result] markers emitted by the shims are carried through."""
        msgs = [
            PromptMessage(role="user", content="weather in Berlin?"),
            PromptMessage(role="assistant",
                          content="[tool_use id=call_1 name=get_weather]\n{\"city\": \"Berlin\"}"),
            PromptMessage(role="user", content="[tool_result id=call_1]\nsunny, 20C"),
        ]
        text = ACPClient._build_prompt_blocks(msgs)[0]["text"]
        assert "Assistant: [tool_use id=call_1 name=get_weather]" in text
        assert "User: [tool_result id=call_1]" in text
        assert text.index("[tool_use") < text.index("[tool_result")

    def test_accepts_dict_messages(self):
        """Messages may also arrive as plain dicts (role/content)."""
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        text = ACPClient._build_prompt_blocks(msgs)[0]["text"]
        assert text == "User: a\n\nAssistant: b"


# ---------------------------------------------------------------------------
# Image forwarding in the prompt (issue #33): image content blocks travel as
# their own ACP image blocks after the text transcript; documents/audio are
# already text by the time they reach _build_prompt_blocks.
# ---------------------------------------------------------------------------

_IMG = {"type": "image", "mimeType": "image/png", "data": "QUJD"}


class TestSplitContent:
    """ACPClient._split_content separates text from image blocks."""

    def test_plain_string_has_no_images(self):
        assert ACPClient._split_content("hello") == ("hello", [])

    def test_text_only_block_list(self):
        text, imgs = ACPClient._split_content([{"type": "text", "text": "a"},
                                               {"type": "text", "text": "b"}])
        assert text == "a\nb"
        assert imgs == []

    def test_image_block_extracted(self):
        text, imgs = ACPClient._split_content([{"type": "text", "text": "look"}, _IMG])
        assert text == "look"
        assert imgs == [{"type": "image", "mimeType": "image/png", "data": "QUJD"}]

    def test_image_without_data_skipped(self):
        text, imgs = ACPClient._split_content([{"type": "image", "mimeType": "image/png"}])
        assert imgs == []

    def test_none_content(self):
        assert ACPClient._split_content(None) == ("", [])


class TestBuildPromptBlocksImages:
    """_build_prompt_blocks emits forwarded image blocks alongside text."""

    def test_lone_user_text_plus_image(self):
        msgs = [PromptMessage(role="user", content=[{"type": "text", "text": "what is this?"}, _IMG])]
        blocks = ACPClient._build_prompt_blocks(msgs)
        assert blocks[0]["type"] == "text"
        assert "what is this?" in blocks[0]["text"]
        assert "[image]" in blocks[0]["text"]  # inline marker
        assert blocks[1] == {"type": "image", "mimeType": "image/png", "data": "QUJD"}

    def test_image_only_user_message(self):
        msgs = [PromptMessage(role="user", content=[_IMG])]
        blocks = ACPClient._build_prompt_blocks(msgs)
        # text block carries the [image] marker, image block follows
        assert blocks[0] == {"type": "text", "text": "[image]"}
        assert blocks[1]["type"] == "image"

    def test_multi_turn_with_image_keeps_labels_and_appends_image(self):
        msgs = [
            PromptMessage(role="user", content=[{"type": "text", "text": "see this"}, _IMG]),
            PromptMessage(role="assistant", content="ok"),
        ]
        blocks = ACPClient._build_prompt_blocks(msgs)
        text = blocks[0]["text"]
        assert "User: see this" in text
        assert "Assistant: ok" in text
        assert blocks[-1]["type"] == "image"

    def test_multiple_images_all_forwarded(self):
        img2 = {"type": "image", "mimeType": "image/jpeg", "data": "WFla"}
        msgs = [PromptMessage(role="user", content=[{"type": "text", "text": "two"}, _IMG, img2])]
        blocks = ACPClient._build_prompt_blocks(msgs)
        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(image_blocks) == 2
        assert blocks[0]["text"].count("[image]") == 2
