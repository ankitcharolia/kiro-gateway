# ACP-compliant Kiro Gateway

This fork pivots `kiro-gateway` away from direct token/API interception and toward an ACP-based architecture aligned with Kiro's stated allowed usage.

## Allowed usage basis

Kiro states that subscriptions may be used with:
- Kiro IDE
- Kiro CLI
- Kiro Web
- ACP-compatible IDEs
- software-development automation such as reviews during CI/CD

Kiro also states that "OpenClaw and similar tools that leverage third-party harnesses" are prohibited.

This fork therefore uses **Kiro CLI as the official execution engine** and exposes:
- an **ACP agent transport** for ACP-compatible IDEs
- an optional **OpenAI-compatible shim** for tools that can only speak OpenAI APIs
- an optional **Anthropic-compatible shim** for tools that can only speak Anthropic APIs

The intended compliance model is:

```text
ACP client / OpenAI shim client / Anthropic shim client
                    ↓
              kiro-gateway
                    ↓
               kiro CLI (official)
                    ↓
               Kiro service
```

## Important note

This architecture is designed to route all execution through `kiro` CLI instead of private reverse-engineered APIs. Final compliance depends on Kiro's interpretation of whether protocol translation layers on top of their official ACP/CLI surface are acceptable in your context.

## Modes

### 1. ACP mode
Use this when your editor already supports ACP.

- The gateway exposes ACP JSON-RPC endpoints over HTTP (`/acp/chat`, `/acp/chat/stream`).
- The gateway creates sessions and forwards prompts to a local `kiro acp` subprocess.
- Streaming mirrors ACP progress events 1:1 as typed SSE events (`acp_text`, `acp_tool_call`, `acp_thinking`, `acp_done`, `acp_capability`).
- This is the preferred mode.

### 2. OpenAI shim mode
Use this for tools that only support OpenAI-style chat completions.

- `GET /v1/models`
- `POST /v1/chat/completions` — streaming and non-streaming

Streaming yields tokens as they arrive from kiro-cli with no buffering. Tool-calling is fully supported: `tool_calls` deltas stream correctly and tool results sent back by the caller are forwarded to kiro-cli as a follow-up prompt.

### 3. Anthropic shim mode
Use this for tools that only support Anthropic message APIs.

- `GET /v1/models`
- `POST /v1/messages` — streaming and non-streaming

Streaming follows the Anthropic SSE event taxonomy exactly (`message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`). Tool use blocks (`tool_use` / `input_json_delta`) are streamed correctly and tool results in the user turn are forwarded to kiro-cli.

## Quick start

### Requirements
- Python 3.11+
- `kiro` CLI installed and authenticated (`kiro auth login`)
- local shell access to run `kiro`

### Start

```bash
cp .env.example .env
# edit .env — set PROXY_API_KEY at minimum
python main.py
```

### Key env vars

```env
PROXY_API_KEY=change-me
KIRO_CLI_COMMAND=kiro
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

## Supported clients

### Native ACP clients
Any editor/application that supports ACP over HTTP can connect directly.

### OpenAI-compatible clients (Cursor, Cline, Continue, etc.)
Set:
- Base URL: `http://localhost:8000/v1`
- API key: value of `PROXY_API_KEY`

### Anthropic-compatible clients (Claude Code, Kilo Code, etc.)
Set:
- Base URL: `http://localhost:8000`
- Header: `x-api-key: <PROXY_API_KEY>`

## Streaming

All three modes stream tokens in real time. Events are forwarded from kiro-cli as they arrive — there is no response buffering.

| ACP event | OpenAI SSE | Anthropic SSE |
|---|---|---|
| `text` | `delta.content` chunk | `content_block_delta[text_delta]` |
| `tool_call` | `delta.tool_calls` chunk | `content_block_start[tool_use]` + `input_json_delta` |
| `thinking` | `delta.content` chunk | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | error chunk + `[DONE]` | `error` event |

## Tool calling

Both shims support the full tool-call round-trip:

1. kiro-cli emits a `tool_call` ACP event during streaming.
2. The shim translates it to the caller's format (OpenAI `function_call` / Anthropic `tool_use` block) and streams it.
3. The caller executes the tool and sends back results (`role: "tool"` message in OpenAI / `tool_result` content block in Anthropic).
4. The gateway injects the results into a follow-up `session/prompt` so kiro-cli sees them and continues the completion.

Parallel tool calls are supported in the OpenAI shim via index-tracked `tool_calls` delta chunks.

## Filesystem and terminal capability mediation

kiro-cli may request filesystem or terminal access during a session. The gateway handles these transparently via `CapabilityExecutor`:

| Capability request | What happens |
|---|---|
| `capability/readFile` | Reads file if path is within a configured `filesystem_roots` entry with `read: true`. Max 10 MB. |
| `capability/writeFile` | Writes file if path is within a root with `write: true`. Creates parent directories. |
| `capability/listDirectory` | Lists directory entries (name, type, size, URI). |
| `capability/runCommand` | Runs command if it is in the `terminal.allowed_commands` whitelist. Enforces timeout. |

For **non-ACP callers** (OpenAI/Anthropic shims), capability requests are handled automatically by the built-in executor. Capability handling runs concurrently with the token stream — it never blocks or interrupts tokens reaching the client.

For **native ACP callers** (`/acp/chat/stream`), capability requests are forwarded as `acp_capability` SSE events so the rich client can handle them directly.

### Configuring filesystem roots and terminal

Pass these in the request body as gateway extensions (standard clients ignore unknown fields):

```json
{
  "model": "claude-sonnet-4-5",
  "messages": [...],
  "filesystem_roots": [
    { "uri": "file:///home/user/project", "name": "project", "read": true, "write": true }
  ],
  "terminal": {
    "allowed_commands": ["git", "npm", "python"],
    "working_directory": "/home/user/project",
    "timeout_seconds": 30
  }
}
```

## Architecture

### Core components

| Component | Purpose |
|---|---|
| `kiro/acp_client.py` | Runs `kiro` CLI in ACP mode; exchanges JSON-RPC 2.0 over stdio; routes progress events and capability requests to per-session queues |
| `kiro/acp_models.py` | Pydantic models for all ACP request/response/notification types |
| `kiro/capability_executor.py` | Handles `readFile`, `writeFile`, `listDirectory`, `runCommand` for non-ACP callers with path/command sandboxing |
| `kiro/shim_service.py` | Shared orchestration: streaming, tool-call round-trips, capability mediation, session lifecycle |
| `kiro/routes_acp.py` | Native ACP-over-HTTP endpoints (`/acp/chat`, `/acp/chat/stream`) |
| `kiro/routes_openai_shim.py` | OpenAI-to-ACP translation (`/v1/chat/completions`, `/v1/models`) |
| `kiro/routes_anthropic_shim.py` | Anthropic-to-ACP translation (`/v1/messages`, `/v1/models`) |

## Recommended usage

- Prefer **ACP-native IDEs** whenever possible — they get the full event stream without translation overhead.
- Use the OpenAI/Anthropic shims for clients that cannot yet speak ACP natively.
- Keep all authentication in the official `kiro` CLI — the gateway never touches credentials.
- Scope `filesystem_roots` to the minimum required directories and keep `write: false` unless the agent genuinely needs to write files.
- Keep `terminal.allowed_commands` as narrow as possible.

## License

AGPL-3.0, preserving upstream license requirements.
