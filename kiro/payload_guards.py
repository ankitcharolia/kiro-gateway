"""Pre-flight payload validation and sanitisation."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .model_resolver import get_capabilities, resolve_model

logger = logging.getLogger(__name__)

# Hard limits
_MAX_STOP_SEQUENCES = 4
_MAX_TOOLS = 128
_ABSOLUTE_MAX_TOKENS = 64_000


def guard_openai_request(req: Any) -> None:
    """
    Validate and sanitise an OpenAI ChatCompletionRequest in-place.
    Raises HTTPException(422) for unrecoverable issues.
    """
    model_id = resolve_model(getattr(req, "model", "") or "")
    cap = get_capabilities(model_id)

    # --- thinking + tools mutual exclusion ---
    thinking = getattr(req, "thinking", None)
    tools = getattr(req, "tools", None)
    if thinking and tools:
        logger.warning(
            "Request has both thinking and tools enabled; disabling tools per Kiro constraint."
        )
        req.tools = None

    # --- thinking requires a supporting model ---
    if thinking and not cap.supports_thinking:
        logger.warning(
            "Model %s does not support thinking; stripping thinking config.", model_id
        )
        req.thinking = None

    # --- max_tokens clamp ---
    max_tokens = getattr(req, "max_tokens", None)
    if max_tokens is None or max_tokens <= 0:
        req.max_tokens = min(4_096, cap.max_output_tokens)
    elif max_tokens > cap.max_output_tokens:
        logger.warning(
            "max_tokens %d exceeds model cap %d; clamping.", max_tokens, cap.max_output_tokens
        )
        req.max_tokens = cap.max_output_tokens

    # --- stop sequences ---
    stop = getattr(req, "stop", None)
    if isinstance(stop, list) and len(stop) > _MAX_STOP_SEQUENCES:
        logger.warning("Truncating stop sequences from %d to %d.", len(stop), _MAX_STOP_SEQUENCES)
        req.stop = stop[:_MAX_STOP_SEQUENCES]

    # --- tool count ---
    if tools and len(tools) > _MAX_TOOLS:
        raise HTTPException(
            status_code=422,
            detail=f"Too many tools: {len(tools)} exceeds maximum of {_MAX_TOOLS}.",
        )


def guard_anthropic_request(req: Any) -> None:
    """
    Validate and sanitise an AnthropicRequest in-place.
    Raises HTTPException(422) for unrecoverable issues.
    """
    model_id = resolve_model(getattr(req, "model", "") or "")
    cap = get_capabilities(model_id)

    thinking = getattr(req, "thinking", None)
    tools = getattr(req, "tools", None)

    if thinking and tools:
        logger.warning(
            "Anthropic request has both thinking and tools; disabling tools per Kiro constraint."
        )
        req.tools = None

    if thinking and not cap.supports_thinking:
        logger.warning(
            "Model %s does not support thinking; stripping thinking config.", model_id
        )
        req.thinking = None

    max_tokens = getattr(req, "max_tokens", None)
    if not max_tokens or max_tokens <= 0:
        req.max_tokens = min(4_096, cap.max_output_tokens)
    elif max_tokens > cap.max_output_tokens:
        logger.warning(
            "max_tokens %d exceeds model cap %d; clamping.", max_tokens, cap.max_output_tokens
        )
        req.max_tokens = cap.max_output_tokens

    stop_seqs = getattr(req, "stop_sequences", None)
    if isinstance(stop_seqs, list) and len(stop_seqs) > _MAX_STOP_SEQUENCES:
        logger.warning(
            "Truncating stop_sequences from %d to %d.", len(stop_seqs), _MAX_STOP_SEQUENCES
        )
        req.stop_sequences = stop_seqs[:_MAX_STOP_SEQUENCES]

    if tools and len(tools) > _MAX_TOOLS:
        raise HTTPException(
            status_code=422,
            detail=f"Too many tools: {len(tools)} exceeds maximum of {_MAX_TOOLS}.",
        )
