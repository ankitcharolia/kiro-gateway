"""Resolve the ACP session working directory from a harness request.

The OpenAI and Anthropic wire protocols carry **no** dedicated field for the
client's current working directory, so historically the gateway anchored every
``session/new`` in its own process cwd — which is wrong when a coding harness
(OpenCode, Claude Code, …) runs in a project directory different from where the
gateway was launched, and doubly wrong when several harness sessions run in
different directories at once.

Coding harnesses do, however, communicate their cwd in-band: they embed it in
an ``<env>`` block in the system prompt as a ``Working directory: <abs path>``
line. This was verified against a live capture — OpenCode 1.17.18 sends::

    <env>
      Working directory: /tmp/kiro_cwd_probe_f0crhY
      Workspace root folder: /
      ...
    </env>

and Claude Code uses the identical ``Working directory:`` convention. This
module recovers that path so the gateway anchors kiro-cli in the harness's cwd
**by default**, with no configuration.

Resolution order (first absolute, existing directory wins):

1. The ``X-Kiro-Workspace`` request header — an explicit per-request override
   for harnesses that can set a custom header (not a config flag/env var).
2. Any explicit ``filesystem_roots`` on the request body (native ACP clients).
3. A ``Working directory:`` line parsed from the request's messages.

When none is usable, the caller falls back to the gateway process cwd (via
:meth:`ACPClient._derive_cwd`), preserving the previous behaviour.

Security note
-------------
A resolved directory is only an **anchor** for relative paths and the agent's
default project context — it is **not** a sandbox. Verified against a live
kiro-cli 2.12.2 probe: with ``ACP_TRUST_TOOLS=true`` the agent can still read,
write and execute at absolute paths outside the cwd on request. The real
execution-permission control therefore remains ``ACP_TRUST_TOOLS``; this module
only decides where the session is *anchored*. Every candidate is validated to
be an absolute, existing directory before use, so a malformed or non-existent
value in untrusted prompt text is ignored rather than honoured.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Optional

from loguru import logger

from kiro.acp_models import FilesystemRoot, PromptMessage

# Header a harness (or a proxy in front of it) may set to pin the session cwd
# explicitly. Lower-cased because Starlette header lookups are case-insensitive.
WORKSPACE_HEADER = "x-kiro-workspace"

# Harnesses phrase the working-directory line differently, so several patterns
# are tried in order. Verified against live captures:
#   * "Working directory: <path>"          — OpenCode, Claude Code, Kilo Code
#   * "current working directory is '<path>'" — Oh My Pi (quoted, no colon)
# All are case-insensitive; the colon form is multiline (label at line start).
# _validate_dir still guards the result, so an over-broad match is harmless.
_WORKDIR_PATTERNS = (
    # Quoted path after ':' or 'is' (handles paths containing spaces).
    re.compile(r"working directory(?::|\s+is)\s*['\"](?P<path>[^'\"\n]+)['\"]", re.IGNORECASE),
    # Colon form, path runs to end of line (OpenCode / Claude Code / Kilo).
    re.compile(r"working directory:[ \t]*(?P<path>\S[^\n]*?)[ \t]*$", re.IGNORECASE | re.MULTILINE),
    # "is <absolute path>" without quotes (path token up to whitespace/quote).
    re.compile(r"working directory\s+is\s+(?P<path>/[^\s'\"\n]+)", re.IGNORECASE),
)


def _iter_message_text(messages: Iterable[PromptMessage]) -> Iterable[str]:
    """Yield every text fragment carried by a list of prompt messages.

    Args:
        messages: The request's prompt messages. ``content`` may be a plain
            string or a list of content blocks (dicts with a ``text`` field).

    Yields:
        Each text fragment found, in message/block order.
    """
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            yield content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        yield text


def _validate_dir(path: Optional[str]) -> Optional[str]:
    """Return ``path`` iff it is an absolute, existing directory, else ``None``.

    Args:
        path: A candidate directory string (may carry a ``file://`` scheme or
            surrounding quotes), or ``None``.

    Returns:
        The cleaned absolute directory path when valid, otherwise ``None``.
    """
    if not path:
        return None
    candidate = path.strip().strip('"').strip("'")
    if candidate.startswith("file://"):
        candidate = candidate[len("file://"):]
    candidate = candidate.strip()
    if not candidate or not os.path.isabs(candidate):
        return None
    if os.path.isdir(candidate):
        return candidate
    return None


def parse_working_dir(messages: Iterable[PromptMessage]) -> Optional[str]:
    """Extract a validated working directory from a request's messages.

    Scans every message's text for a working-directory line (the ``<env>`` /
    environment block convention used by OpenCode, Claude Code, Kilo Code,
    Oh My Pi and Hermes) and returns the first absolute, existing directory
    found.

    Args:
        messages: The request's prompt messages.

    Returns:
        The resolved absolute directory path, or ``None`` if none is present.
    """
    for text in _iter_message_text(messages):
        for pattern in _WORKDIR_PATTERNS:
            for match in pattern.finditer(text):
                resolved = _validate_dir(match.group("path"))
                if resolved:
                    return resolved
    return None


def resolve_workspace_cwd(
    header_value: Optional[str],
    messages: Iterable[PromptMessage],
) -> Optional[str]:
    """Resolve the session cwd from the harness request (header, then prompt).

    Args:
        header_value: Raw value of the ``X-Kiro-Workspace`` header, or ``None``.
        messages: The request's prompt messages.

    Returns:
        A validated absolute directory path, or ``None`` when nothing usable is
        present (the caller then falls back to ``filesystem_roots`` / the
        gateway process cwd).
    """
    from_header = _validate_dir(header_value)
    if from_header:
        logger.debug(f"Session cwd resolved from {WORKSPACE_HEADER} header: {from_header}")
        return from_header
    from_prompt = parse_working_dir(messages)
    if from_prompt:
        logger.debug(f"Session cwd resolved from prompt <env> block: {from_prompt}")
        return from_prompt
    return None


def build_filesystem_roots(
    header_value: Optional[str],
    body_roots: Optional[list[dict]],
    messages: Iterable[PromptMessage],
) -> list[FilesystemRoot]:
    """Build the session's filesystem roots, defaulting to the harness cwd.

    Precedence (first wins):

    1. ``X-Kiro-Workspace`` header (explicit override).
    2. Explicit ``filesystem_roots`` on the request body (native ACP clients).
    3. A ``Working directory:`` line parsed from the messages (OpenCode /
       Claude Code default).

    When none is usable an empty list is returned, so ``ACPClient`` falls back
    to the gateway process cwd — preserving the previous behaviour.

    Args:
        header_value: Raw value of the ``X-Kiro-Workspace`` header, or ``None``.
        body_roots: The request body's ``filesystem_roots`` (raw dicts), or
            ``None``/empty when the client sent none.
        messages: The request's prompt messages.

    Returns:
        A list with at most one :class:`FilesystemRoot`, or an empty list.
    """
    header_ws = _validate_dir(header_value)
    if header_ws:
        logger.debug(f"Session cwd resolved from {WORKSPACE_HEADER} header: {header_ws}")
        return [FilesystemRoot(path=header_ws)]

    if body_roots:
        return [FilesystemRoot(**root) for root in body_roots]

    prompt_ws = parse_working_dir(messages)
    if prompt_ws:
        logger.debug(f"Session cwd resolved from prompt <env> block: {prompt_ws}")
        return [FilesystemRoot(path=prompt_ws)]

    return []
