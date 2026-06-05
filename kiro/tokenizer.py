"""Token counting utilities using tiktoken with model-aware fallback."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

logger = logging.getLogger(__name__)

# Attempt to import tiktoken; fall back to character-based estimation if absent.
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed; falling back to character-based token estimation.")


# ---------------------------------------------------------------------------
# Encoding resolution
# ---------------------------------------------------------------------------

_MODEL_ENCODING_MAP = {
    "gpt-4o": "o200k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5": "cl100k_base",
    "claude": "cl100k_base",  # approximation
}


@lru_cache(maxsize=8)
def _get_encoding(encoding_name: str):
    if not _TIKTOKEN_AVAILABLE:
        return None
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def _resolve_encoding(model: Optional[str]):
    if not _TIKTOKEN_AVAILABLE:
        return None
    if not model:
        return _get_encoding("cl100k_base")
    model_lower = model.lower()
    for prefix, enc_name in _MODEL_ENCODING_MAP.items():
        if prefix in model_lower:
            return _get_encoding(enc_name)
    return _get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def count_tokens(text: str, model: Optional[str] = None) -> int:
    """Count tokens in *text* for the given model."""
    if not text:
        return 0
    enc = _resolve_encoding(model)
    if enc is None:
        # Character-based fallback: ~4 chars/token
        return max(1, len(text) // 4)
    try:
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def count_messages_tokens(messages: List[dict], model: Optional[str] = None) -> int:
    """Estimate total token count for a list of message dicts."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                part.get("text", str(part)) if isinstance(part, dict) else str(part)
                for part in content
            )
        total += count_tokens(str(content), model)
        # Per-message overhead (role token + framing)
        total += 4
    return total


def tokens_remaining(max_tokens: int, used_tokens: int) -> int:
    """How many tokens remain in the context window."""
    return max(0, max_tokens - used_tokens)
