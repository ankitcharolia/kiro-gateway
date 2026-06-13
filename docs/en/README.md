# Kiro Gateway — Documentation

A **fully ACP-compliant** bridge that lets any OpenAI-compatible or Anthropic-compatible AI tool use your single Kiro subscription — by routing every request through the official `kiro` CLI binary.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Client Setup](#client-setup)
5. [API Endpoints](#api-endpoints)
6. [Tool Calls](#tool-calls)
7. [Filesystem & Terminal Sandboxing](#filesystem--terminal-sandboxing)
8. [Streaming Events](#streaming-events)
9. [Running Tests](#running-tests)
10. [Release Process](#release-process)

---

## Architecture

Every request flows through the official `kiro` CLI via JSON-RPC 2.0 over stdio — no private HTTP endpoints, no credential sharing, no account pooling.

```
Any OpenAI / Anthropic client
             │
  ┌──────────┴──────────┐
  │                     │
routes_openai_shim   routes_anthropic_shim
 /v1/chat/completions  /v1/messages
             │
       shim_service.py
    (orchestration + tool-call round-trips)
             │
       acp_client.py
    (JSON-RPC 2.0 over stdio)
             │
         kiro CLI
    (official, authenticated)
             │
       Kiro Backend
```

### Core Components

| Component | File | Purpose |
|---|---|---|
| ACP bridge | `kiro/acp_client.py` | Spawns `kiro` CLI; JSON-RPC 2.0 over stdio |
| ACP models | `kiro/acp_models.py` | Pydantic models for all ACP types |
| Capability sandbox | `kiro/capability_executor.py` | readFile / writeFile / listDirectory / runCommand sandboxing |
| Orchestration | `kiro/shim_service.py` | Streaming, tool-call round-trips, session lifecycle |
| ACP routes | `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| OpenAI shim | `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| Anthropic shim | `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| Compliance guard | `kiro/compliance.py` | Single-account enforcement at startup |
| Model resolver | `kiro/model_resolver.py` | Maps model names to Kiro-supported IDs |
| Payload guards | `kiro/payload_guards.py` | Request validation and size limits |
| Tokenizer | `kiro/tokenizer.py` | Token counting for truncation decisions |
| Truncation | `kiro/truncation_state.py` | Conversation history truncation |

---

## Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| **Kiro CLI** | Install from [kiro.dev](https://kiro.dev), then run `kiro auth login` |
| **Python 3.11+** | Required for bare-metal path only |
| **Docker** | Required for the container path only |

### Option A — Bare metal

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit PROXY_API_KEY
kiro auth login
python main.py
```

### Option B — Docker (published image)

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### Option C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # edit PROXY_API_KEY
docker compose up -d
```

### Option D — Build locally

```bash
docker build -t kiro-gateway:local .
docker run -d -p 8000:8000 -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" kiro-gateway:local
```

---

## Configuration

All settings are read from environment variables or a `.env` file.

```env
# Required
PROXY_API_KEY=change-me

# CLI path (override if kiro is not on $PATH)
KIRO_CLI_COMMAND=kiro

# Feature flags
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Compliance (set false only for development)
COMPLIANCE_MODE=true
```

---

## Client Setup

### OpenAI-compatible clients
_(Cursor, Cline, Continue, OpenCode, Hermes-agent, OpenClaw, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000/v1` |
| API Key | value of `PROXY_API_KEY` |
| Model | `claude-sonnet-4-5` |

### Anthropic-compatible clients
_(Claude Code, Kilo Code, Craft-agent, OpenClaw, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000` |
| API Key header | `x-api-key: <PROXY_API_KEY>` |
| Model | `claude-sonnet-4-5` |

### Native ACP clients

```
http://localhost:8000/acp/chat          # non-streaming
http://localhost:8000/acp/chat/stream   # SSE streaming
```

---

## API Endpoints

| Mode | Method | Endpoint | Description |
|---|---|---|---|
| ACP | POST | `/acp/chat` | Non-streaming ACP conversation |
| ACP | POST | `/acp/chat/stream` | SSE streaming ACP conversation |
| OpenAI | GET | `/v1/models` | List available models |
| OpenAI | POST | `/v1/chat/completions` | Streaming and non-streaming completions |
| Anthropic | GET | `/v1/models` | List available models |
| Anthropic | POST | `/v1/messages` | Streaming and non-streaming messages |

---

## Tool Calls

Both shims support the full tool-call cycle:

1. `kiro` CLI emits a `tool_call` ACP event during streaming.
2. The shim translates it to the caller's format (`function_call` / `tool_use`) and streams it.
3. The caller executes the tool and sends back results.
4. The gateway injects results into a follow-up `session/prompt` so `kiro` CLI continues.

Parallel tool calls are supported in the OpenAI shim via index-tracked `tool_calls` delta chunks.

---

## Filesystem & Terminal Sandboxing

| Capability | Behaviour |
|---|---|
| `capability/readFile` | Allowed only within configured `filesystem_roots` with `read: true`. Max 10 MB. |
| `capability/writeFile` | Allowed only within roots with `write: true`. Creates parent dirs. |
| `capability/listDirectory` | Lists entries within allowed roots. |
| `capability/runCommand` | Executes only commands in `terminal.allowed_commands`. Enforces timeout. |

```json
{
  "filesystem_roots": [
    { "uri": "file:///home/user/project", "name": "project", "read": true, "write": false }
  ],
  "terminal": {
    "allowed_commands": ["git", "npm"],
    "working_directory": "/home/user/project",
    "timeout_seconds": 30
  }
}
```

---

## Streaming Events

| ACP event | OpenAI SSE | Anthropic SSE |
|---|---|---|
| `text` | `delta.content` chunk | `content_block_delta[text_delta]` |
| `tool_call` | `delta.tool_calls` chunk | `content_block_start[tool_use]` |
| `thinking` | `delta.content` chunk | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | error chunk + `[DONE]` | `error` event |

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
pytest --cov=kiro --cov-report=term-missing
```

---

## Release Process

```bash
git tag v2.1.0
git push origin v2.1.0
# CI builds linux/amd64 + linux/arm64 and publishes:
#   ghcr.io/ankitcharolia/kiro-gateway:v2.1.0
#   ghcr.io/ankitcharolia/kiro-gateway:latest
# A GitHub Release with source archives is also created automatically.
```

---

## License

AGPL-3.0 — see [LICENSE](../../LICENSE).
