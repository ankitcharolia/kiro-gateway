# Security policy

Kiro Gateway is a compliance-first bridge to the official `kiro-cli` binary.
The gateway does not call private Kiro HTTP endpoints, pool accounts, or own
Kiro credentials. Authentication remains inside `kiro-cli`.

## Scope

This policy covers the gateway source code, its HTTP API, ACP translation, and
its configuration and deployment examples. Vulnerabilities in `kiro-cli`, Kiro,
third-party AI harnesses, or MCP servers should be reported to their respective
maintainers.

## Supported versions

| Version | Security fixes |
|---|---|
| Latest release and `main` | Yes |
| Older releases | Best effort; upgrade before reporting a regression |

## Reporting a vulnerability

Please do **not** open a public issue for a security vulnerability. Use
[GitHub's private vulnerability reporting form](https://github.com/ankitcharolia/kiro-gateway/security/advisories/new)
when it is available. If the form is unavailable, contact the maintainer
through the [GitHub profile](https://github.com/ankitcharolia) and request a
private channel.

Include the affected version or commit, reproduction steps, impact, and any
mitigation you know. Never include API keys, session tokens, Kiro credentials,
or other secrets in a report.

## Deployment note

`ACP_TRUST_TOOLS=true` allows `kiro-cli` to run its built-in tools after the
gateway answers permission requests. For shared or exposed deployments, set it
to `false` and scope the workspace deliberately. See the
[configuration and security notes](README.md#tool-execution--permissions) in
the README.
