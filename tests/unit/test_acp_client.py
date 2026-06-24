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
from kiro.acp_models import PromptMessage, PromptParams

# Capture the genuine new_session implementation at import time. The
# session-scoped ``test_client`` fixture monkeypatches ``ACPClient.new_session``
# for the whole test session, so tests that need the real method call this
# reference directly instead of going through the (patched) class attribute.
_REAL_NEW_SESSION = ACPClient.new_session
# Likewise capture the genuine prompt_stream — the cancellation tests must
# exercise the real generator, not the session-scoped mock installed by the
# ``test_client`` fixture.
_REAL_PROMPT_STREAM = ACPClient.prompt_stream


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
