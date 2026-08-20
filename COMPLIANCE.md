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
| Auth / credential handling | Direct token/credential injection | ❌ Removed — kiro-cli manages auth (v3 engine: one scoped, documented exception below) |
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
- ✅ **No credential handling on the default engine** — all authentication lives
  inside `kiro-cli` (`kiro-cli login`); on `KIRO_ACP_ENGINE=v2` (the default)
  the gateway never reads, stores or forwards a token. See the scoped v3
  exception below.
- ✅ **No private API calls** — the gateway never calls Kiro's internal HTTP
  endpoints and never pools accounts.

The gateway is a **standards-based ACP client that wraps the official CLI**, not
a credential extractor or internal-API interceptor.

## Scoped exception: the v3 agent engine's auth callback

`KIRO_ACP_ENGINE=v3` (opt-in; **not** the default) requires the gateway to
handle one credential, so it is documented here explicitly rather than hidden.

**Why it is unavoidable.** `kiro-cli acp --agent-engine v3` does not run the
agent itself: it spawns the Kiro Agent Server (KAS) and launches it with
`--auth=acp-callback`, which is hardcoded. Verified against a live kiro-cli
2.18.0 process:

```
node --experimental-wasm-modules …/@kiro/agent/dist/server/acp-server.js \
     --transport=stdio --auth=acp-callback
```

In that mode KAS keeps no credential of its own and asks its ACP *client* for an
access token via `_kiro/auth/getAccessToken`. `kiro-cli acp` exposes no flag to
select another mode, and KAS's alternatives (`--auth=user`, `--auth=machine`,
`KIRO_API_KEY`) are unreachable through the CLI. A client that declines gets
`initialize` and `session/new`, but every `session/prompt` fails with
`-32000 Auth refresh callback failed`.

**What the gateway does.** It relays a short-lived access token obtained **from
kiro-cli itself** (`kiro-cli chat _ get-kas-token`, which resolves and refreshes
the token inside the official binary) to kiro-cli's own agent server:

| Property | Behaviour |
|---|---|
| OIDC refresh token | **Never read.** It stays in kiro-cli's own store. |
| OIDC refresh flow | **Never performed by the gateway.** Delegated to the official binary. |
| Token storage | **None.** Not cached, not written to disk (KAS caches internally — a live probe showed one callback per subprocess). |
| Token logging | **Never.** Only expiry and presence flags are logged; failures raise fixed, token-free messages. |
| Destination | kiro-cli's own agent server, over the existing stdio pipe. The gateway makes no HTTP call with it. |
| Forwarded fields | Only the covenant keys (`accessToken`, `expiresAt`, `profileArn`, `authMethod`, `provider`) — never a raw passthrough. |

Implementation: [`kiro/kiro_auth.py`](kiro/kiro_auth.py). Precedent: this is the
same mechanism used by [`kirodotdev/KiroCrew`](https://github.com/kirodotdev/KiroCrew)
(a first-party Kiro project) in `src/kiro_crew/acp/kas_auth.py`.

**Operator control.** Set `ACP_AUTH_BRIDGE=false` to refuse the relay: the
callback is then declined and v3 fails closed with a `401 authentication_error`
instead of silently handling a credential. `KIRO_ACP_ENGINE=v2` (the default)
avoids the question entirely.

**Rejected alternatives.**
- *Reading kiro-cli's credential store* (`data.sqlite3` → `auth_kv`): depends on
  an undocumented on-disk schema and touches the row holding the refresh token,
  for no benefit over the official command.
- *Refreshing the token in the gateway*: would duplicate kiro-cli's auth logic
  and risk desynchronising its store on refresh-token rotation, logging the user
  out.
- *Spawning KAS directly* (as KiroCrew does): would stop invoking the official
  binary — the project's core claim — and couple the gateway to kiro-cli's
  internal `kas/<version>-<hash>/` layout.

**Unchanged on v3.** The gateway still advertises no client-side filesystem or
terminal capabilities and declines every other agent callback v3 offers
(`_kiro/fs/read|write|delete`, hooks, checkpoints, `_kiro/openExternalUrl`), so
the least-privilege posture is identical to v2.

**Inherited from kiro-cli, not chosen by the gateway.** When kiro-cli launches
KAS it sets its own environment, including `KIRO_CONTENT_COLLECTION_ENABLED=true`
and `KIRO_TELEMETRY_ENABLED=true`. That is kiro-cli's posture for any ACP client
(the Kiro IDE included) and is the same whether you use the gateway or
`kiro-cli chat` interactively; the gateway neither sets nor overrides it. v3 also
auto-loads the MCP servers from kiro-cli's own configuration, independently of
`KIRO_MCP_SERVERS` and `MCP_DISCOVERY`.

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
