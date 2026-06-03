# Kiro Gateway — ACP Mode

> ⚠️ **Compliance Notice:** The original kiro-gateway used Kiro's internal API directly, which violates Kiro's Terms of Service. This fork has been rewritten to route all requests through `kiro-cli` via the [Agent Client Protocol (ACP)](https://agentclientprotocol.com) — the officially approved integration path.

## How It Works

```
Cursor / Cline / Kilo Code / OpenCode / Hermes / Zed
               ↓  OpenAI or Anthropic API  (or native ACP)
         kiro-gateway  (this repo)
               ↓  ACP JSON-RPC over stdio
           kiro-cli  (official Kiro client)
               ↓
          Kiro Backend
```

## Prerequisites

### 1. Install kiro-cli

```bash
# macOS
brew install kiro-cli

# Linux
curl -fsSL https://kiro.dev/install.sh | sh

# Windows
winget install Kiro.CLI
```

### 2. Log in

```bash
kiro-cli auth login
```

This opens a browser window. Log in with your Kiro account. Your credentials are stored by kiro-cli — the gateway never touches them.

### 3. Install gateway dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the gateway

```bash
python main_acp.py
# Or:
python main_acp.py --port 9000
```

The gateway will:
1. Spawn `kiro-cli acp` as a subprocess
2. Perform the ACP `initialize` handshake
3. Listen for requests from your editors

## Tool Configuration

### Cursor

Settings → Models → Add Model:
- **Provider:** OpenAI Compatible
- **Base URL:** `http://localhost:8000/v1`
- **API Key:** any non-empty string (e.g. `kiro`)
- **Model:** `claude-sonnet-4-5`

### Cline (VS Code)

Settings:
- **API Provider:** OpenAI Compatible
- **Base URL:** `http://localhost:8000/v1`
- **API Key:** `kiro`
- **Model:** `claude-sonnet-4-5`

### Kilo Code (VS Code)

Settings:
- **Provider:** OpenAI Compatible
- **Base URL:** `http://localhost:8000/v1`
- **API Key:** `kiro`
- **Model:** `claude-sonnet-4-5`

### OpenCode (Hermes agent)

`~/.config/opencode/config.json`:
```json
{
  "providers": {
    "kiro": {
      "name": "Kiro (via ACP)",
      "apiKey": "kiro",
      "baseURL": "http://localhost:8000/v1",
      "models": [
        {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5"}
      ]
    }
  }
}
```

### Zed (native ACP)

Zed supports ACP natively. Add to `~/.config/zed/settings.json`:
```json
{
  "agent": {
    "profiles": {
      "kiro-gateway": {
        "name": "Kiro (via gateway)",
        "tools": {},
        "enable_all_context_servers": true
      }
    }
  }
}
```
Or connect Zed directly to `kiro-cli acp` (bypassing this gateway).

### JetBrains IDEs

Settings → AI Assistant → Agents → Add Agent:
- **Name:** Kiro Gateway
- **URL:** `http://localhost:8000/acp`
- **Type:** ACP

### Claude Code / OpenClaw

```bash
export ANTHROPIC_BASE_URL=http://localhost:8000/v1
export ANTHROPIC_API_KEY=kiro
claude
```

## Available Endpoints

| Endpoint | Protocol | For |
|---|---|---|
| `POST /v1/chat/completions` | OpenAI | Cursor, Cline, Kilo Code, OpenCode, OpenClaw |
| `POST /v1/messages` | Anthropic | Claude Code, Cursor (Anthropic mode) |
| `GET /v1/models` | OpenAI | Model discovery |
| `POST /acp/session/new` | ACP native | Zed, JetBrains (native ACP) |
| `POST /acp/session/prompt` | ACP native | Zed, JetBrains (native ACP, SSE) |
| `POST /acp/session/cancel` | ACP native | Cancel in-progress request |
| `GET /acp/health` | — | Health check |
| `GET /health` | — | Health check |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KIRO_CLI_CMD` | `kiro-cli` | Path to kiro-cli binary |
| `KIRO_CWD` | current dir | Working directory for kiro-cli |
| `SERVER_HOST` | `0.0.0.0` | Bind address |
| `SERVER_PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `INFO` | Logging level |

## Troubleshooting

**`kiro-cli not found`**
→ Install kiro-cli and ensure it's in `PATH`. Run `which kiro-cli`.

**`503 ACP session manager not available`**
→ The gateway failed to start kiro-cli. Check logs for the error.

**`kiro-cli auth error`**
→ Run `kiro-cli auth login` to authenticate.

**Slow first response**
→ kiro-cli takes 2-5s to initialize on first launch. Subsequent requests are fast.
