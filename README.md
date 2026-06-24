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

For tools that only understand the OpenAI API (Cursor, Cline, Continue, OpenCode, Hermes-agent, OpenClaw, Oh My Pi, …).

| Endpoint | Description |
|---|---|
| `GET /v1/models` | List available models (live catalogue from kiro-cli, with fallback) |
| `GET /v1/models/{model}` | Retrieve a single model object (probed by some harnesses, e.g. hermes-agent) |
| `POST /v1/chat/completions` | Streaming and non-streaming completions |
| `POST /v1/responses` | OpenAI Responses API (streaming and non-streaming) |
| `POST /v1/embeddings` | Returns `501 Not Implemented` — kiro-cli/ACP provides no embeddings model |

### 3. Anthropic shim

For tools that only understand the Anthropic API (Claude Code, Kilo Code, Craft-agent, OpenClaw, Oh My Pi, …).

| Endpoint | Description |
|---|---|
| `GET /v1/models` | List available models (live catalogue from kiro-cli, with fallback) |
| `GET /v1/models/{model}` | Retrieve a single model object |
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
# Expose kiro-cli's own built-in tool calls to the OpenAI/Anthropic shims as
# executable tool_calls/tool_use? Default false — kiro-cli runs them itself and
# returns the final answer, so the shims work with every harness. Enable only
# for ACP-aware UIs that just display tool activity (the native /acp/chat route
# always surfaces it).
ACP_SURFACE_TOOL_CALLS=false
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

_(Cursor, Cline, Continue, OpenCode, Hermes-agent, OpenClaw, Oh My Pi, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000/v1` |
| API Key | value of `KIRO_GATEWAY_API_KEY` |
| Model | `claude-sonnet-4.6` (or any Kiro-supported model: `auto`, `claude-opus-4.8`, …) |

### Anthropic-compatible clients

_(Claude Code, Kilo Code, Craft-agent, OpenClaw, Oh My Pi, …)_

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8000` |
| API Key header | `x-api-key: <KIRO_GATEWAY_API_KEY>` |
| Model | `claude-sonnet-4.6` |

### How to integrate an AI harness

Ready-to-use config examples for common harnesses live in
[`examples/clients/`](examples/clients/). Each file is named
`<harness>-<api>` so you can pick the one matching your tool and the API it
speaks, copy it to the harness's config location, and set
`KIRO_GATEWAY_API_KEY` as the key.

| Harness | API | Example config | Save to |
|---|---|---|---|
| OpenCode | OpenAI | [`opencode-openai.json`](examples/clients/opencode-openai.json) | `~/.config/opencode/opencode.json` |
| Kilo Code | OpenAI | [`kilocode-openai.json`](examples/clients/kilocode-openai.json) | `~/.config/kilo/kilo.jsonc` |
| Kilo Code | Anthropic | [`kilocode-anthropic.json`](examples/clients/kilocode-anthropic.json) | `~/.config/kilo/kilo.jsonc` |
| Hermes-agent | OpenAI | [`hermes-agent-openai.yaml`](examples/clients/hermes-agent-openai.yaml) | `~/.hermes/config.yaml` |
| OpenClaw | OpenAI | [`openclaw-openai.json`](examples/clients/openclaw-openai.json) | OpenClaw config (merge the `providers` block) |
| OpenClaw | Anthropic | [`openclaw-anthropic.json`](examples/clients/openclaw-anthropic.json) | OpenClaw config (merge the `providers` block) |
| Oh My Pi | OpenAI | [`oh-my-pi-openai.yaml`](examples/clients/oh-my-pi-openai.yaml) | `~/.omp/agent/models.yml` |
| Oh My Pi | Anthropic | [`oh-my-pi-anthropic.yaml`](examples/clients/oh-my-pi-anthropic.yaml) | `~/.omp/agent/models.yml` |

Each example carries its destination path as a comment on the first line.
Replace the placeholder `change-me` (or `${KIRO_GATEWAY_API_KEY}`) with your
gateway key before saving.

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

## Error handling

ACP/upstream failures are classified into the correct HTTP status code and
returned in each API's **native error shape** (instead of a generic `502` with
a bare `{"detail": ...}` body), so harness retry/back-off logic behaves
correctly. The same classification applies to **both shims** and **both**
streaming and non-streaming paths.

| Upstream condition | HTTP status | OpenAI error `type` | Anthropic error `type` |
|---|---|---|---|
| Rate limit / throttle / quota / `429` | `429` | `rate_limit_error` | `rate_limit_error` |
| Overloaded / unavailable / capacity | `503` | `server_error` | `overloaded_error` |
| Timeout / deadline exceeded | `504` | `server_error` | `api_error` |
| Any other failure (default) | `502` | `server_error` | `api_error` |

