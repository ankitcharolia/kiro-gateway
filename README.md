# ACP-Compliant Kiro Gateway

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io%2Fankitcharolia%2Fkiro--gateway-blue?logo=docker)](https://ghcr.io/ankitcharolia/kiro-gateway)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)

A **fully ACP-compliant** bridge that lets any OpenAI-compatible or Anthropic-compatible AI harness use your **single** Kiro subscription — by routing every request through the official `kiro` CLI, never through reverse-engineered APIs.

---

## Compliance model

Kiro permits subscriptions to be used with:
- Kiro IDE, Kiro CLI, Kiro Web
- ACP-compatible IDEs
- Software-development automation (CI/CD reviews, etc.)

This gateway **only** communicates with Kiro through the official `kiro` CLI binary.
It never calls private HTTP endpoints, never pools accounts, and never circumvents rate limits.

### Full request path

```
OpenCode / Hermes-agent / Kilo Code / Craft-agent
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
              │     kiro  CLI        │  ← only official binary
              │  (official, authed)  │
              └───────────┬──────────┘
                          │
              ┌───────────▼──────────┐
              │    Kiro Backend      │
              └──────────────────────┘
```

> **Single-account enforcement** — the gateway validates at startup that only one kiro CLI session is active at any time (`kiro.compliance.validate_single_account_compliance`). Attempting to spin up parallel accounts raises a hard `ComplianceError`.

---

## Modes

### 1. ACP (preferred)

For editors that speak ACP natively.

| Endpoint | Description |
|---|---|
| `POST /acp/chat` | Non-streaming ACP conversation |
| `POST /acp/chat/stream` | SSE streaming ACP conversation |

### 2. OpenAI shim

For tools that only understand the OpenAI API (Cursor, Cline, Continue, OpenCode, Hermes-agent, etc.).

| Endpoint | Description |
|---|---|
| `GET /v1/models` | List available models |
| `POST /v1/chat/completions` | Streaming and non-streaming completions |

### 3. Anthropic shim

For tools that only understand the Anthropic API (Claude Code, Kilo Code, Craft-agent, etc.).

| Endpoint | Description |
|---|---|
| `GET /v1/models` | List available models |
| `POST /v1/messages` | Streaming and non-streaming messages |

---

## Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| **Kiro CLI** | Install from [kiro.dev](https://kiro.dev) and run `kiro auth login` |
| **Python 3.11+** | Required for the bare-metal path only |
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
#   PROXY_API_KEY=<your-chosen-secret-key>
#   KIRO_CLI_COMMAND=kiro             # full path if not on $PATH

# 5. Authenticate with Kiro (once)
kiro auth login

# 6. Start the gateway
python main.py
# Gateway is now listening on http://localhost:8000
```

---

### Option B — Docker (published image)

Pre-built multi-arch images (`linux/amd64`, `linux/arm64`) are published to the GitHub Container Registry on every release.

```bash
# Pull the latest release
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest

# Run — mount your kiro credentials so the container can call the CLI
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -e KIRO_CLI_COMMAND=/usr/local/bin/kiro \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

> **Credential mount** — Kiro stores its session tokens in `~/.kiro`. Mounting this directory read-only into the container lets the bundled `kiro` CLI authenticate without re-running `kiro auth login` inside the container.

#### Pinning a specific version

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:v2.1.0
```

---

### Option C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env
# edit .env: set PROXY_API_KEY

docker compose up -d
```

The included `docker-compose.yml` mounts `~/.kiro` automatically.

---

### Option D — Build the Docker image locally

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway

docker build -t kiro-gateway:local .

docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  kiro-gateway:local
```

---

## Configuration

All settings are read from environment variables (or a `.env` file).

```env
# ── Required ──────────────────────────────────────────────────────────
PROXY_API_KEY=change-me          # Secret key clients must send as Bearer / x-api-key

# ── CLI path ──────────────────────────────────────────────────────────
KIRO_CLI_COMMAND=kiro            # Override if kiro is not on $PATH

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

_(Cursor, Cline, Continue, OpenCode, Hermes-agent, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000/v1` |
| API Key | value of `PROXY_API_KEY` |
| Model | `claude-sonnet-4-5` (or any Kiro-supported model) |

### Anthropic-compatible clients

_(Claude Code, Kilo Code, Craft-agent, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000` |
| API Key header | `x-api-key: <PROXY_API_KEY>` |
| Model | `claude-sonnet-4-5` |

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

Both shims support the full tool-call cycle:

1. `kiro` CLI emits a `tool_call` ACP event during streaming.
2. The shim translates it to the caller's format (`function_call` / `tool_use`) and streams it.
3. The caller executes the tool and sends back results.
4. The gateway injects results into a follow-up `session/prompt` so `kiro` CLI continues.

Parallel tool calls are supported in the OpenAI shim via index-tracked `tool_calls` delta chunks.

---

## Filesystem & terminal sandboxing

Capability requests from `kiro` CLI are mediated by `CapabilityExecutor`:

| Capability | Behaviour |
|---|---|
| `capability/readFile` | Allowed only within configured `filesystem_roots` with `read: true`. Max 10 MB. |
| `capability/writeFile` | Allowed only within roots with `write: true`. Creates parent dirs. |
| `capability/listDirectory` | Lists entries (name, type, size, URI) within allowed roots. |
| `capability/runCommand` | Executes only commands in `terminal.allowed_commands`. Enforces timeout. |

```json
{
  "model": "claude-sonnet-4-5",
  "messages": [{ "role": "user", "content": "Review my code" }],
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

## Architecture reference

| Component | File | Purpose |
|---|---|---|
| ACP bridge | `kiro/acp_client.py` | Spawns `kiro` CLI; exchanges JSON-RPC 2.0 over stdio; routes events to per-session queues |
| ACP models | `kiro/acp_models.py` | Pydantic models for all ACP types |
| Capability sandbox | `kiro/capability_executor.py` | readFile / writeFile / listDirectory / runCommand with path + command sandboxing |
| Orchestration | `kiro/shim_service.py` | Streaming, tool-call round-trips, capability mediation, session lifecycle |
| ACP routes | `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| OpenAI shim | `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| Anthropic shim | `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| Compliance guard | `kiro/compliance.py` | Single-account enforcement at startup |

---

## Running tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run the full ACP-compliance + behaviour suite
pytest tests/unit/ -v

# Run compliance checks only
pytest tests/unit/test_acp_compliance.py tests/unit/test_compliance.py -v
```

The test suite verifies:
- All removed direct-API modules raise `ImportError`
- `main.py` mounts only ACP-backed routers
- `acp_client.py` uses subprocess stdio, not HTTP
- No private Kiro API URLs appear in source files
- Single-account `ComplianceError` is raised for 2+ sessions
- OpenAI + Anthropic shim endpoints return spec-compliant responses
- `CapabilityExecutor` sandbox enforces path + command boundaries

---

## Docker image release process

Images are built and pushed automatically by GitHub Actions on every `v*` tag.

```bash
# Create and push a release tag
git tag v2.1.0
git push origin v2.1.0
# → CI builds linux/amd64 + linux/arm64 and pushes:
#     ghcr.io/ankitcharolia/kiro-gateway:v2.1.0
#     ghcr.io/ankitcharolia/kiro-gateway:latest
```

---

## Recommended practices

- Prefer **ACP-native IDEs** whenever available — zero translation overhead.
- Keep `filesystem_roots` scoped to the project directory and `write: false` unless the agent needs to create files.
- Keep `terminal.allowed_commands` as narrow as possible.
- Never share `PROXY_API_KEY` — treat it like any API secret.
- All Kiro authentication lives in the `kiro` CLI. The gateway never touches credentials.

---

## Support

If this project is useful, consider supporting it:

[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)

## License

AGPL-3.0 — preserving upstream license requirements.
