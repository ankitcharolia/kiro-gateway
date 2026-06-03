# Compliance Policy

This fork of [kiro-gateway](https://github.com/jwadow/kiro-gateway) has been rewritten to be **fully ACP-compliant**.

## Architecture

```
Editor / Tool                    kiro-gateway                kiro-cli (official)       Kiro Backend
─────────────────────────────────────────────────────────────────────────────────────────────────
Cursor / Cline        ──OpenAI─►  /v1/chat/completions
Kilo Code / Hermes    ──OpenAI─►  /v1/chat/completions  ──ACP JSON-RPC over stdio─► kiro-cli ─► Kiro API
OpenCode / Zed        ──Anthropic► /v1/messages
ACP-native clients    ──ACP────► /acp/*
```

**All AI completions route through `kiro-cli`** via the Agent Client Protocol (ACP), the official Kiro-approved integration path.

## What Changed from Upstream

| Feature | `jwadow/kiro-gateway` (upstream) | `ankitcharolia/kiro-gateway` (this fork) |
|---|---|---|
| Auth / credential handling | Direct token/credential injection | ❌ Removed — kiro-cli manages auth |
| Kiro internal API calls | Direct HTTP to Kiro backend | ❌ Removed — ACP over kiro-cli only |
| Multi-account failover | ✅ `ACCOUNT_SYSTEM=true` | ❌ Disabled — single account enforced |
| ACP protocol support | ❌ Not present | ✅ Full ACP client (session/prompt, streaming) |
| Kiro ToS compliance | ❌ Prohibited (third-party harness) | ✅ Compliant (approved ACP path) |
| Tools allowed | OpenAI/Anthropic API shim | OpenAI shim + Anthropic shim + Native ACP |

## Why This Is Compliant

Kiro's FAQ explicitly permits:
- ✅ **Kiro CLI** — this gateway calls `kiro-cli acp` as a subprocess
- ✅ **ACP-compatible IDEs** — this gateway is an ACP relay
- ✅ **CI/CD automation** — calling the gateway from pipelines routes through kiro-cli

The gateway is now a **standards-based ACP client** that wraps the official CLI, not a credential thief or internal API interceptor.

## Setup Requirements

1. Install kiro-cli: https://kiro.dev/docs/cli/
2. Log in: `kiro-cli auth login`
3. Start gateway: `python main.py`

No `.env`, no tokens, no credential files needed.

## References

- [ACP Specification](https://agentclientprotocol.com)
- [Kiro CLI ACP docs](https://kiro.dev/docs/cli/acp/)
- [AWS Acceptable Use Policy](https://aws.amazon.com/aup/)
- [GNU AGPL v3 License](./LICENSE)
