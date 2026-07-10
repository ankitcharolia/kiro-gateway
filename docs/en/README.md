# Kiro Gateway — Documentation

A bridge that lets any OpenAI-compatible or Anthropic-compatible AI tool use your single Kiro subscription — by routing every request through the official `kiro-cli` binary.

> ### 💛 Support this project
>
> If Kiro Gateway is useful to you, please consider supporting its continued development:
>
> **[☕ Buy Me a Coffee](https://buymeacoffee.com/achar)** &nbsp;·&nbsp; **[💸 Donate via PayPal](https://paypal.me/ankitcharolia)**

---

## Table of Contents

1. [Architecture](#architecture)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Client Setup](#client-setup)
5. [API Endpoints](#api-endpoints)
6. [Tool Calls](#tool-calls)
7. [Tool Execution & Permissions](#tool-execution--permissions)
8. [Streaming Events](#streaming-events)
9. [Running Tests](#running-tests)
10. [Release Process](#release-process)

---

## Architecture

Every request flows through the official `kiro-cli` binary via JSON-RPC 2.0 over stdio — no private HTTP endpoints, no credential sharing, no account pooling.

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
         kiro-cli
    (official, authenticated)
             │
       Kiro Backend
```

### Core Components

| Component | File | Purpose |
|---|---|---|
| ACP bridge | `kiro/acp_client.py` | Spawns `kiro-cli`; JSON-RPC 2.0 over stdio |
| ACP models | `kiro/acp_models.py` | Pydantic models for all ACP types |
| Permission handling | `kiro/acp_client.py` | Answers `session/request_permission` (auto-approve / reject via `ACP_TRUST_TOOLS`) |
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
| **Kiro CLI** | Install from [kiro.dev](https://kiro.dev), then run `kiro-cli login` |
| **Python 3.14+** | Required for bare-metal path only |
| **Docker** | Required for the container path only |

### Option A — Bare metal

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
uv sync
cp .env.example .env   # edit KIRO_GATEWAY_API_KEY
kiro-cli login
uv run main.py
```

### Option B — Docker (published image)

The image bundles the Kiro CLI (installed at build time); you only mount your
per-user credentials/state, read-write, and run as your own UID/GID.

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  --user "$(id -u):$(id -g)" \
  -e KIRO_GATEWAY_API_KEY=change-me \
  -v "${HOME}/.aws:/home/gateway/.aws" \
  -v "${HOME}/.kiro:/home/gateway/.kiro" \
  -v "${HOME}/.local/share/kiro-cli:/home/gateway/.local/share/kiro-cli" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

> If you pulled an older release that predates the bundled CLI, build locally
> (Option D) until a newer release is published.

### Option C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # edit KIRO_GATEWAY_API_KEY
printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" >> .env   # run as your user
docker compose up -d
```

`docker-compose.yml` runs as your UID/GID and mounts `~/.aws`, `~/.kiro` and
`~/.local/share/kiro-cli`. Uncomment `build: .` to run local source.

### Option D — Build locally

The build installs the Kiro CLI into the image (self-contained).

```bash
docker build -t kiro-gateway:local .
docker run -d -p 8000:8000 \
  --user "$(id -u):$(id -g)" \
  -e KIRO_GATEWAY_API_KEY=change-me \
  -v "${HOME}/.aws:/home/gateway/.aws" \
  -v "${HOME}/.kiro:/home/gateway/.kiro" \
  -v "${HOME}/.local/share/kiro-cli:/home/gateway/.local/share/kiro-cli" \
  kiro-gateway:local
```

---

## Configuration

All settings are read from environment variables or a `.env` file.

```env
# Required
KIRO_GATEWAY_API_KEY=change-me

# CLI path (override if kiro-cli is not on $PATH)
KIRO_CLI_PATH=kiro-cli

# Models — fallback list for GET /v1/models until the live catalogue is
# discovered from kiro-cli. The requested model is forwarded via
# session/set_model, so clients can select any model kiro-cli supports.
KIRO_MODELS=auto,claude-opus-4.8,claude-sonnet-4.6

# Tool execution — kiro-cli runs its own built-in tools and asks the gateway
# for permission first. true = auto-approve each request, false = reject.
ACP_TRUST_TOOLS=true
ACP_WORKSPACE_DIR=            # Default session cwd (defaults to process cwd)
ACP_TIMEOUT=120              # Seconds to await a JSON-RPC response
ACP_STDIO_MAX_BYTES=16777216 # Max bytes per ACP stdout line (16 MiB) — raise
                             # for very large tool outputs in long agent turns

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
| API Key | value of `KIRO_GATEWAY_API_KEY` |
| Model | `claude-sonnet-4.6` (or `auto`, `claude-opus-4.8`, …) |

### Anthropic-compatible clients
_(Claude Code, Kilo Code, Craft-agent, OpenClaw, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000` |
| API Key header | `x-api-key: <KIRO_GATEWAY_API_KEY>` |
| Model | `claude-sonnet-4.6` |

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

Both shims surface the tool activity `kiro-cli` performs:

1. `kiro-cli` decides to run a built-in tool and requests permission via `session/request_permission`.
2. The gateway approves or rejects based on `ACP_TRUST_TOOLS`.
3. The invocation is streamed to the caller as a `tool_call` event, translated to the caller's format (`tool_calls` / `tool_use`).
4. `kiro-cli` executes the tool itself and continues the same turn, streaming the resulting assistant text.

Because each request opens a fresh ACP session, tool execution and continuation
happen entirely inside `kiro-cli` within a single turn. Parallel tool calls are
surfaced in the OpenAI shim via index-tracked `tool_calls` delta chunks.

---

## Tool Execution & Permissions

`kiro-cli` ships its **own** built-in tools (file reads/edits, command
execution, search) and runs them itself inside the session working directory.
The gateway advertises **no** client-side filesystem or terminal capabilities,
so it never executes tools on the agent's behalf — it only answers the
permission requests the agent sends back.

| Agent request | Gateway behaviour |
|---|---|
| `session/request_permission` | Auto-approves a single invocation (`allow_once`) when `ACP_TRUST_TOOLS=true`; rejects (`reject_once`) when `false`. |

```env
ACP_TRUST_TOOLS=true     # auto-approve built-in tool runs (file edits, commands)
ACP_TRUST_TOOLS=false    # answer-only: every tool permission request is denied
ACP_WORKSPACE_DIR=/path  # working directory kiro-cli operates in (default: process cwd)
```

A request may also pass `filesystem_roots`; the first root's path becomes the
`cwd` for `session/new`.

> **Security:** with `ACP_TRUST_TOOLS=true` the agent can write files and run
> commands in the working directory without human confirmation. Use `false` for
> a read/answer-only deployment.

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
uv sync
pytest tests/ -v
pytest --cov=kiro --cov-report=term-missing
```

---

## Release Process

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
# CI builds linux/amd64 + linux/arm64 and publishes:
#   ghcr.io/ankitcharolia/kiro-gateway:vX.Y.Z
#   ghcr.io/ankitcharolia/kiro-gateway:latest
# A GitHub Release with source archives is also created automatically.
```

---

## Support

If this project saves you time, consider supporting its continued development:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/achar)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)

---

## Compliance & licensing

The gateway talks to Kiro only through the official `kiro-cli` binary — it never
calls private endpoints, pools accounts, or handles credentials. This reflects
the project's design intent and the maintainer's reading of Kiro's official
integration paths, not legal advice. The Kiro CLI is licensed as "AWS Content"
under the [AWS Customer Agreement](https://aws.amazon.com/agreement/) and the
[AWS IP License](https://aws.amazon.com/legal/aws-ip-license-terms/); see
[`COMPLIANCE.md`](../../COMPLIANCE.md) for details.

---

## License

AGPL-3.0 — see [LICENSE](../../LICENSE).
