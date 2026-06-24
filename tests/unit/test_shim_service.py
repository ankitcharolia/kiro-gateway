"""
Unit tests for ShimService — the ACP orchestration layer.
Verifies event translation for text, tool_call, thinking, error, and done events.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from kiro.shim_service import ShimService
from kiro.acp_client import ACPClient as _ACPClient

# Capture the genuine prompt_stream at import time. The session-scoped
# ``test_client`` fixture later monkeypatches ACPClient.prompt_stream for the
# whole session; the cancellation passthrough test needs the real generator.
_REAL_PROMPT_STREAM = _ACPClient.prompt_stream


# ---------------------------------------------------------------------------
# Stub ACP client matching ACPClient's interface used by ShimService
# ---------------------------------------------------------------------------

class StubACP:
    """Minimal ACP client stub for ShimService unit tests."""

    def __init__(self, stream_events: list[dict], prompt_result: dict | None = None):
        self._events = stream_events
        self._prompt_result = prompt_result or {
            "content": "".join(
                e.get("content", "") for e in stream_events if e.get("type") == "text"
            ),
            "finish_reason": "stop",
            "tool_calls": [],
            "usage": {},
        }
        # Records the model passed to new_session so tests can assert forwarding.
        self.last_model: str | None = None
        # Records the PromptParams passed to prompt/prompt_stream.
        self.last_params = None
        self.available_models: list[dict] = []

    async def new_session(self, capabilities=None, cwd=None, model=None) -> str:
        self.last_model = model
        return "stub-session-id"

    async def prompt(self, params) -> dict:
        self.last_params = params
        return self._prompt_result

    async def prompt_stream(self, params):
        self.last_params = params
        for event in self._events:
            yield event

    async def capability_requests(self, session_id: str):
        # Empty async generator — no capability requests in unit tests
        return
        yield  # make it an async generator


async def collect_stream(gen) -> list[dict]:
    results = []
    async for item in gen:
        results.append(item)
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shim_service_text_stream():
    """ShimService yields text events from the ACP stream."""
    acp = StubACP([
        {"type": "text", "content": "Hello "},
        {"type": "text", "content": "world"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "Hi"}]))
    text_events = [e for e in events if e.get("type") == "text"]
    assert len(text_events) >= 1
    combined = "".join(e.get("content", "") for e in text_events)
    assert "Hello" in combined


@pytest.mark.asyncio
async def test_shim_service_done_event():
    """ShimService emits a done event at stream end."""
    acp = StubACP([
        {"type": "text", "content": "Done."},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "go"}]))
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) >= 1


@pytest.mark.asyncio
async def test_shim_service_error_event():
    """ShimService propagates error events from ACP."""
    acp = StubACP([{"type": "error", "message": "kiro CLI crashed"}])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "go"}]))
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1


@pytest.mark.asyncio
async def test_shim_service_tool_call_event():
    """ShimService passes through tool_call events from ACP."""
    acp = StubACP([
        {"type": "tool_call", "id": "call_1", "name": "read_file", "arguments": '{"path": "/tmp/x"}'},
        {"type": "done", "finish_reason": "tool_calls"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "read it"}]))
    tool_events = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_events) >= 1
    assert tool_events[0].get("name") == "read_file"


@pytest.mark.asyncio
async def test_shim_service_thinking_event():
    """ShimService passes through thinking events from ACP."""
    acp = StubACP([
        {"type": "thinking", "content": "Let me think..."},
        {"type": "text", "content": "Answer"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    events = await collect_stream(svc.stream_tokens([{"role": "user", "content": "think"}]))
    thinking_events = [e for e in events if e.get("type") == "thinking"]
    assert len(thinking_events) >= 1


@pytest.mark.asyncio
async def test_shim_service_non_streaming_complete():
    """ShimService.complete() returns aggregated result for non-streaming callers."""
    acp = StubACP(
        stream_events=[],
        prompt_result={"content": "Paris", "finish_reason": "stop", "tool_calls": [], "usage": {}},
    )
    svc = ShimService(acp)
    result = await svc.complete([{"role": "user", "content": "Capital of France?"}])
    assert isinstance(result, dict)
    assert result.get("content") == "Paris"


# ---------------------------------------------------------------------------
# Model forwarding + catalogue exposure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_forwards_model_to_new_session():
    """complete() passes the requested model down to ACPClient.new_session."""
    acp = StubACP(
        stream_events=[],
        prompt_result={"content": "ok", "finish_reason": "stop", "tool_calls": [], "usage": {}},
    )
    svc = ShimService(acp)
    await svc.complete([{"role": "user", "content": "hi"}], model="claude-sonnet-4.6")
    assert acp.last_model == "claude-sonnet-4.6"


@pytest.mark.asyncio
async def test_stream_tokens_forwards_model_to_new_session():
    """stream_tokens() passes the requested model down to ACPClient.new_session."""
    acp = StubACP([
        {"type": "text", "content": "hi"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    await collect_stream(
        svc.stream_tokens([{"role": "user", "content": "hi"}], model="claude-opus-4.8")
    )
    assert acp.last_model == "claude-opus-4.8"


@pytest.mark.asyncio
async def test_available_models_proxies_to_acp_client():
    """available_models() returns the ACP client's cached catalogue."""
    acp = StubACP([])
    acp.available_models = [{"id": "claude-sonnet-4.6", "name": "claude-sonnet-4.6", "description": ""}]
    svc = ShimService(acp)
    models = svc.available_models()
    assert [m["id"] for m in models] == ["claude-sonnet-4.6"]


