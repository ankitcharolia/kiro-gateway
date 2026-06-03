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

- The gateway exposes ACP JSON-RPC endpoints.
- The gateway creates sessions and forwards prompts to a local `kiro acp` subprocess.
- This is the preferred mode.

### 2. OpenAI shim mode
Use this for tools that only support OpenAI-style chat completions.

- `/v1/chat/completions`
- `/v1/models`

The gateway translates OpenAI requests into ACP `session/prompt` flows and returns aggregated responses.

### 3. Anthropic shim mode
Use this for tools that only support Anthropic message APIs.

- `/v1/messages`
- `/v1/models`

The gateway translates Anthropic-style messages into ACP `session/prompt` flows and returns aggregated responses.

## Quick start

### Requirements
- Python 3.11+
- `kiro` CLI installed and authenticated
- local shell access to run `kiro`

### Start

```bash
cp .env.example .env
python main.py
```

### Key env vars

```env
PROXY_API_KEY=change-me
KIRO_CLI_COMMAND=kiro
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true
```

## Supported clients

### Native ACP clients
Any editor/application that supports ACP can connect directly through the ACP interface.

### OpenAI-compatible clients
Examples: tools that only allow a custom OpenAI base URL.

Set:
- Base URL: `http://localhost:8000/v1`
- API key: `PROXY_API_KEY`

### Anthropic-compatible clients
Examples: tools that only allow a custom Anthropic base URL.

Set:
- Base URL: `http://localhost:8000`
- Header: `x-api-key: <PROXY_API_KEY>`

## Architecture

### Core components

| Component | Purpose |
|---|---|
| `kiro/acp_client.py` | Runs `kiro` CLI in ACP mode and exchanges JSON-RPC messages |
| `kiro/acp_models.py` | Pydantic models for ACP requests and responses |
| `kiro/routes_acp.py` | ACP endpoints |
| `kiro/routes_openai_shim.py` | OpenAI-to-ACP translation |
| `kiro/routes_anthropic_shim.py` | Anthropic-to-ACP translation |
| `kiro/shim_service.py` | Shared message/session orchestration |

## Limitations

- Streaming support in the shims is implemented as a compatibility layer, not a full ACP event mirror.
- Tool-calling parity depends on what the downstream client expects.
- Some ACP capabilities such as filesystem or terminal mediation may need richer client participation than a simple HTTP shim can provide.

## Recommended usage

- Prefer **ACP-native IDEs** whenever possible.
- Use the OpenAI/Anthropic shims only for clients that cannot yet speak ACP.
- Keep all authentication in the official `kiro` CLI.

## License

AGPL-3.0, preserving upstream license requirements.