- **Non-streaming.** The response status code is the mapped code and the body
  is the native envelope — OpenAI `{"error": {"message", "type", "code",
  "param"}}`; Anthropic `{"type": "error", "error": {"type", "message"}}`. When
  the upstream message carries a retry hint (e.g. "retry after 30"), a
  `Retry-After` header is added (most relevant for `429`).
- **Streaming.** The SSE stream has already begun (HTTP `200`), so the mapped
  error `type` is carried in the terminal error event: an OpenAI error chunk
  (followed by `[DONE]`), a Responses `response.failed` event, or an Anthropic
  `error` event.

Classification is message-based (kiro-cli surfaces upstream conditions as
text), so it works identically whether the failure arrives as a JSON-RPC error
on a non-streaming completion or as a streaming error event.

---

## System & developer roles

Instruction provenance is preserved rather than flattened into anonymous user
text. ACP has no dedicated system channel, so a fresh-session prompt is
serialised into a single text block — but each message keeps its role label
(`System:` / `Developer:` / `User:` / `Assistant:`) and its order, and multiple
system messages are kept distinct rather than merged.

| Client input | Carried as | Rendered prompt label |
|---|---|---|
| OpenAI `system` message | `system` role | `System:` |
| OpenAI `developer` message | `developer` role | `Developer:` |
| OpenAI `tool` message | `user` role (with `[tool_result id=…]` marker) | `User:` |
| OpenAI Responses `instructions` | `system` role | `System:` |
| Anthropic `system` field (string or block list) | `system` role | `System:` |

> kiro-cli treats the whole serialised prompt as one turn; these labels make
> the system/developer instructions legible to the agent without inventing a
> system channel the protocol does not expose.

---

## Generation parameters

Sampling parameters are accepted on both shims, validated, and **forwarded** to
`kiro-cli` on every turn (streaming and non-streaming) inside the ACP
`session/prompt` request, under the protocol's reserved `_meta` extension field:

```jsonc
"params": {
  "sessionId": "…",
  "prompt": [ … ],
  "_meta": {
    "generationConfig": {        // only the keys the caller set are included
      "temperature": 0.2,
      "maxTokens": 1024,
      "topP": 0.9,
      "topK": 40,
      "stopSequences": ["\n\n"]
    }
  }
}
```

| Client field | Forwarded as | OpenAI | Anthropic |
|---|---|---|---|
| `temperature` | `temperature` | ✓ | ✓ |
| `max_tokens` / `max_output_tokens` | `maxTokens` | ✓ | ✓ |
| `top_p` | `topP` | ✓ | ✓ |
| `top_k` | `topK` | — | ✓ |
| `stop` / `stop_sequences` | `stopSequences` | ✓ | ✓ |