# ---------------------------------------------------------------------------
# Tool-definition normalisation (regression: PromptParams validation)
# ---------------------------------------------------------------------------

from kiro.shim_service import normalize_tool_definitions


class TestNormalizeToolDefinitions:
    """Unit tests for normalize_tool_definitions across all caller encodings."""

    def test_openai_chat_nested_function_is_flattened(self):
        """OpenAI chat tools ({type, function:{...}}) gain a top-level name."""
        tools = [{
            "type": "function",
            "function": {
                "name": "edit",
                "description": "Edit a file",
                "parameters": {"type": "object", "required": ["command"]},
            },
        }]
        result = normalize_tool_definitions(tools)
        assert result == [{
            "name": "edit",
            "description": "Edit a file",
            "input_schema": {"type": "object", "required": ["command"]},
        }]

    def test_anthropic_input_schema_is_preserved(self):
        """Anthropic tools ({name, description, input_schema}) pass through intact."""
        tools = [{"name": "grep", "description": "search", "input_schema": {"type": "object"}}]
        result = normalize_tool_definitions(tools)
        assert result == [{"name": "grep", "description": "search", "input_schema": {"type": "object"}}]

    def test_responses_flat_function_is_normalised(self):
        """OpenAI Responses tools (flat {type, name, parameters}) are normalised."""
        tools = [{"type": "function", "name": "web", "parameters": {"type": "object"}}]
        result = normalize_tool_definitions(tools)
        assert result == [{"name": "web", "description": "", "input_schema": {"type": "object"}}]

    def test_pydantic_model_is_supported(self):
        """ACPToolDefinition models are dumped and normalised."""
        from kiro.acp_models import ACPToolDefinition
        tools = [ACPToolDefinition(name="ls", description="list", input_schema={"type": "object"})]
        result = normalize_tool_definitions(tools)
        assert result == [{"name": "ls", "description": "list", "input_schema": {"type": "object"}}]

    def test_nameless_tool_is_skipped(self):
        """A tool without a resolvable name is dropped rather than crashing."""
        tools = [{"type": "function", "function": {"description": "no name"}}]
        assert normalize_tool_definitions(tools) == []

    def test_none_and_empty_return_empty_list(self):
        """Falsy tool inputs normalise to an empty list."""
        assert normalize_tool_definitions(None) == []
        assert normalize_tool_definitions([]) == []

    def test_output_satisfies_prompt_params(self):
        """Normalised tools validate against PromptParams (the original bug)."""
        from kiro.acp_models import PromptParams
        tools = [{"type": "function", "function": {"name": "f", "parameters": {}}}]
        params = PromptParams(session_id="s", messages=[], tools=normalize_tool_definitions(tools))
        assert params.tools[0].name == "f"


@pytest.mark.asyncio
async def test_complete_accepts_openai_nested_tools():
    """complete() no longer raises on OpenAI chat-format tools (issue: PromptParams.name)."""
    acp = StubACP(
        stream_events=[],
        prompt_result={"content": "ok", "finish_reason": "stop", "tool_calls": [], "usage": {}},
    )
    svc = ShimService(acp)
    tools = [{"type": "function", "function": {"name": "edit", "parameters": {"type": "object"}}}]
    result = await svc.complete([{"role": "user", "content": "hi"}], tools=tools)
    assert result.get("content") == "ok"
    # Tools reached PromptParams with a valid top-level name.
    assert acp.last_params.tools[0].name == "edit"


