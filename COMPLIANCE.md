# Compliance Policy

This fork of [kiro-gateway](https://github.com/jwadow/kiro-gateway) enforces **single-account personal use** to operate within the spirit of the [AWS Acceptable Use Policy](https://aws.amazon.com/aup/) and Kiro's terms of service.

## What This Fork Does Differently

| Feature | Upstream (`jwadow/kiro-gateway`) | This Fork (`ankitcharolia/kiro-gateway`) |
|---|---|---|
| Multi-account failover | ✅ Supported (`ACCOUNT_SYSTEM=true`) | 🚫 **Disabled** |
| Rate-limit bypass across accounts | ✅ Automatic on 429/402 | 🚫 **Errors surfaced to caller** |
| Credential pooling | ✅ `credentials.json` array | 🚫 **Single entry enforced** |
| Personal single-account use | ✅ Supported | ✅ **Supported** |

## Rules Enforced at Startup

1. **`ACCOUNT_SYSTEM=true` is blocked.** Setting this in `.env` causes an immediate startup error.
2. **`credentials.json` must have exactly one entry.** If multiple accounts are detected, the gateway refuses to start.
3. **Rate-limit errors (429, 402, 403) are not retried on another account.** They are returned directly to the caller.
4. **Single credential rebuilt from `.env` on every restart.** Prevents accumulation of multiple entries over time.

## Intended Use

This gateway is a **personal API compatibility shim** — it lets you use your own valid Kiro subscription (free or paid) with OpenAI/Anthropic-compatible tools like Cursor, Cline, or Claude Code, using the same credentials your Kiro IDE uses.

It does **not**:
- Share credentials across users
- Pool multiple subscriptions
- Bypass or circumvent quota/rate-limit enforcement
- Create or use fake/unauthorized accounts

## References

- [AWS Acceptable Use Policy](https://aws.amazon.com/aup/)
- [Kiro Terms of Service](https://kiro.dev/terms)
- [GNU AGPL v3 License](./LICENSE)
