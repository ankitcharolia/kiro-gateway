"""Unified request body parsers for OpenAI and Anthropic API surfaces."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import Request, HTTPException

from .models_openai import ChatCompletionRequest
from .models_anthropic import AnthropicRequest


async def parse_openai_request(request: Request) -> ChatCompletionRequest:
    """Parse and validate an incoming OpenAI-compatible chat request."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}")
    try:
        return ChatCompletionRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Request validation error: {exc}")


async def parse_anthropic_request(request: Request) -> AnthropicRequest:
    """Parse and validate an incoming Anthropic-compatible messages request."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}")
    try:
        return AnthropicRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Request validation error: {exc}")


def extract_stream_flag(body: Dict[str, Any]) -> bool:
    """Safely extract the stream flag from a raw request body dict."""
    return bool(body.get("stream", False))


def extract_model(body: Dict[str, Any], default: str = "claude-sonnet-4-5") -> str:
    """Extract the model name from a raw request body dict."""
    return str(body.get("model") or default)