@pytest.mark.asyncio
async def test_stream_tokens_accepts_openai_nested_tools():
    """stream_tokens() no longer raises on OpenAI chat-format tools."""
    acp = StubACP([
        {"type": "text", "content": "hi"},
        {"type": "done", "finish_reason": "stop"},
    ])
    svc = ShimService(acp)
    tools = [{"type": "function", "function": {"name": "grep", "parameters": {"type": "object"}}}]
    await collect_stream(svc.stream_tokens([{"role": "user", "content": "hi"}], tools=tools))
    assert acp.last_params.tools[0].name == "grep"


# ---------------------------------------------------------------------------
# Cancellation passthrough (issue #41): closing the stream_tokens generator
# early must propagate to the real ACPClient and emit session/cancel.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_tokens_early_close_cancels_acp_session():
    """Abandoning a ShimService stream cancels the underlying ACP turn."""
    from kiro.acp_client import ACPClient

    # The session-scoped ``test_client`` fixture monkeypatches
    # ACPClient.prompt_stream/new_session for the whole test session, so bind
    # the genuine prompt_stream onto this instance to exercise the real path.
    real_prompt_stream = _REAL_PROMPT_STREAM

    client = ACPClient()
    written: list[str] = []

    async def fake_write_line(line: str) -> None:
        written.append(line)

    async def fake_new_session(capabilities=None, cwd=None, model=None) -> str:
        return "svc-sess"

    client._write_line = fake_write_line  # type: ignore[assignment]
    client.new_session = fake_new_session  # type: ignore[assignment]
    client.prompt_stream = lambda params: real_prompt_stream(client, params)  # type: ignore[assignment]

    svc = ShimService(client)
    gen = svc.stream_tokens([{"role": "user", "content": "Hi"}])

    async def feed() -> None:
        for _ in range(1000):
            queue = client._event_queues.get("svc-sess")
            if queue is not None:
                queue.put_nowait({"type": "text", "content": "partial"})
                return
            await asyncio.sleep(0)

    feeder = asyncio.create_task(feed())
    first = await gen.__anext__()
    await feeder
    assert first["type"] == "text"

    # Client disconnects before completion.
    await gen.aclose()

    for _ in range(20):
        await asyncio.sleep(0)
        if any('"session/cancel"' in w for w in written):
            break

    cancels = [w for w in written if '"session/cancel"' in w]
    assert len(cancels) == 1
    assert '"sessionId": "svc-sess"' in cancels[0] or '"sessionId":"svc-sess"' in cancels[0]


# ---------------------------------------------------------------------------
# Sampling-param forwarding (issue #32): ShimService threads temperature,
# max_tokens, top_p, top_k and stop into PromptParams for both modes.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_forwards_sampling_params():
    """complete() forwards every sampling param onto PromptParams."""
    acp = StubACP([{"type": "text", "content": "hi"}, {"type": "done", "finish_reason": "stop"}])
    svc = ShimService(acp)

    await svc.complete(
        [{"role": "user", "content": "hi"}],
        model="m", max_tokens=10, temperature=0.3, top_p=0.8, top_k=5, stop=["X"],
    )

    p = acp.last_params
    assert p.temperature == 0.3
    assert p.max_tokens == 10
    assert p.top_p == 0.8
    assert p.top_k == 5
    assert p.stop == ["X"]


@pytest.mark.asyncio
async def test_stream_tokens_forwards_sampling_params():
    """stream_tokens() forwards every sampling param onto PromptParams."""
    acp = StubACP([{"type": "text", "content": "hi"}, {"type": "done", "finish_reason": "stop"}])
    svc = ShimService(acp)

    _ = [
        e async for e in svc.stream_tokens(
            [{"role": "user", "content": "hi"}],
            temperature=0.1, max_tokens=7, top_p=0.5, top_k=9, stop=["Z"],
        )
    ]

    p = acp.last_params
    assert p.temperature == 0.1
    assert p.max_tokens == 7
    assert p.top_p == 0.5
    assert p.top_k == 9
    assert p.stop == ["Z"]
