"""Payload validation and trimming guards."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .tokenizer import count_message_tokens


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class PayloadTrimStats:
    """Statistics about a trim operation performed by :func:`trim_messages`."""
    original_message_count: int = 0
    trimmed_message_count: int = 0
    original_token_estimate: int = 0
    trimmed_token_estimate: int = 0
    messages_removed: int = 0

    @property
    def was_trimmed(self) -> bool:
        return self.messages_removed > 0


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def trim_messages(
    messages: List[Dict[str, Any]],
    max_input_tokens: int,
    preserve_system: bool = True,
) -> Tuple[List[Dict[str, Any]], PayloadTrimStats]:
    """Trim *messages* so that the estimated token count is below *max_input_tokens*.

    Returns the (possibly shortened) message list and a :class:`PayloadTrimStats`.
    """
    stats = PayloadTrimStats(
        original_message_count=len(messages),
        original_token_estimate=count_message_tokens(messages),
    )

    if stats.original_token_estimate <= max_input_tokens:
        stats.trimmed_message_count = len(messages)
        stats.trimmed_token_estimate = stats.original_token_estimate
        return messages, stats

    # Separate system message if present
    result: List[Dict[str, Any]] = []
    system_msg: Optional[Dict[str, Any]] = None
    rest = list(messages)

    if preserve_system and rest and rest[0].get("role") == "system":
        system_msg = rest.pop(0)

    # Drop oldest non-system messages until we fit
    while rest and count_message_tokens(
        ([system_msg] if system_msg else []) + rest
    ) > max_input_tokens:
        rest.pop(0)
        stats.messages_removed += 1

    result = ([system_msg] if system_msg else []) + rest
    stats.trimmed_message_count = len(result)
    stats.trimmed_token_estimate = count_message_tokens(result)
    return result, stats


def validate_max_tokens(
    requested: Optional[int],
    hard_limit: int = 8192,
) -> int:
    """Clamp *requested* max_tokens to *hard_limit*."""
    if requested is None:
        return hard_limit
    return min(requested, hard_limit)
