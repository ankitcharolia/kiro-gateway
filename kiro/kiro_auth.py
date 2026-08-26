# -*- coding: utf-8 -*-
"""
Resolver for the v3 agent engine's ``_kiro/auth/getAccessToken`` callback
(issue #52).

Why this exists
---------------
``kiro-cli acp --agent-engine v3`` does not run the agent itself: it spawns the
Kiro Agent Server (KAS) and launches it with ``--auth=acp-callback``, which is
hardcoded. Verified against a live kiro-cli 2.18.0 process::

    node --experimental-wasm-modules …/@kiro/agent/dist/server/acp-server.js \\
         --transport=stdio --auth=acp-callback

In that mode KAS keeps **no** credential of its own and asks its ACP *client*
for an access token. A client that declines still gets ``initialize`` and
``session/new`` to succeed, but every ``session/prompt`` fails with
``-32000 Auth refresh callback failed`` — the v3 blocker in issue #52.

The gateway's job is a **passthrough**: kiro-cli owns the OIDC refresh token and
exposes a subcommand that resolves-and-refreshes the access token, printing it as
one JSON line::

    kiro-cli chat _ get-kas-token
    → {"kind": "getKasToken", "data": {"accessToken": …, "expiresAt": …,
                                       "profileArn": …, "provider": …}}

So no OIDC flow, no refresh logic and no token custody live here. This mirrors
`kirodotdev/KiroCrew <https://github.com/kirodotdev/KiroCrew>`_ (a first-party
Kiro project), whose ``acp/kas_auth.py`` answers the same callback the same way.

Compliance position (deliberate, documented — see COMPLIANCE.md)
---------------------------------------------------------------
On the default ``v2`` engine nothing here ever runs and the gateway remains
completely credential-free. On ``v3`` the gateway relays a short-lived access
token **from kiro-cli to kiro-cli's own agent server**:

* only the access token is handled — the OIDC **refresh token is never read**;
* the token is **never cached, persisted or logged** (KAS caches it internally:
  a live probe showed exactly one callback per subprocess);
* only the covenant keys are forwarded, so no future kiro-cli field leaks onto
  the wire unreviewed;
* it is sent nowhere else — the gateway makes no HTTP call with it.

Security notes
--------------
* Failure messages are **fixed strings**, never the subprocess output: a
  malformed line could itself be a live token with trailing junk, so it must not
  travel in an exception, a log record or a traceback.
* The command is spawned with an argv **list** and no shell, so there is no
  command-injection surface, and a timeout guarantees a hung kiro-cli cannot
  wedge the callback (and with it every prompt on the connection).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, Optional

from loguru import logger

#: The request the v3 agent server sends to its ACP client. Connection-level: it
#: carries no ``sessionId``, so it is answered directly rather than routed to a
#: session. Note the single-underscore ``_kiro/`` namespace, distinct from v2's
#: ``_kiro.dev/`` one.
AUTH_CALLBACK_METHOD = "_kiro/auth/getAccessToken"

#: JSON-RPC error code returned when the callback cannot be fulfilled. KAS
#: treats any rejection as an expired-token signal, so the exact code is not
#: load-bearing; -32000 is the ACP server-error range.
AUTH_CALLBACK_ERROR_CODE = -32000

#: Subcommand that resolves + refreshes the KAS access token and prints one JSON
#: line. This is a hidden kiro-cli IPC surface and may change without notice;
#: failures are reported with an actionable message rather than papered over.
_GET_KAS_TOKEN_ARGS = ("chat", "_", "get-kas-token")

#: Marker kiro-cli puts on a successful token line.
_TOKEN_KIND = "getKasToken"

#: Hard cap on the callback subprocess. A refresh is a network round-trip, so
#: allow room, but never let a hung process block the connection forever.
_CALLBACK_TIMEOUT_SECONDS = 20.0

#: The only keys forwarded to KAS, matching its ``GetAccessTokenResponse``.
#: ``accessToken``/``expiresAt`` are required by KAS (which rejects a token
#: expiring within 3 minutes); ``profileArn`` drives its AWS region (without it
#: KAS falls back to ``us-east-1``); ``provider`` drives its enterprise
#: governance path. Filtering — rather than forwarding ``data`` wholesale —
#: keeps any future kiro-cli field off the wire until it is reviewed.
_COVENANT_KEYS = ("accessToken", "expiresAt", "profileArn", "authMethod", "provider")


class KiroAuthError(RuntimeError):
    """A v3 auth callback could not be fulfilled.

    Its ``str`` is always a fixed, token-free description — safe to log and to
    send back as a JSON-RPC error message.
    """


class KiroAuthResolver:
    """Resolves v3 access tokens by shelling out to kiro-cli.

    Holds no state beyond configuration: every callback runs the official
    command afresh, so no credential is retained between calls.
    """

    def __init__(
        self,
        cli_path: str = "kiro-cli",
        timeout: float = _CALLBACK_TIMEOUT_SECONDS,
    ) -> None:
        """
        Args:
            cli_path: Path/name of the kiro-cli binary (``KIRO_CLI_PATH``).
            timeout: Seconds to allow the token subprocess before killing it.
        """
        self._cli_path = cli_path or "kiro-cli"
        self._timeout = timeout
        self._disclosed = False

    async def resolve(self) -> dict[str, Any]:
        """Resolve a fresh access token as the ACP callback result payload.

        Returns:
            The ``_kiro/auth/getAccessToken`` result dict: ``accessToken`` and
            ``expiresAt`` always, plus whichever of ``profileArn`` /
            ``authMethod`` / ``provider`` kiro-cli supplied.

        Raises:
            KiroAuthError: When kiro-cli cannot be launched, times out, or does
                not return a usable token. The message never contains token
                material.
        """
        argv = [self._cli_path, *_GET_KAS_TOKEN_ARGS]
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:
            # A spawn failure carries no token: the text is a path/errno.
            raise KiroAuthError(
                f"could not launch kiro-cli for the v3 auth callback: {exc}"
            ) from None

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(ProcessLookupError, asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            raise KiroAuthError("kiro-cli token callback timed out") from None
        except asyncio.CancelledError:
            # Teardown cancelled this callback mid-flight: kill the credential
            # subprocess synchronously so it cannot linger detached, and do not
            # await here (we are unwinding a cancellation).
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            raise

        payload = parse_token_output(stdout, stderr)
        self._disclose_once(payload)
        return payload

    def _disclose_once(self, payload: dict[str, Any]) -> None:
        """Log the compliance-relevant disclosure once per process.

        Args:
            payload: The resolved covenant payload. Only non-secret fields
                (expiry, presence flags) are logged — never the token.
        """
        if self._disclosed:
            return
        self._disclosed = True
        logger.info(
            "v3 auth bridge active: relaying kiro-cli's short-lived access token "
            "to kiro-cli's own agent server (token not cached, refresh token "
            "never read). "
            f"expires_at={payload.get('expiresAt', 'unknown')} "
            f"profile_arn={'set' if payload.get('profileArn') else 'unset'} "
            f"provider={payload.get('provider') or 'unset'}"
        )


def parse_token_output(stdout: bytes, stderr: bytes) -> dict[str, Any]:
    """Parse ``kiro-cli chat _ get-kas-token`` output into the ACP result.

    Split out from the spawn so it is unit-testable without a real process.

    Args:
        stdout: Raw stdout from the token command.
        stderr: Raw stderr, deliberately **not** surfaced (see below).

    Returns:
        The covenant-filtered result dict.

    Raises:
        KiroAuthError: On empty, unparseable or error output. The message is
            always a fixed string: stdout/stderr are untrusted and could contain
            token material, so they are dropped rather than echoed or logged.
    """
    text = stdout.decode("utf-8", "replace").strip()
    if not text:
        raise KiroAuthError(
            "kiro-cli returned no token output; run `kiro-cli login` on the "
            "gateway host"
        )

    # kiro-cli emits exactly one JSON line, but a stray leading log line must
    # not derail the parse.
    last_line = text.splitlines()[-1]
    try:
        obj = json.loads(last_line)
    except (ValueError, TypeError):
        # Never put the line in the message — it may be a live token.
        raise KiroAuthError("could not parse kiro-cli token output") from None

    if not isinstance(obj, dict):
        raise KiroAuthError("kiro-cli token output was not a JSON object")

    data = obj.get("data")
    if not isinstance(data, dict):
        raise KiroAuthError("kiro-cli token output had no data object")

    kind = obj.get("kind")
    if kind == "error":
        # kiro-cli's own message is untrusted text; raise a fixed, actionable
        # one instead and leave the specifics in kiro-cli's logs.
        raise KiroAuthError(
            "kiro-cli authentication failed; run `kiro-cli login` on the "
            "gateway host"
        )
    if kind != _TOKEN_KIND:
        raise KiroAuthError("unexpected kiro-cli token output kind")

    if not data.get("accessToken"):
        raise KiroAuthError("kiro-cli token output missing accessToken")
    if not data.get("expiresAt"):
        # KAS rejects a response whose expiresAt does not parse, so failing here
        # gives a clearer error than its TokenInvalidError.
        raise KiroAuthError("kiro-cli token output missing expiresAt")

    return {key: data[key] for key in _COVENANT_KEYS if key in data}


def build_resolver(
    cli_path: str, engine: str, enabled: bool
) -> Optional[KiroAuthResolver]:
    """Build the auth resolver for a configured engine, or ``None``.

    The resolver is only created for the ``v3`` engine: on ``v1``/``v2`` the
    agent never sends the callback, so the gateway stays credential-free and its
    behaviour is byte-identical to before this feature.

    Args:
        cli_path: Path/name of the kiro-cli binary.
        engine: The configured ``--agent-engine`` value.
        enabled: The ``ACP_AUTH_BRIDGE`` switch. When ``False`` the callback is
            declined even on v3, so an operator who declines the credential
            relay fails closed instead of relaying a token.

    Returns:
        A :class:`KiroAuthResolver`, or ``None`` when the bridge must not run.
    """
    if (engine or "").strip().lower() != "v3":
        return None
    if not enabled:
        logger.warning(
            "KIRO_ACP_ENGINE=v3 but ACP_AUTH_BRIDGE is disabled: the agent's "
            "auth callback will be declined and generation will fail. "
            "Set ACP_AUTH_BRIDGE=true or use KIRO_ACP_ENGINE=v2."
        )
        return None
    return KiroAuthResolver(cli_path=cli_path)
