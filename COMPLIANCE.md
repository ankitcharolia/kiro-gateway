# Compliance Policy

This fork of [kiro-gateway](https://github.com/jwadow/kiro-gateway) has been rewritten to route **every** request through the official `kiro-cli` binary via the Agent Client Protocol (ACP), instead of calling Kiro's internal API or handling credentials directly. See the note below for licensing details.

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
| Kiro ToS compliance | ❌ Prohibited (third-party harness) | ✅ Official `kiro-cli` ACP path only (see note) |
| Tools allowed | OpenAI/Anthropic API shim | OpenAI shim + Anthropic shim + Native ACP |

## Design Intent: Staying Inside the Official Integration Path

This gateway is designed around the official, documented Kiro integration
surfaces rather than any reverse-engineered API:

- ✅ **Kiro CLI** — the gateway calls `kiro-cli acp` as a subprocess; it is the
  only component that talks to Kiro.
- ✅ **Agent Client Protocol (ACP)** — the gateway is a standards-based ACP
  client, the same protocol Kiro-compatible IDEs use.
- ✅ **No credential handling** — all authentication lives inside `kiro-cli`
  (`kiro-cli login`); the gateway never reads, stores, or forwards tokens.
- ✅ **No private API calls** — the gateway never calls Kiro's internal HTTP
  endpoints and never pools accounts.

The gateway is a **standards-based ACP client that wraps the official CLI**, not
a credential extractor or internal-API interceptor.

> **Note on licensing.** The points above describe the project's design goals
> and the maintainer's reading of Kiro's published integration paths; they are
> not legal advice. A few things worth knowing:
>
> - The Kiro CLI is licensed as "AWS Content" under the
>   [AWS Customer Agreement](https://aws.amazon.com/agreement/) and the
>   [AWS IP License](https://aws.amazon.com/legal/aws-ip-license-terms/)
>   (see the [official license](https://kiro.dev/license/)), so your use is
>   governed by those terms.
> - Kiro's docs don't publish a specific authorization for wrapping a
>   subscription behind an OpenAI/Anthropic-style API gateway, so it's worth
>   confirming this fits your own agreement.
> - If you publish a Docker image that bundles the Kiro CLI, review the AWS
>   redistribution terms first. For private or local use this isn't a concern.

## Setup Requirements

1. Install kiro-cli: https://kiro.dev/docs/cli/
2. Log in: `kiro-cli auth login`
3. Start gateway: `uv run main.py`

No `.env`, no tokens, no credential files needed.

## References

- [ACP Specification](https://agentclientprotocol.com)
- [Kiro CLI ACP docs](https://kiro.dev/docs/cli/acp/)
- [AWS Acceptable Use Policy](https://aws.amazon.com/aup/)
- [GNU AGPL v3 License](./LICENSE)

## Support

If this project saves you time, consider supporting its continued development:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/achar)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)
