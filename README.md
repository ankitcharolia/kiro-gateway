# ACP-Compliant Kiro Gateway

[![CI](https://github.com/ankitcharolia/kiro-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitcharolia/kiro-gateway/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io%2Fankitcharolia%2Fkiro--gateway-blue?logo=docker)](https://ghcr.io/ankitcharolia/kiro-gateway)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/achar)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)

An **ACP-based** bridge that lets any OpenAI-compatible or Anthropic-compatible AI harness use your **single** Kiro subscription — by routing every request through the official `kiro-cli` binary, never through reverse-engineered APIs.

> ### 💛 Support this project
>
> If Kiro Gateway is useful to you, please consider supporting its continued development:
>
> **[☕ Buy Me a Coffee](https://buymeacoffee.com/achar)** &nbsp;·&nbsp; **[💸 Donate via PayPal](https://paypal.me/ankitcharolia)**

---

## Compliance model

This gateway is designed to stay on Kiro's official, documented integration
surfaces:
- It communicates with Kiro **only** through the official `kiro-cli` binary.
- It never calls private HTTP endpoints, never pools accounts, and never
  circumvents rate limits.
- It never reads or stores credentials — all authentication lives inside
  `kiro-cli` (`kiro-cli login`).

### Full request path

```
OpenCode / Hermes-agent / Kilo Code / Craft-agent / OpenClaw
              (any OpenAI or Anthropic API client)
                             │
            ┌────────────────┴─────────────────┐
            │                                  │
   routes_openai_shim.py          routes_anthropic_shim.py
     POST /v1/chat/completions       POST /v1/messages
     GET  /v1/models                 GET  /v1/models
            │                                  │
            └────────────────┬─────────────────┘
                             │
                 ┌───────────▼──────────┐
                 │    shim_service.py   │
                 │ orchestration + tool │
                 │ call round-trips     │
                 └───────────┬──────────┘
                             │
                 ┌───────────▼──────────┐
                 │    acp_client.py     │
                 │  JSON-RPC 2.0 over   │
                 │       stdio          │
                 └───────────┬──────────┘
                             │
                 ┌───────────▼──────────┐
                 │     kiro-cli         │  ← only official binary
                 │  (official, authed)  │
                 └───────────┬──────────┘
                             │
                 ┌───────────▼──────────┐
                 │    Kiro Backend      │
                 └──────────────────────┘
```

> **Single-account enforcement** — the gateway validates at startup that only one kiro-cli session is active at any time (`kiro.compliance.validate_single_account_compliance`). Attempting to spin up parallel accounts raises a hard `ComplianceError`.

---

## Modes

### 1. ACP (preferred)

For editors that speak ACP natively.

| Endpoint | Description |
|---|---|
| `POST /acp/chat` | Non-streaming ACP conversation |
| `POST /acp/chat/stream` | SSE streaming ACP conversation |

### 2. OpenAI shim

For tools that only understand the OpenAI API (Cursor, Cline, Continue, OpenCode, Hermes-agent, OpenClaw, …).

| Endpoint | Description |
|---|---|
| `GET /v1/models` | List available models (live catalogue from kiro-cli, with fallback) |
| `POST /v1/chat/completions` | Streaming and non-streaming completions |
| `POST /v1/responses` | OpenAI Responses API (streaming and non-streaming) |
| `POST /v1/embeddings` | Returns `501 Not Implemented` — kiro-cli/ACP provides no embeddings model |

### 3. Anthropic shim

For tools that only understand the Anthropic API (Claude Code, Kilo Code, Craft-agent, OpenClaw, …).

| Endpoint | Description |
|---|---|
| `GET /v1/models` | List available models (live catalogue from kiro-cli, with fallback) |
| `POST /v1/messages` | Streaming and non-streaming messages |
| `POST /v1/messages/count_tokens` | Estimate input tokens for a request (local tokenizer estimate) |

---

## Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| **Kiro CLI** | Install from [kiro.dev](https://kiro.dev) and run `kiro-cli login` |
| **Python 3.14+** | Required for the bare-metal path only |
| **Docker** | Required for the container path only |

---

### Option A — Clone and run (bare metal)

```bash
# 1. Clone the repository
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway

# 2. Create a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Open .env and set at minimum:
#   KIRO_GATEWAY_API_KEY=<your-chosen-secret-key>
#   KIRO_CLI_PATH=kiro-cli    # full path if not on $PATH

# 5. Authenticate with Kiro (once)
kiro-cli login

# 6. Start the gateway
python main.py
# Gateway is now listening on http://localhost:8000
```

---

### Docker credentials & state

The Docker image **bundles the Kiro CLI** (installed from the official
`https://cli.kiro.dev/install` at build time), so you never mount the binary.
You only mount your per-user Kiro credentials/state, which the CLI needs to
authenticate and cannot be baked into an image:

| Host path | Purpose | Mode |
|---|---|---|
| `~/.aws` | SSO token cache | read-write |
| `~/.kiro` | sessions, settings | read-write |
| `~/.local/share/kiro-cli` | OAuth token secret store (`data.sqlite3`) + helper binaries | read-write |

Mounts must be **read-write** (the CLI refreshes the auth token in place and
writes session files). Run the container as **your own UID/GID** so it can read
and write those files: `--user "$(id -u):$(id -g)"`. Run `kiro-cli login` on the
host once before starting the container.

---

### Option B — Docker (published image)

Pre-built multi-arch images (`linux/amd64`, `linux/arm64`) are published to the
GitHub Container Registry on every release.

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

> The published image must be built from a release that includes the bundled
> Kiro CLI. If you pulled an older release, build locally (Option D) until a new
> release is published.

#### Pinning a specific version

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:vX.Y.Z
```

---

### Option C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env
# edit .env: set KIRO_GATEWAY_API_KEY
# add your UID/GID so the container can read your mounted credentials:
printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" >> .env

docker compose up -d
```

The included `docker-compose.yml` runs as your UID/GID and mounts `~/.aws`,
`~/.kiro` and `~/.local/share/kiro-cli`. It uses the published image by default;
to run the local source, comment out `image:` and uncomment `build: .`.

---

### Option D — Build the Docker image locally

The build installs the Kiro CLI into the image, so it is self-contained.

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway

docker build -t kiro-gateway:local .

docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  --user "$(id -u):$(id -g)" \
  -e KIRO_GATEWAY_API_KEY=change-me \
  -v "${HOME}/.aws:/home/gateway/.aws" \
  -v "${HOME}/.kiro:/home/gateway/.kiro" \
  -v "${HOME}/.local/share/kiro-cli:/home/gateway/.local/share/kiro-cli" \
  kiro-gateway:local
```

---

## Configuration

All settings are read from environment variables (or a `.env` file).

```env
# ── Required ──────────────────────────────────────────────────────────
KIRO_GATEWAY_API_KEY=change-me          # Secret key clients must send as Bearer / x-api-key

# ── CLI path ──────────────────────────────────────────────────────────
KIRO_CLI_PATH=kiro-cli           # Override if kiro-cli is not on $PATH

# ── Models ────────────────────────────────────────────────────────────
# Fallback model list advertised by GET /v1/models before the live catalogue
# is discovered from kiro-cli. The live list (reported on every session) takes
# precedence at runtime. The model named in a request is forwarded to kiro-cli
# via session/set_model, so clients can select any model kiro-cli supports.
KIRO_MODELS=auto,claude-opus-4.8,claude-sonnet-4.6

# ── Tool execution ────────────────────────────────────────────────────
# kiro-cli runs its own built-in tools (file edits, command execution) and
# asks the gateway for permission first. true = auto-approve each request,
# false = reject (read/answer-only posture).
ACP_TRUST_TOOLS=true
ACP_WORKSPACE_DIR=               # Default session cwd (defaults to process cwd)
ACP_TIMEOUT=120                  # Seconds to await a JSON-RPC response
ACP_STDIO_MAX_BYTES=16777216     # Max bytes per ACP stdout line (16 MiB) — raise
                                 # for very large tool outputs in long agent turns

# ── Feature flags ─────────────────────────────────────────────────────
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true

# ── Server ────────────────────────────────────────────────────────────
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# ── Compliance ────────────────────────────────────────────────────────
COMPLIANCE_MODE=true             # Enforces single-account; set false only for development
```

---

## Client setup

### OpenAI-compatible clients

_(Cursor, Cline, Continue, OpenCode, Hermes-agent, OpenClaw, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000/v1` |
| API Key | value of `KIRO_GATEWAY_API_KEY` |
| Model | `claude-sonnet-4.6` (or any Kiro-supported model: `auto`, `claude-opus-4.8`, …) |

### Anthropic-compatible clients

_(Claude Code, Kilo Code, Craft-agent, OpenClaw, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000` |
| API Key header | `x-api-key: <KIRO_GATEWAY_API_KEY>` |
| Model | `claude-sonnet-4.6` |

### OpenClaw — quick setup

OpenClaw supports both OpenAI and Anthropic API modes. Use the OpenAI shim for maximum compatibility:

```json
{
  "provider": "openai",
  "base_url": "http://localhost:8000/v1",
  "api_key": "<KIRO_GATEWAY_API_KEY>",
  "model": "claude-sonnet-4.6"
}
```

Or use the Anthropic shim if OpenClaw is configured with an Anthropic provider:

```json
{
  "provider": "anthropic",
  "base_url": "http://localhost:8000",
  "api_key": "<KIRO_GATEWAY_API_KEY>",
  "model": "claude-sonnet-4.6"
}
```

### Native ACP clients

Point your ACP client at:
```
http://localhost:8000/acp/chat         # non-streaming
http://localhost:8000/acp/chat/stream  # SSE streaming
```

---

## Streaming event map

| ACP event | OpenAI SSE | Anthropic SSE |
|---|---|---|
| `text` | `delta.content` chunk | `content_block_delta[text_delta]` |
| `tool_call` | `delta.tool_calls` chunk | `content_block_start[tool_use]` + `input_json_delta` |
| `thinking` | `delta.content` chunk | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | error chunk + `[DONE]` | `error` event |

---

## Tool-call round-trips

Both shims surface the tool activity that `kiro-cli` performs:

1. `kiro-cli` decides to run one of its built-in tools and asks the gateway for
   permission via `session/request_permission`.
2. The gateway approves or rejects based on `ACP_TRUST_TOOLS` (see below).
3. The tool invocation is streamed to the caller as a `tool_call` event,
   translated to the caller's format (`tool_calls` / `tool_use`).
4. `kiro-cli` executes the tool itself and continues the same turn, streaming
   the resulting assistant text.

Parallel tool calls are surfaced in the OpenAI shim via index-tracked
`tool_calls` delta chunks. Because each gateway request opens a fresh ACP
session, tool execution and continuation happen entirely inside `kiro-cli`
within a single turn — callers receive the tool activity for visibility rather
than having to execute tools themselves.

---

## Tool execution & permissions

`kiro-cli` ships its **own** built-in tools (file reads/edits, command
execution, search, …) and runs them itself inside the session working
directory. The gateway advertises **no** client-side filesystem or terminal
capabilities, so it never executes tools on the agent's behalf — it only
answers the permission requests the agent sends back:

| Agent request | Gateway behaviour |
|---|---|
| `session/request_permission` | Auto-approves a single invocation (`allow_once`) when `ACP_TRUST_TOOLS=true`; rejects (`reject_once`) when `false`. |

```env
ACP_TRUST_TOOLS=true     # auto-approve built-in tool runs (file edits, commands)
ACP_TRUST_TOOLS=false    # answer-only: every tool permission request is denied
ACP_WORKSPACE_DIR=/path  # working directory kiro-cli operates in (default: process cwd)
```

> **Security:** with `ACP_TRUST_TOOLS=true` the agent can write files and run
> commands in `ACP_WORKSPACE_DIR` without human confirmation. Use `false` for a
> read/answer-only deployment, and scope `ACP_WORKSPACE_DIR` to a project
> directory.

A request may also pass `filesystem_roots` to set the session's working
directory; the first root's path is used as the `cwd` for `session/new`.

---

## Architecture reference

| Component | File | Purpose |
|---|---|---|
| ACP bridge | `kiro/acp_client.py` | Spawns `kiro-cli`; exchanges JSON-RPC 2.0 over stdio; routes events to per-session queues |
| ACP models | `kiro/acp_models.py` | Pydantic models for all ACP types |
| Permission handling | `kiro/acp_client.py` | Answers `session/request_permission` (auto-approve / reject via `ACP_TRUST_TOOLS`) |
| Orchestration | `kiro/shim_service.py` | Per-request session creation, streaming passthrough, non-streaming aggregation |
| ACP routes | `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| OpenAI shim | `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| Anthropic shim | `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| Compliance guard | `kiro/compliance.py` | Single-account enforcement at startup |

---

## Running tests

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run the full suite
pytest tests/ -v

# Run compliance checks only
pytest tests/unit/test_acp_compliance.py tests/unit/test_compliance.py -v

# Run with coverage
pytest --cov=kiro --cov-report=term-missing
```

The test suite verifies:
- All removed direct-API modules raise `ImportError`
- `main.py` mounts only ACP-backed routers
- `acp_client.py` uses subprocess stdio, not HTTP
- No private Kiro API URLs appear in source files
- Single-account `ComplianceError` is raised for 2+ sessions
- OpenAI + Anthropic shim endpoints return spec-compliant responses
- `session/request_permission` is auto-approved or rejected per `ACP_TRUST_TOOLS`

---

## Docker image release process

Images are built and pushed automatically by GitHub Actions on every `v*` tag.

```bash
# Create and push a release tag
git tag vX.Y.Z
git push origin vX.Y.Z
# → CI builds linux/amd64 + linux/arm64 and pushes:
#     ghcr.io/ankitcharolia/kiro-gateway:vX.Y.Z
#     ghcr.io/ankitcharolia/kiro-gateway:latest
```

> The published image bundles the Kiro CLI binary; see
> [Compliance & licensing](#compliance--licensing) before publishing it publicly.

---

## Recommended practices

- Prefer **ACP-native IDEs** whenever available — zero translation overhead.
- Scope `ACP_WORKSPACE_DIR` to a single project directory.
- Set `ACP_TRUST_TOOLS=false` for an answer-only deployment where the agent must not edit files or run commands.
- Never share `KIRO_GATEWAY_API_KEY` — treat it like any API secret.
- All Kiro authentication lives in `kiro-cli`. The gateway never touches credentials.

---

## Performance & long-running sessions

The gateway holds **one** persistent `kiro-cli acp` subprocess and opens a fresh
ACP session per HTTP request, so concurrent and repeated requests stay isolated.
A few notes for long-running agents that issue many large turns:

- **Large tool outputs / long turns.** ACP streams tool results and assistant
  text as single JSON-RPC lines on stdout. `ACP_STDIO_MAX_BYTES` (default 16 MiB)
  sets the per-line read buffer; raise it if an agent produces very large diffs,
  file dumps, or completions. (asyncio's built-in default is only 64 KiB, which
  oversized lines would silently overrun — the gateway raises it for you.)
- **Model selection is cheap.** The requested model is forwarded with one
  `session/set_model` call, and the gateway **skips** it when the request already
  asks for the session's default model — no extra round-trip in the common case.
- **Concurrency.** All requests multiplex over the single subprocess (required by
  the single-account compliance model); throughput is bounded by `kiro-cli`
  itself, not by the gateway's translation layer.
- **Statelessness.** Each request re-sends its full conversation (standard for the
  OpenAI/Anthropic APIs) and runs in its own session, so there is no cross-request
  state to leak or grow on the gateway side.

---

## Support

If this project is useful, please consider supporting its continued development — **[☕ Buy Me a Coffee](https://buymeacoffee.com/achar)** or **[💸 PayPal](https://paypal.me/ankitcharolia)**.

## Compliance & licensing

The gateway talks to Kiro only through the official `kiro-cli` binary — it never
calls private endpoints, pools accounts, or handles credentials. This reflects
the project's design intent and the maintainer's reading of Kiro's official
integration paths, not legal advice. The Kiro CLI is licensed as "AWS Content"
under the [AWS Customer Agreement](https://aws.amazon.com/agreement/) and the
[AWS IP License](https://aws.amazon.com/legal/aws-ip-license-terms/) (see the
[official license](https://kiro.dev/license/)), so your use is governed by those
terms. If you plan to publish a Docker image that bundles the Kiro CLI, review
the redistribution terms first. See [`COMPLIANCE.md`](COMPLIANCE.md) for details.

## License

AGPL-3.0 — preserving upstream license requirements.
