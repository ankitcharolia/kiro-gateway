# ACP-Compliant Kiro Gateway

[![CI](https://github.com/ankitcharolia/kiro-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitcharolia/kiro-gateway/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)
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
| **Python 3.14+** | Required |

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
# How to handle a requested model that isn't in kiro-cli's live catalogue.
#   warn (default) = log a warning and fall back to the session default;
#   strict         = reject with a 404 (native error shape);
#   off            = forward silently (legacy). Validation is skipped until the
# live catalogue is discovered (first session).
MODEL_VALIDATION=warn
# Optional model-id aliases so a harness that hardcodes a foreign id can be
# mapped to a real kiro-cli model (resolved before validation). Comma-separated
# alias=target pairs.
MODEL_ALIASES=
# Enforce max_tokens by capping the output stream (kiro-cli doesn't honor it).
# Default false (no cap). true = stop generation at the limit (finish_reason
# length). stop sequences are always enforced when a client sends them.
ENFORCE_MAX_TOKENS=false

# ── Tool execution ────────────────────────────────────────────────────
# kiro-cli runs its own built-in tools (file edits, command execution) and
# asks the gateway for permission first. true = auto-approve each request,
# false = reject (read/answer-only posture).
ACP_TRUST_TOOLS=true
# How the shims present kiro-cli's own built-in tool activity. Default false =
# inline, non-executable reasoning text (interleaved with thinking, like
# kiro-cli; needs ACP_SURFACE_THINKING=true) — works with every harness. true =
# executable tool_calls/tool_use (only for ACP-aware UIs that just display
# activity). The native /acp/chat route always surfaces a structured tool call.
ACP_SURFACE_TOOL_CALLS=false
# Surface kiro-cli's reasoning/"thinking" in each API's native reasoning shape
# (OpenAI reasoning_content / Responses reasoning items; Anthropic thinking
# blocks). Default true — reasoning is additive and never changes the final
# answer. Set false to emit only the final answer.
ACP_SURFACE_THINKING=true
ACP_WORKSPACE_DIR=               # Default session cwd (defaults to process cwd)
ACP_TIMEOUT=120                  # Seconds to await a JSON-RPC response
ACP_STDIO_MAX_BYTES=16777216     # Max bytes per ACP stdout line (16 MiB) — raise
                                 # for very large tool outputs in long agent turns

# ── ACP session mode & spawn args ─────────────────────────────────────
# Agent persona selected per session via session/set_mode (kiro_default,
# code, kiro_planner, kiro_guide). Empty = kiro-cli's default mode.
KIRO_ACP_MODE=
# Flags passed to `kiro-cli acp` at launch (all optional). The engine is
# pinned explicitly (default v2) so a future change to kiro-cli's default
# engine can't silently alter behaviour. v3 needs host-mediated auth the
# gateway does not implement (generation fails) — keep v2.
KIRO_ACP_ENGINE=v2               # v1 | v2 | v3
KIRO_ACP_AGENT=                  # --agent: (custom) agent config for the first session
KIRO_ACP_MODEL=                  # --model: initial session model (per-request model still wins)
KIRO_ACP_EFFORT=                 # --effort: low | medium | high | xhigh | max
KIRO_ACP_EXTRA_ARGS=             # extra raw args appended verbatim (shell-quoted)

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
| `tool_call` | folded into `reasoning_content` by default; `delta.tool_calls` chunk when `ACP_SURFACE_TOOL_CALLS=true` | folded into a `thinking` block by default; `content_block_start[tool_use]` + `input_json_delta` when surfacing |
| `thinking` | `delta.reasoning_content` chunk (Responses: `response.reasoning_summary_text.delta`) | `content_block_start[thinking]` + `thinking_delta` |
| `plan` (task list) | folded into `reasoning_content` (Responses reasoning item) | folded into a `thinking` block |
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

## Embeddings (not supported — by design)

`POST /v1/embeddings` returns **`501 Not Implemented`** in the OpenAI-native
error envelope (`{"error": {"type": "invalid_request_error", "code":
"embeddings_not_supported", "message": …}}`). kiro-cli over ACP exposes **no
embeddings model** — it only generates text — so the gateway has no compliant
way to produce embedding vectors. It deliberately neither 404s (clients read
that as a misconfigured base URL) nor fabricates vectors (which would silently
corrupt search results).

**Harness features that depend on embeddings will not work through this
gateway**, including:

- **RAG / document indexing** (building a vector store over a codebase or docs).
- **Semantic code search** (embedding-based "find similar code").
- **Embedding-based long-term memory** (vector recall of past context).

Chat/completion features are unaffected — only the embeddings step fails, with a
clear, parseable `501`.

### Decision: no built-in embeddings passthrough

A built-in opt-in passthrough to a user-configured embeddings provider was
**considered and declined**. It would require the gateway to **hold a
third-party API credential** and **transmit request data to an endpoint outside
kiro-cli** — both of which break the project's foundational compliance model
(*only the official binary is invoked; no credential handling; no routing
through other providers*). Embeddings are therefore kept entirely out of this
gateway.

**Recommended pattern:** point your harness's **embedding model** at a dedicated
embeddings provider directly (e.g. an OpenAI/local-embeddings endpoint),
configured separately from this gateway, while the **chat/completion model**
points at the gateway. Most harnesses let you configure the embedding and chat
providers independently. This keeps embeddings fully outside the single-account,
credential-free compliance path.

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
| OpenAI `assistant` `tool_calls` | `assistant` role (with `[tool_use id=… name=…]` markers) | `Assistant:` |
| OpenAI `tool` message | `user` role (with `[tool_result id=…]` marker) | `User:` |
| OpenAI Responses `instructions` | `system` role | `System:` |
| Anthropic `system` field (string or block list) | `system` role | `System:` |
| Anthropic `tool_use` block | `assistant` role (with `[tool_use id=… name=…]` marker) | `Assistant:` |
| Anthropic `tool_result` block | `user` role (with `[tool_result id=…]` marker) | `User:` |

> kiro-cli treats the whole serialised prompt as one turn; these labels make
> the system/developer instructions legible to the agent without inventing a
> system channel the protocol does not expose.

### Multi-turn & tool history fidelity

ACP's `session/prompt` carries a **single, role-less** list of content blocks
(the protocol's content block has no per-message `role` field), and ACP keeps
multi-turn state server-side across prompts within one session. The gateway is
**stateless** — a fresh session per request — so it must serialise the whole
conversation into one prompt. The faithful maximum ACP allows is therefore a
single text block whose turns are delimited by stable `Role:` labels, in order,
separated by blank lines:

- **Turn boundaries** are explicit and ordered (`System:` / `Developer:` /
  `User:` / `Assistant:`); multiple system messages stay distinct.
- **Tool turns are preserved, not dropped.** A prior assistant tool call —
  OpenAI `tool_calls` or Anthropic `tool_use` — is rendered as
  `[tool_use id=… name=…]` followed by its arguments, and a tool result
  (OpenAI `tool` role or Anthropic `tool_result`) as `[tool_result id=…]` with
  its content. The two shims use the **same markers**, so the transcript
  kiro-cli sees is consistent across both APIs.
- **Limitation (documented).** Because ACP attaches no role to a content block,
  the gateway does not — and cannot — send structured, role-tagged turns;
  splitting the transcript into multiple blocks would add no structural
  fidelity (kiro-cli concatenates them) while risking ambiguous boundaries. A
  single labelled, blank-line-delimited block is the stable, faithful
  representation. Client-side function calling itself is still not honored by
  kiro-cli over ACP (see [Tool-call round-trips](#tool-call-round-trips) and
  issue #31); this section is purely about how prior tool turns are **carried**
  in the prompt history.

---

## Image & document input

The gateway forwards **image** attachments to kiro-cli and surfaces
**documents/audio** as text instead of silently dropping them. Capability ground
truth — verified against a **live kiro-cli 2.10.0 probe** (`initialize` →
`agentCapabilities.promptCapabilities`): `{"image": true, "audio": false,
"embeddedContext": false}`.

| Input | Behaviour |
|---|---|
| OpenAI `image_url` / Responses `input_image` — **base64 data URL** | Forwarded to kiro-cli as an ACP image content block (`{"type":"image","mimeType":…,"data":…}`) |
| Anthropic `image` — **base64 source** | Forwarded as an ACP image content block |
| Image given as a **remote URL** | **Not fetched** (kiro-cli has no URL content-block capability; fetching untrusted URLs server-side is an SSRF risk). Surfaced as text: `[image: <url> (remote URL not fetched …)]` |
| **Text-like document** (`text/*`, JSON, XML, CSV, …) | Decoded and injected as text: `[document: <name>]\n<content>` — the model reads it |
| **PDF document** | Text extracted with `pypdf` (a standard dependency) — works out of the box; a scanned/image-only PDF that yields no text falls back to a placeholder |
| **Other binary document** / **audio** | Explicit placeholder (`[document: … omitted — unsupported by kiro-cli]` / `[audio omitted …]`) — never a silent drop |

- **Both shims, both modes.** Images are forwarded on OpenAI `/v1/chat/completions`,
  OpenAI `/v1/responses`, and Anthropic `/v1/messages`, in streaming and
  non-streaming paths. Verified end-to-end against the live probe: a forwarded
  32×32 PNG made the model answer with the image's colour.
- **Why documents aren't forwarded as binary.** kiro-cli advertises
  `embeddedContext: false`, so it rejects embedded resources on the wire. The
  gateway therefore reduces documents to text (extracted or placeholder) so the
  model is always aware an attachment existed.
- **Prompt shape.** Images travel as their own ACP content blocks appended after
  the labelled text transcript, with an inline `[image]` marker left in the turn
  text to mark where each appeared (ACP content blocks carry no role; see
  [Multi-turn & tool history fidelity](#multi-turn--tool-history-fidelity)).

---

## Reasoning / thinking

kiro-cli emits reasoning ("thinking") while it works. The gateway surfaces it
in **each API's native reasoning shape** so reasoning-aware harnesses (Kilo
Code, Oh My Pi, Claude Code, …) can display it. Reasoning is **additive — the
final answer text is never changed** — and is gated by `ACP_SURFACE_THINKING`
(default `true`; set `false` to emit only the final answer).

| API / mode | Reasoning surface |
|---|---|
| OpenAI `/v1/chat/completions` (stream) | `choices[].delta.reasoning_content` chunks (DeepSeek/OpenAI-compatible convention) |
| OpenAI `/v1/chat/completions` (non-stream) | `choices[].message.reasoning_content` |
| OpenAI `/v1/responses` (stream) | a `reasoning` output item + `response.reasoning_summary_part.added` / `response.reasoning_summary_text.delta` / `…done` events |
| OpenAI `/v1/responses` (non-stream) | a `{"type": "reasoning", "summary": [{"type": "summary_text", …}]}` item in `output` |
| Anthropic `/v1/messages` (stream) | `content_block_start[thinking]` + `content_block_delta[thinking_delta]` + `content_block_stop` (before the text block) |
| Anthropic `/v1/messages` (non-stream) | a `{"type": "thinking", "thinking": …}` content block (before the text block) |

- The Anthropic `thinking` blocks are emitted **without a cryptographic
  `signature`** (kiro-cli does not provide one over ACP), so they are suitable
  for **display**; they are not intended to be signed/replayed back on a
  follow-up tool turn.
- The native `/acp/chat` route always surfaces reasoning as an `acp_thinking`
  event regardless of this flag.

> [!IMPORTANT]
> **Not seeing any reasoning? It's model-dependent.** kiro-cli only emits
> thinking for some models (e.g. `claude-opus-4.8` does; `claude-sonnet-4.6`
> doesn't) and may skip it on trivial prompts — none of which affects the final
> answer. Per-request `reasoning_effort` / "thinking budget" is **advisory
> only**: kiro-cli decides based on the model, not the client param (the gateway
> forwards it under `_meta` but kiro-cli does not act on it today). `/effort` is
> an interactive-TUI command with no ACP equivalent.

### Task list / plan

kiro-cli expresses a multi-step **task list** through its built-in todo tool
(it has no standard ACP `plan` update). The gateway normalizes that into a
`plan` event and surfaces it under the **same `ACP_SURFACE_THINKING` flag**:

- **Native `/acp/chat/stream`** → a structured `acp_plan` event
  (`{entries: [{content, status}], description}`).
- **OpenAI / Anthropic shims** → the task list is rendered as a checklist and
  folded into the reasoning channel (`reasoning_content` / Responses reasoning
  item / Anthropic `thinking` block), since those APIs have no task-list field.

> kiro-cli emits the list when it's **created** (entries `pending`); it does not
> re-emit a full snapshot as items complete, so surfaced statuses reflect
> creation time. The final answer text is unaffected.

---

## Generation parameters

Sampling parameters are accepted on both shims, validated, and **forwarded** to
`kiro-cli` on every turn (streaming and non-streaming) under the ACP
`session/prompt` request's reserved `_meta.generationConfig` extension (only the
keys the caller set are included).

| Client field | Forwarded as | OpenAI | Anthropic |
|---|---|---|---|
| `temperature` | `temperature` | ✓ | ✓ |
| `max_tokens` / `max_output_tokens` | `maxTokens` | ✓ | ✓ |
| `top_p` | `topP` | ✓ | ✓ |
| `top_k` | `topK` | — | ✓ |
| `stop` / `stop_sequences` | `stopSequences` | ✓ | ✓ |

> [!IMPORTANT]
> **kiro-cli itself honors none of these over ACP**, so the gateway enforces the
> two it *can* apply to the output stream:
> - **`stop` sequences are enforced by the gateway** — generation is cut at the
>   first stop string (`finish_reason=stop`) and kiro-cli is cancelled. Always
>   on when a client supplies `stop`.
> - **`max_tokens` is enforced when `ENFORCE_MAX_TOKENS=true`** (default off) —
>   the output is capped at the limit (`finish_reason=length`). Off by default
>   to preserve the historical no-cap behaviour.
> - **`temperature` / `top_p` / `top_k` remain inert** — they steer sampling
>   during generation, which only kiro-cli can do; they are forwarded under
>   `_meta` for forward-compatibility. Other OpenAI params (`seed`, `n`,
>   `frequency_penalty`, `presence_penalty`, `logit_bias`) are likewise ignored.
> The one model control kiro-cli honors natively is the **model**
> (`session/set_model`).

---

## Structured outputs (no-op, but accepted & forwarded)

JSON mode / structured outputs (`response_format`), strict tool schemas
(`strict`) and tool-selection (`tool_choice`) are **accepted on both shims and
forwarded to `kiro-cli` under the schema-safe `_meta` extension**, but they are
**not honored over ACP today** — a request that sets them validates and
succeeds, returning free-form text (the model isn't constrained to the schema).
They are forwarded (not dropped) so they take effect automatically if a future
`kiro-cli` honors them. Mapping:

| Client field | API | Forwarded as |
|---|---|---|
| `response_format` | OpenAI chat (`json_object` / `json_schema`) | `_meta.structuredOutput.responseFormat` |
| `text` / `response_format` | OpenAI Responses (`text.format`) | `_meta.structuredOutput.responseFormat` |
| `tool_choice` | OpenAI + Anthropic | `_meta.structuredOutput.toolChoice` |
| `parallel_tool_calls` | OpenAI | accepted (no-op) |
| `strict` (per tool function) | OpenAI | `strict` on the tool in `_meta.tools` |

> [!NOTE]
> The Anthropic Messages API has **no `response_format` field** (structured
> output is expressed through tools), so only `tool_choice` is accepted there.
> Strict schemas are accepted either way (the Oh My Pi `disableStrictTools`
> workaround is no longer needed), though strict enforcement is still inert. See
> [issue #35](https://github.com/ankitcharolia/kiro-gateway/issues/35).

---

## Usage & token accounting

Both shims return a `usage` object on every completion. The gateway **prefers
real counts** reported by `kiro-cli` and otherwise falls back to a **consistent
local tokenizer estimate** (tiktoken `cl100k_base` + a Claude correction
factor — the same estimator used by `POST /v1/messages/count_tokens`), so a
usage field is never silently `0`.

| API / mode | Usage surface |
|---|---|
| OpenAI `/v1/chat/completions` (non-stream) | `usage.{prompt_tokens, completion_tokens, total_tokens, prompt_tokens_details.cached_tokens}` |
| OpenAI `/v1/chat/completions` (stream) | a final usage-only chunk (`choices: []`) **when** the request sets `stream_options: {"include_usage": true}` (OpenAI semantics) |
| OpenAI `/v1/responses` (stream + non-stream) | `usage.{input_tokens, output_tokens, total_tokens, input_tokens_details.cached_tokens}` |
| Anthropic `/v1/messages` (non-stream) | `usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}` |
| Anthropic `/v1/messages` (stream) | `input_tokens` (+ cache fields) in `message_start`, `output_tokens` in `message_delta` |

- **Real vs. estimated.** Each field is resolved independently: a reported,
  positive count wins; otherwise it's estimated. `kiro-cli` 2.x reports no usage
  over ACP today (its `/usage` is an interactive REPL command, not part of the
  `session/prompt` result), so most counts are estimates — but the gateway
  already reads any usage `kiro-cli` emits (prompt result, `session/update`, or
  `_meta`), so real counts surface automatically if a future version provides
  them. `/usage` is not a harness feature (harnesses read the `usage` object,
  not the slash command). Estimates are for budgeting, not exact billing.

### Prompt caching (no-op, but reported)

Prompt caching is **not available over ACP** (kiro-cli advertises no caching
capability). So Anthropic `cache_control` markers are **accepted as a no-op**
(validated, never a 422), and the native cache-token fields are **reported (as
`0`) rather than omitted**, keeping the `usage` shape faithful: Anthropic
`usage.cache_creation_input_tokens` / `cache_read_input_tokens`, OpenAI chat
`usage.prompt_tokens_details.cached_tokens`, OpenAI Responses
`usage.input_tokens_details.cached_tokens`. They are never estimated and surface
real counts verbatim if a future `kiro-cli` reports them.

### logprobs (unsupported)

The ACP path exposes no token log-probabilities. The OpenAI shim accepts
`logprobs` / `top_logprobs` for compatibility and reports `"logprobs": null` per
choice; the Anthropic Messages API has no logprobs feature.

---

## Tool-call round-trips

`kiro-cli` over ACP is an **autonomous agent**, not a raw function-calling
model. Two distinct cases:

1. **kiro-cli's own built-in tools** (code, file read/edit, shell, AWS, web
   search) — **fully supported.** kiro-cli decides to run them, asks the gateway
   for permission, executes them in the session directory, and continues the
   turn. Harnesses drive these and get the final answer.
2. **Client-declared tools** (the harness's own functions) — **not honored by
   kiro-cli today.** Definitions on `session/prompt` (top-level `tools` or
   `_meta.tools`) are accepted but ignored; ACP's only external-tool channel is
   **MCP servers** registered at `session/new` (executed by the MCP server, not
   the harness). The gateway still forwards client tool defs under `_meta.tools`
   for forward-compatibility, but OpenAI/Anthropic-style client-side function
   calling does **not** round-trip today. See
   [issue #31](https://github.com/ankitcharolia/kiro-gateway/issues/31).

**By default (`ACP_SURFACE_TOOL_CALLS=false`) the shims surface kiro-cli's
built-in tool activity as inline, non-executable reasoning** — each tool run
(`⚙ Reading config.py`, `⚙ Running: …`) is folded into the reasoning channel,
interleaved with thinking and before the answer (rides `ACP_SURFACE_THINKING`;
live interleaving needs streaming). The harness gets a normal completion
(`finish_reason=stop`/`end_turn`), never a tool call it can't run — so this
works with every harness. File edits render as a fenced ` ```diff ` block;
shell commands render the command + a fenced output block; file reads show only
the label.

When `ACP_SURFACE_TOOL_CALLS=true` (opt-in, for ACP-aware UIs), the activity is
instead emitted as executable-shaped `tool_calls`/`tool_use` events. The native
`/acp/chat` route always surfaces a structured tool call. Either way, tool
execution happens entirely inside `kiro-cli` within one turn — callers never
execute tools themselves.

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
> *allowed to run* its built-in tools; `ACP_SURFACE_TOOL_CALLS` controls *how*
> that activity is shown to the OpenAI/Anthropic shims. Keep
> `ACP_TRUST_TOOLS=true` so the agent can use its full toolset. With
> `ACP_SURFACE_TOOL_CALLS=false` (default) the activity is shown as inline
> reasoning text (interleaved, non-executable) so every harness works; set it
> `true` only for ACP-aware UIs that want executable `tool_calls`/`tool_use`.

> **Security:** with `ACP_TRUST_TOOLS=true` the agent can write files and run
> commands in `ACP_WORKSPACE_DIR` without human confirmation. Use `false` for a
> read/answer-only deployment, and scope `ACP_WORKSPACE_DIR` to a project
> directory.

A request may also pass `filesystem_roots` to set the session's working
directory; the first root's path is used as the `cwd` for `session/new`.

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
terms. If you plan to redistribute the Kiro CLI, review
the redistribution terms first. See [`COMPLIANCE.md`](COMPLIANCE.md) for details.

## License

AGPL-3.0 — preserving upstream license requirements.
