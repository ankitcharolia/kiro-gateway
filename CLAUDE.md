# CLAUDE.md — Guide for AI Agents Working in Kiro Gateway

This file orients AI coding agents (Claude, GPT, etc.) working in this
repository. It documents the **current** architecture: an ACP-compliant bridge
that routes every completion through the official `kiro-cli` binary via the
Agent Client Protocol (ACP). For deeper conventions and contribution rules see
[`AGENTS.md`](AGENTS.md); for user-facing docs see [`README.md`](README.md).

> If anything here disagrees with the code, the code wins — read the source and
> update this file.

---

## What this project is

**Kiro Gateway** is a Python/FastAPI server that exposes OpenAI-compatible,
Anthropic-compatible, and native ACP HTTP endpoints, and fulfils every request
by talking to a single long-lived `kiro-cli acp` subprocess over JSON-RPC 2.0
on stdio. It never calls private Kiro HTTP APIs and never touches credentials —
all authentication lives inside `kiro-cli` (`kiro-cli login`).

- **Language**: Python 3.14+
- **Framework**: FastAPI + uvicorn
- **Entry point**: `main.py`
- **Package**: `kiro/`
- **License**: AGPL-3.0

---

## Request path

```
OpenAI / Anthropic / native-ACP client
        │  HTTP (OpenAI | Anthropic | ACP)
        ▼
routes_openai_shim.py / routes_anthropic_shim.py / routes_acp.py
        │
        ▼
shim_service.py        # session lifecycle + event passthrough/aggregation
        │
        ▼
acp_client.py          # one kiro-cli subprocess, JSON-RPC 2.0 over stdio
        │
        ▼
kiro-cli acp           # official, authenticated binary
        │
        ▼
Kiro Backend
```

---

## The ACP wire protocol (as implemented by `kiro-cli acp`, agent v2.x)

This is the real Zed Agent Client Protocol. Getting the shapes right matters —
sending the wrong `initialize` params makes the agent exit immediately.

1. **`initialize`** — request, **once per process**
   ```json
   {"protocolVersion": 1,
    "clientCapabilities": {"fs": {"readTextFile": false, "writeTextFile": false},
                            "terminal": false}}
   ```
   Returns `{protocolVersion, agentCapabilities, authMethods, agentInfo}`.
   **No session id is created here.**

2. **`session/new`** — request, **once per gateway request**
   ```json
   {"cwd": "<absolute path>", "mcpServers": []}
   ```
   Returns `{sessionId, modes}`. A fresh session per HTTP request keeps
   concurrent requests isolated.

3. **`session/prompt`** — request, per user turn
   ```json
   {"sessionId": "...", "prompt": [{"type": "text", "text": "..."}]}
   ```
   Returns `{stopReason}` (`end_turn`, `max_tokens`, `tool_use`, …) when the
   turn finishes. The `prompt` array is a list of **role-less** content blocks;
   the whole conversation is serialised into one labelled text block, and
   **image** attachments are appended as `{"type":"image","mimeType","data"}`
   blocks (kiro-cli advertises `promptCapabilities.image`; documents/audio are
   reduced to text — see `kiro/multimodal.py`).

4. **`session/update`** — notifications (no id) streamed during a prompt.
   Discriminated by `update.sessionUpdate`:
   - `agent_message_chunk` → assistant text delta
   - `agent_thought_chunk` → reasoning/thinking delta
   - `tool_call`           → a built-in tool the agent is invoking
   - `tool_call_update`    → status change for a running tool call

5. **`session/request_permission`** — a request (has id) the agent sends *back*
   to the gateway before running a built-in tool. The gateway answers
   `{"outcome": {"outcome": "selected", "optionId": "<id>"}}`.

`kiro-cli` runs its **own** built-in tools (file edits, command execution). The
gateway advertises **no** client-side `fs`/`terminal` capabilities, so it only
ever has to answer permission requests — it does not execute tools itself.

---

## Internal event contract (the boundary every route relies on)

`ACPClient` translates raw `session/update` notifications and the terminal
`session/prompt` result into **plain dicts**. `ShimService` passes them through
unchanged; the route translators turn them into OpenAI/Anthropic/ACP SSE.

| dict event | Fields | Source |
|---|---|---|
| `{"type": "text", ...}` | `content: str` | `agent_message_chunk` |
| `{"type": "thinking", ...}` | `content: str` | `agent_thought_chunk` |
| `{"type": "tool_call", ...}` | `id, name, arguments: dict` | `tool_call` |
| `{"type": "done", ...}` | `finish_reason: str, usage: dict` | prompt result `stopReason` |
| `{"type": "error", ...}` | `message: str` | JSON-RPC error / subprocess exit |

