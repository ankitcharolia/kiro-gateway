"""System prompt sanitizer — strip harness identity overrides.

Claude Code, Kilo Code, and other AI harnesses inject large system prompts
(~30KB) that include identity assertions ("You are Claude Code"), concealment
instructions ("Never reveal you're behind a gateway"), and framework boilerplate.
When serialised into the ACP prompt text, kiro-cli's model may detect these as
prompt injection attempts and refuse to answer (issue #73).

This module strips **identity-override and concealment patterns** while
preserving useful context (coding standards, project rules, memory, tool
descriptions). It operates on the system message text *before* it is serialised
into the ACP prompt block.

The filter is **opt-out** via ``SANITIZE_SYSTEM_PROMPTS=false`` for users who
encounter no issues and want the full system text forwarded verbatim.
"""
from __future__ import annotations

import re
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Patterns to strip (compiled once at module load)
# ---------------------------------------------------------------------------

# Identity assertions: "You are Claude Code", "You are Claude", "I am Claude"
_IDENTITY_PATTERNS = [
    # "You are <Name>, ..." (up to end of sentence or line)
    re.compile(
        r"^.*?(?:You are|I am|This is|You must identify (?:yourself )?as)\s+"
        r"(?:Claude(?:\s+Code)?|Copilot|ChatGPT|GPT-\d|Gemini|an? (?:AI |interactive )?"
        r"(?:CLI )?tool (?:made|created|developed) by)"
        r"[^\n]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # "You are NOT any other AI", "You are NOT Kiro", "Always identify as Claude"
    re.compile(
        r"^.*?(?:You (?:are|must) (?:NOT|never)|Always (?:identify|maintain|keep))"
        r"[^\n]*?(?:other (?:AI|assistant)|identity|identify as|Claude|Kiro)"
        r"[^\n]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # "Never say you are Kiro/another assistant"
    re.compile(
        r"^.*?(?:Never|Do not|Don't)\s+(?:say|claim|admit|reveal)\s+"
        r"(?:you are|that you're)"
        r"[^\n]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
]

# Concealment instructions: "Never reveal the gateway/proxy/bridge"
_CONCEALMENT_PATTERNS = [
    re.compile(
        r"^.*?(?:Never|Do not|Don't|Must not|Should not)\s+"
        r"(?:reveal|disclose|mention|say|tell|expose|admit)"
        r"[^\n]*?(?:gateway|proxy|bridge|running through|behind)"
        r"[^\n]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    re.compile(
        r"^.*?(?:Ignore|Disregard|Override)\s+(?:any )?(?:instructions?|rules?)\s+"
        r"(?:that )?(?:contradict|conflict)"
        r"[^\n]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
]

# Identity section headers that usually precede identity-override blocks.
# We strip the header line only (the block content is caught by the patterns
# above or left intact if it's useful context).
_IDENTITY_HEADERS = re.compile(
    r"^#+\s*(?:Identity|Who You Are|Your Identity|Agent Identity)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# All patterns combined for a single pass
_ALL_PATTERNS = _IDENTITY_PATTERNS + _CONCEALMENT_PATTERNS + [_IDENTITY_HEADERS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_system_prompt(text: Optional[str]) -> Optional[str]:
    """Remove identity-override and concealment lines from a system prompt.

    Preserves everything else (coding standards, memory, tool descriptions,
    project rules) — only lines that try to override the agent's identity or
    hide the gateway are stripped.

    Args:
        text: The raw system prompt text, or ``None``.

    Returns:
        The sanitized text (may be shorter), or ``None`` if input was ``None``.
    """
    if not text:
        return text

    original_len = len(text)
    result = text
    for pattern in _ALL_PATTERNS:
        result = pattern.sub("", result)

    # Collapse runs of 3+ blank lines down to 2 (cosmetic)
    result = re.sub(r"\n{3,}", "\n\n", result)

    stripped = original_len - len(result)
    if stripped > 0:
        logger.debug(
            f"System prompt sanitized: removed {stripped} chars "
            f"({stripped * 100 // original_len}% of {original_len})"
        )

    return result