> [!IMPORTANT]
> **kiro-cli currently treats these sampling parameters as no-ops.** Verified
> against a live `kiro-cli` 2.8.0 ACP probe: the agent advertises no sampling
> capability, accepts the values without error, and produces identical output
> with or without them (`max_tokens` does not cap output, `stop` does not stop,
> `temperature`/`top_p`/`top_k` have no effect). They are forwarded via `_meta`
> (a schema-safe extension point) so they reach kiro-cli and take effect
> automatically if a future version honors them — no gateway change required.
>
> The **one** per-request generation control kiro-cli honors today is the
> **model** (`model` → `session/set_model`); see [Models](#modes). Other OpenAI
> params (`seed`, `n`, `frequency_penalty`, `presence_penalty`, `logit_bias`)
> are likewise not honored by ACP and are ignored.

---

## Usage & token accounting

Both shims return a `usage` object on every completion. The gateway **prefers
real counts** reported by `kiro-cli` and otherwise falls back to a **consistent
local tokenizer estimate** (tiktoken `cl100k_base` + a Claude correction
factor — the same estimator used by `POST /v1/messages/count_tokens`), so a
usage field is never silently `0`.

| API / mode | Usage surface |
|---|---|
| OpenAI `/v1/chat/completions` (non-stream) | `usage.{prompt_tokens, completion_tokens, total_tokens}` |
| OpenAI `/v1/chat/completions` (stream) | a final usage-only chunk (`choices: []`) **when** the request sets `stream_options: {"include_usage": true}` (OpenAI semantics) |
| OpenAI `/v1/responses` (stream + non-stream) | `usage.{input_tokens, output_tokens, total_tokens}` |
| Anthropic `/v1/messages` (non-stream) | `usage.{input_tokens, output_tokens}` |
| Anthropic `/v1/messages` (stream) | `input_tokens` in `message_start`, `output_tokens` in `message_delta` |

- **Real vs. estimated.** Each field is resolved independently: a reported,
  positive count wins; otherwise that field is estimated. `kiro-cli` 2.x does
  not report usage over ACP (its `/usage` view is an interactive REPL command,
  not part of the `session/prompt` result), so today most counts are estimates.
  The gateway already reads any usage `kiro-cli` emits — on the prompt result,
  a `session/update`, or under the ACP `_meta` extension — so real counts are
  surfaced automatically if a future `kiro-cli` provides them, with **no
  gateway change required**.
- **`/usage` is not a harness feature.** `/usage` is a slash command of the
  interactive `kiro-cli` chat TUI; harnesses (OpenAI/Anthropic clients) never
  issue it — they read the `usage` object on each completion response, which the
  gateway always fills. Sending the literal text `/usage` as a prompt does not
  return token counts either: over ACP it is treated as ordinary prompt text,
  and the gateway opens a fresh, stateless session per request, so there is no
  cumulative interactive session for `/usage` to report on.
- **Estimates are approximate.** They are suitable for budgeting and cost
  displays, not exact billing.

### logprobs (unsupported)

The ACP path exposes no token log-probabilities, so `logprobs` is **not
supported**. The OpenAI shim accepts the `logprobs` / `top_logprobs` request
fields for API compatibility and reports `"logprobs": null` on each choice;
the value is never populated. The Anthropic Messages API has no logprobs
feature.

---

## Tool-call round-trips

> [!IMPORTANT]
> **How tools work with kiro-cli (verified against a live `kiro-cli` 2.8.0 ACP
> probe).** `kiro-cli` over ACP is an **autonomous agent**, not a raw
> function-calling model. There are two distinct cases:
>
> 1. **kiro-cli's own built-in tools (code, file read/edit, shell/command
>    execution, AWS, web search) — fully supported through the gateway.** When a
>    harness sends a prompt, kiro-cli decides to run these itself, asks the
>    gateway for permission, executes them inside the session working directory,
>    and continues the turn. *Probe confirmation:* a prompt asking it to run
>    `echo <marker>` produced a `tool_call` (`kind: execute`), one
>    `session/request_permission` (auto-approved `allow_once`), and the marker
>    appeared in the streamed response. So harnesses **can** drive kiro-cli's
>    built-in agentic toolset through the gateway. By default the shims present
>    the result as a normal completion (the tool activity is **not** surfaced as
>    executable `tool_calls`/`tool_use` — see `ACP_SURFACE_TOOL_CALLS` below);
>    harnesses never execute these tools themselves.
> 2. **Client-declared tools (the harness's own functions) — not honored by
>    kiro-cli today.** Definitions sent on `session/prompt` (whether as a
>    top-level `tools` field or under `_meta.tools`) are accepted without error
>    but ignored: in the probe the model replied that it had *no* such tool and
>    listed only its built-ins. ACP's only channel for *external* tools is **MCP
>    servers** registered at `session/new` (kiro-cli advertises
>    `mcpCapabilities.http: true`), where the **MCP server — not the harness —**
>    executes the tool. The gateway still **forwards** normalized client tool
>    definitions under the schema-safe `_meta.tools` extension (consistent with
>    the sampling-param forwarding) so they reach kiro-cli and take effect
>    automatically if a future version ingests them — but **OpenAI/Anthropic-style
>    client-side function calling does not round-trip through kiro-cli today.**
>    See [issue #31](https://github.com/ankitcharolia/kiro-gateway/issues/31).

**By default the shims do not surface kiro-cli's built-in tool activity as
executable `tool_calls`/`tool_use`** (`ACP_SURFACE_TOOL_CALLS=false`). kiro-cli
runs the tools itself and streams the finished answer, so a harness receives a
normal completion (`finish_reason=stop` / `end_turn`) — never a tool call for a
tool it didn't declare and can't run. This is what makes the gateway work with
every harness out of the box.

When `ACP_SURFACE_TOOL_CALLS=true` (opt-in, for ACP-aware UIs that just display
activity), the round-trip is:

1. `kiro-cli` decides to run one of its built-in tools and asks the gateway for
   permission via `session/request_permission`.
2. The gateway approves or rejects based on `ACP_TRUST_TOOLS` (see below).
3. The tool invocation is streamed to the caller as a `tool_call` event,
   translated to the caller's format (`tool_calls` / `tool_use`).
4. `kiro-cli` executes the tool itself and continues the same turn, streaming
   the resulting assistant text.

The native `/acp/chat` route always surfaces this activity (ACP clients display
it and never execute it, per the protocol). Either way, tool execution and
continuation happen entirely inside `kiro-cli` within a single turn — callers
never execute tools themselves.

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

> **Surfacing vs. execution.** `ACP_TRUST_TOOLS` controls whether kiro-cli is
> *allowed to run* its built-in tools; `ACP_SURFACE_TOOL_CALLS` (default
> `false`) controls whether that activity is *shown* to the OpenAI/Anthropic
> shims as `tool_calls`/`tool_use`. Keep `ACP_TRUST_TOOLS=true` so the agent can
> use its full toolset, and leave `ACP_SURFACE_TOOL_CALLS=false` so harnesses
> receive a clean completion instead of a tool call they cannot execute.

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
