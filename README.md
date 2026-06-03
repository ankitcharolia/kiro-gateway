<div align="center">

# 👻 Kiro Gateway 
**Proxy gateway for Kiro API (Amazon Q Developer / AWS CodeWhisperer)**
## (fork of https://github.com/jwadow/kiro-gateway)

🇬🇧 English • [🇷🇺 Русский](docs/ru/README.md) • [🇨🇳 中文](docs/zh/README.md) • [🇪🇸 Español](docs/es/README.md) • [🇮🇩 Indonesia](docs/id/README.md) • [🇧🇷 Português](docs/pt/README.md) • [🇯🇵 日本語](docs/ja/README.md) • [🇰🇷 한국어](docs/ko/README.md)

Made with ❤️ by [@Jwadow](https://github.com/jwadow)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Sponsor](https://img.shields.io/badge/💖_Sponsor-Support_Development-ff69b4)](#-support-the-project)

*Use Claude models from Kiro with Claude Code, OpenCode, OpenClaw, Claw Code, Codex app, Cursor, Cline, Roo Code, Kilo Code, Obsidian, OpenAI SDK, LangChain, Continue and other OpenAI or Anthropic compatible tools*

[Models](#-supported-models) • [Features](#-features) • [Quick Start](#-quick-start) • [Configuration](#%EF%B8%8F-configuration) • [💖 Sponsor](#-support-the-project)

</div>

---

## 🤖 Available Models (Free List)

> ⚠️ **Important:** Model availability depends on your Kiro tier (free/paid). The gateway provides access to whatever models are available in your IDE or CLI based on your subscription. The list below shows models commonly available on the **free tier**.

> 🔒 **Claude Opus 4.5** was removed from the free tier on January 17, 2026. It may be available on paid tiers — check your IDE/CLI model list.

🚀 **Claude Sonnet 4.5** — Balanced performance. Great for coding, writing, and general-purpose tasks.

⚡ **Claude Haiku 4.5** — Lightning fast. Perfect for quick responses, simple tasks, and chat.

📦 **Claude Sonnet 4** — Previous generation. Still powerful and reliable for most use cases.

💤 **GLM-5** — Open MoE model (744B params, 40B active). Advanced model for complex systems engineering and long-horizon agentic tasks.

🐋 **DeepSeek-V3.2** — Open MoE model (685B params, 37B active). Balanced performance for coding, reasoning, and general tasks.

🧩 **MiniMax M2.5** — Open MoE model (230B params, 10B active). Enhanced version with improved reasoning and task handling.

🧩 **MiniMax M2.1** — Open MoE model (230B params, 10B active). Great for complex tasks, planning, and multi-step workflows.

🤖 **Qwen3-Coder-Next** — Open MoE model (80B params, 3B active). Coding-focused. Excellent for development and large projects.

> 💡 **Smart Model Resolution:** Use any model name format — `claude-sonnet-4-5`, `claude-sonnet-4.5`, or even versioned names like `claude-sonnet-4-5-20250929`. The gateway normalizes them automatically.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔌 **OpenAI-compatible API** | Works with any OpenAI-compatible tool |
| 🔌 **Anthropic-compatible API** | Native `/v1/messages` endpoint |
| 🔒 **Compliance Mode** | Single-account enforced; rate limits surfaced to caller |
| 🌐 **VPN/Proxy Support** | HTTP/SOCKS5 proxy for restricted networks |
| 🧠 **Extended Thinking** | Reasoning is exclusive to our project |
| 👁️ **Vision Support** | Send images to model |
| 🔍 **Web Search** | Search the web for current information |
| 🛠️ **Tool Calling** | Supports function calling |
| 💬 **Full message history** | Passes complete conversation context |
| 📡 **Streaming** | Full SSE streaming support |
| 🔄 **Retry Logic** | Automatic retries on errors (403, 429, 5xx) |
| 📋 **Extended model list** | Including versioned models |
| 🔐 **Smart token management** | Automatic refresh before expiration |

---

## 🚀 Quick Start

**Choose your deployment method:**
- 🐍 **Native Python** - Full control, easy debugging
- 🐳 **Docker** - Isolated environment, easy deployment → [jump to Docker](#-docker-deployment)

### Prerequisites

- Python 3.10+
- One of the following:
  - [Kiro IDE](https://kiro.dev/) with logged in account, OR
  - [Kiro CLI](https://kiro.dev/cli/) with AWS SSO (AWS IAM Identity Center, OIDC) - free Builder ID or corporate account

### Installation

```bash
# Clone the repository (requires Git)
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway

# Or download ZIP: Code → Download ZIP → extract → open kiro-gateway folder

# Install dependencies
pip install -r requirements.txt

# Configure (see Configuration section)
cp .env.example .env
# Copy and edit .env with your credentials

# Start the server
python main.py

# Or with custom port (if 8000 is busy)
python main.py --port 9000
```

The server will be available at `http://localhost:8000`

---

## ⚙️ Configuration

> 💡 **Single-account only:** This fork enforces single-account personal use. See [Compliance](#-compliance) and [COMPLIANCE.md](COMPLIANCE.md).

### Option 1: JSON Credentials File (Kiro IDE / Enterprise)

Specify the path to the credentials file:

Works with:
- **Kiro IDE** (standard) - for personal accounts
- **Enterprise** - for corporate accounts with SSO

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"

# Password to protect YOUR proxy server (make up any secure string)
# You'll use this as api_key when connecting to your gateway
PROXY_API_KEY="my-super-secret-password-123"
```

<details>
<summary>📄 JSON file format</summary>

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "profileArn": "arn:aws:codewhisperer:us-east-1:...",
  "region": "us-east-1",
  "clientIdHash": "abc123..."  // Optional: for corporate SSO setups
}
```

> **Note:** If you have two JSON files in `~/.aws/sso/cache/` (e.g., `kiro-auth-token.json` and a file with a hash name), use `kiro-auth-token.json` in `KIRO_CREDS_FILE`. The gateway will automatically load the other file.

</details>

### Option 2: Environment Variables (.env file)

Create a `.env` file in the project root:

```env
# Required
REFRESH_TOKEN="your_kiro_refresh_token"

# Password to protect YOUR proxy server (make up any secure string)
PROXY_API_KEY="my-super-secret-password-123"

# Optional
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
```

### Option 3: AWS SSO Credentials (kiro-cli / Enterprise)

If you use `kiro-cli` or Kiro IDE with AWS SSO (AWS IAM Identity Center), the gateway will automatically detect and use the appropriate authentication.

Works with both free Builder ID accounts and corporate accounts.

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/your-sso-cache-file.json"

# Password to protect YOUR proxy server
PROXY_API_KEY="my-super-secret-password-123"

# Note: For AWS SSO, PROFILE_ARN is optional in many setups.
# Builder ID usually works without it, but some corporate/enterprise setups require it.
# If you get a "profileArn required" error, set PROFILE_ARN explicitly.
```

<details>
<summary>📄 AWS SSO JSON file format</summary>

AWS SSO credentials files (from `~/.aws/sso/cache/`) contain:

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "region": "us-east-1",
  "clientId": "...",
  "clientSecret": "..."
}
```

**Note:** For AWS SSO users, `profileArn` is optional in many setups. Builder ID often works without it. Some corporate/enterprise setups require it; if you get `profileArn required`, set `PROFILE_ARN`.

</details>

<details>
<summary>🔍 How it works</summary>

The gateway automatically detects the authentication type based on the credentials file:

- **Kiro Desktop Auth** (default): Used when `clientId` and `clientSecret` are NOT present
  - Endpoint: `https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
  
- **AWS SSO (OIDC)**: Used when `clientId` and `clientSecret` ARE present
  - Endpoint: `https://oidc.{region}.amazonaws.com/token`

No additional configuration is needed — just point to your credentials file!

</details>

### Option 4: kiro-cli SQLite Database

If you use `kiro-cli` and prefer to use its SQLite database directly:

```env
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"

# Password to protect YOUR proxy server
PROXY_API_KEY="my-super-secret-password-123"

# Note: For AWS SSO, PROFILE_ARN is optional in many setups.
# Builder ID usually works without it, but some corporate/enterprise setups require it.
# If you get a "profileArn required" error, set PROFILE_ARN explicitly.
```

<details>
<summary>📄 Database locations</summary>

| CLI Tool | Database Path |
|----------|---------------|
| kiro-cli | `~/.local/share/kiro-cli/data.sqlite3` |
| amazon-q-developer-cli | `~/.local/share/amazon-q/data.sqlite3` |

The gateway reads credentials from the `auth_kv` table which stores:
- `kirocli:odic:token` or `codewhisperer:odic:token` — access token, refresh token, expiration
- `kirocli:odic:device-registration` or `codewhisperer:odic:device-registration` — client ID and secret

Both key formats are supported for compatibility with different kiro-cli versions.

</details>

### Getting Credentials

**For Kiro IDE users:**
- Log in to Kiro IDE and use Option 1 above (JSON credentials file)
- The credentials file is created automatically after login

**For Kiro CLI users:**
- Log in with `kiro-cli login` and use Option 3 or Option 4 above
- No manual token extraction needed!

<details>
<summary>🔧 Advanced: Manual token extraction</summary>

If you need to manually extract the refresh token (e.g., for debugging), you can intercept Kiro IDE traffic:
- Look for requests to: `prod.us-east-1.auth.desktop.kiro.dev/refreshToken`

</details>

---

## 🔑 Credential Configuration (credentials.json)

> ⚠️ **Single-account only.** `ACCOUNT_SYSTEM=true` (multi-account mode) is **disabled** in this fork to comply with AWS/Kiro terms of service. Only one credential entry is permitted. See [COMPLIANCE.md](COMPLIANCE.md).

The gateway supports an optional `credentials.json` file as a structured alternative to `.env` for credential configuration. **Only one entry is allowed.**

### Supported Entry Types

```json
[
  {
    "type": "json",
    "path": "~/.aws/sso/cache/kiro-auth-token.json",
    "comment": "Kiro IDE credentials (recommended)"
  }
]
```

Other valid `type` values: `"sqlite"` (kiro-cli DB), `"refresh_token"` (direct token).

For optional per-account region overrides (`profile_arn`, `region`, `api_region`), see [`credentials.json.example`](credentials.json.example).

### Rate Limits

Rate-limit errors (`429`, `402`, `403`) from Kiro are **returned directly to the caller** — they are not retried on another account, as that would circumvent quota enforcement.

---

## 🐳 Docker Deployment

> **Docker-based deployment.** Prefer native Python? See [Quick Start](#-quick-start) above.

### Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway
cp .env.example .env
# Edit .env with your credentials

# 2. Run with docker-compose
docker-compose up -d

# 3. View logs
docker-compose logs -f

# 4. Stop
docker-compose down
```

### Manual Docker Build

```bash
# Build image
docker build -t kiro-gateway .

# Run container
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -v $(pwd)/.env:/app/.env \
  kiro-gateway
```

### Configuration for Docker

You have two options for Docker credentials:

**Option 1: Mount credentials directory (recommended)**
```yaml
# In docker-compose.yml:
volumes:
  - ~/.aws/sso/cache:/root/.aws/sso/cache:ro
```

**Option 2: Environment variables**
```yaml
# In docker-compose.yml:
environment:
  - REFRESH_TOKEN=${REFRESH_TOKEN}
  - PROXY_API_KEY=${PROXY_API_KEY}
```

---

## 🔌 Client Setup

### Claude Code

```bash
claude config set -g apiUrl http://localhost:8000
claude config set -g apiKey your-proxy-api-key
```

### Cursor IDE

Settings → Models → Add model → Set base URL to `http://localhost:8000/v1`

### Cline / Roo Code

Provider: OpenAI Compatible  
Base URL: `http://localhost:8000/v1`  
API Key: your PROXY_API_KEY value

### Continue (VSCode extension)

```json
{
  "models": [
    {
      "title": "Claude Sonnet 4.5",
      "provider": "openai",
      "model": "claude-sonnet-4-5",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "your-proxy-api-key"
    }
  ]
}
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-proxy-api-key"
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

### Python (Anthropic SDK)

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="your-proxy-api-key"
)

message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}]
)
print(message.content[0].text)
```

---

## 📖 API Reference

### OpenAI-Compatible Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completions |
| `/v1/models` | GET | List available models |
| `/v1/models/{model}` | GET | Get model details |

### Anthropic-Compatible Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/messages` | POST | Messages API |
| `/v1/models` | GET | List available models |

### Health Check

```bash
curl http://localhost:8000/health
```

### Authentication

All requests require the `PROXY_API_KEY` as a Bearer token:

```bash
curl -H "Authorization: Bearer your-proxy-api-key" http://localhost:8000/v1/models
```

---

## 🧠 Extended Thinking

Extended thinking (reasoning) is supported for models that have this capability. Enable it by setting the `thinking` parameter:

```python
response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": "Solve this step by step: ..."}],
    extra_body={"thinking": {"type": "enabled", "budget_tokens": 10000}}
)
```

---

## 🔍 Web Search

Web search is supported when the model has this capability:

```python
response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": "What's the latest news about AI?"}],
    extra_body={"tools": [{"type": "web_search"}]}
)
```

---

## 📊 Supported Models

The gateway exposes all models available in your Kiro account. Use `/v1/models` to get the current list:

```bash
curl -H "Authorization: Bearer your-proxy-api-key" http://localhost:8000/v1/models
```

Model names are normalized automatically — use any format:
- `claude-sonnet-4-5`
- `claude-sonnet-4.5`  
- `claude-sonnet-4-5-20250929`
- `anthropic.claude-sonnet-4-5-v1`

All resolve to the same model.

---

## 🛡️ Compliance

This fork enforces **single-account personal use** to operate within the spirit of the [AWS Acceptable Use Policy](https://aws.amazon.com/aup/) and Kiro's terms of service.

| Rule | Status |
|------|--------|
| `ACCOUNT_SYSTEM=true` blocked | ✅ Enforced at startup |
| `credentials.json` >1 entry blocked | ✅ Enforced at startup |
| 429/402/403 surfaced to caller | ✅ No cross-account retry |
| Single-subscription requirement | ✅ Documented |

See [COMPLIANCE.md](COMPLIANCE.md) for the full policy.

---

## 🔧 Advanced Configuration

### Environment Variables Reference

<details>
<summary>📋 Full .env reference</summary>

See [`.env.example`](.env.example) for all available options with descriptions.

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PROXY_API_KEY` | (required) | Password for your gateway |
| `KIRO_CREDS_FILE` | - | Path to Kiro JSON credentials |
| `REFRESH_TOKEN` | - | Direct refresh token |
| `KIRO_CLI_DB_FILE` | - | Path to kiro-cli SQLite DB |
| `SERVER_HOST` | `0.0.0.0` | Server bind address |
| `SERVER_PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `VPN_PROXY_URL` | - | HTTP/SOCKS5 proxy URL |
| `STREAMING_READ_TIMEOUT` | `300` | Streaming timeout (seconds) |

</details>

### VPN / Proxy

For restricted networks, set `VPN_PROXY_URL` in your `.env`:

```env
VPN_PROXY_URL="socks5://user:pass@proxy.example.com:1080"
# or
VPN_PROXY_URL="http://proxy.example.com:8080"
```

---

## 💖 Support the Project

If this project helps you, consider supporting the original author:

- ⭐ **Star the repo** — helps others discover it
- 💖 **Sponsor @Jwadow** — [GitHub Sponsors](https://github.com/sponsors/jwadow)

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a PR.

---

## 📄 License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).

---

## ⚠️ Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Amazon Web Services (AWS), Anthropic, or Kiro IDE. Use at your own risk and in compliance with the terms of service of the underlying APIs.