Rules:
- Events are **dicts**, accessed with `event.get("type")` — never attribute
  access. This is the contract the unit tests assert and the routes consume.
- `stopReason` is normalised (`end_turn → stop`, `max_tokens → length`,
  `tool_use → tool_calls`). The Anthropic route maps `stop → end_turn` back.
- `thinking` is **not** surfaced on the OpenAI/Anthropic content streams (kept
  clean); it is still emitted as an event for native-ACP consumers.

---

## File map

| File | Responsibility |
|---|---|
| `main.py` | App + lifespan: loads `.env`, starts `ACPClient`, runs `initialize` once |
| `kiro/acp_client.py` | The subprocess + JSON-RPC bridge; protocol translation; permission handling |
| `kiro/acp_models.py` | Pydantic models (JSON-RPC envelopes, prompt params, content blocks) |
| `kiro/shim_service.py` | Per-request `session/new`, streaming passthrough, non-streaming aggregation |
| `kiro/multimodal.py` | Multimodal input: forward base64 images as ACP image blocks; extract/placeholder documents & audio (issue #33) |
| `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| `kiro/config.py` | Env-driven settings (`settings` object + module constants) |
| `kiro/compliance.py` | Single-account enforcement at startup |
| `kiro/capability_executor.py` | Stub capability dispatch (retained; not in the live permission path) |

---

## Configuration

Read from environment variables or `.env` (loaded by `main.py` at startup;
existing env vars take precedence over `.env`).

| Variable | Default | Purpose |
|---|---|---|
| `KIRO_GATEWAY_API_KEY` | `test-proxy-key` | Bearer / `x-api-key` clients must send |
| `KIRO_CLI_PATH` | `kiro-cli` | Path/name of the Kiro CLI binary |
| `ACP_TRUST_TOOLS` | `true` | Auto-approve a single tool invocation on `session/request_permission`; set `false` to reject (read/answer-only posture) |
| `ACP_WORKSPACE_DIR` | process cwd | Default `cwd` for ACP sessions (per-request `filesystem_roots` override it) |
| `ACP_TIMEOUT` | `120` | Seconds to await a JSON-RPC response |
| `ACP_ENABLED` / `OPENAI_SHIM_ENABLED` / `ANTHROPIC_SHIM_ENABLED` | `true` | Router toggles |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8000` | Bind address |
| `COMPLIANCE_MODE` | `true` | Single-account enforcement |

> **Security note:** `ACP_TRUST_TOOLS=true` lets `kiro-cli` run built-in tools
> (including file writes and command execution) in the session `cwd` without
> human confirmation. Set `ACP_TRUST_TOOLS=false` for an answer-only gateway.

---

## Run, verify, test

```bash
# Run (bare metal) — needs uv: https://docs.astral.sh/uv/
uv sync                       # creates .venv and installs deps
cp .env.example .env          # set KIRO_GATEWAY_API_KEY
kiro-cli login                # once
uv run main.py                # serves on http://localhost:8000

# Smoke test
curl localhost:8000/health
curl -H "Authorization: Bearer $KIRO_GATEWAY_API_KEY" localhost:8000/v1/models
curl -H "Authorization: Bearer $KIRO_GATEWAY_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"claude-sonnet-4.6","messages":[{"role":"user","content":"hi"}]}' \
  localhost:8000/v1/chat/completions

# Tests (fully network-isolated; no real kiro-cli needed)
uv run pytest -q
```

The test suite mocks the ACP subprocess. The `test_client` fixture in
`tests/conftest.py` patches `ACPClient.start/stop/initialize` **and**
`new_session/prompt/prompt_stream` — if you add a new method on the prompt path,
patch it there too or integration tests will block on the JSON-RPC timeout.

---

## Working rules

1. **Read before editing.** Confirm wire shapes against `acp_client.py` and, when
   in doubt, probe `kiro-cli acp` directly over stdio.
2. **Keep the dict-event contract.** Don't reintroduce attribute access on stream
   events; routes and tests depend on dicts.
3. **Apply changes to both APIs and both modes.** OpenAI + Anthropic, streaming +
   non-streaming. Add ACP-route coverage when relevant.
4. **Never spawn the real binary in tests.** Mock it via the conftest fixtures.
5. **Type hints + Google-style docstrings + English-only identifiers.**
6. **Run `uv run pytest -q` before finishing.** The suite must stay green and fast.
