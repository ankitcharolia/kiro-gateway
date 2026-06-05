"""OpenAI-compatible Pydantic models for /v1/models and related endpoints."""
from __future__ import annotations

import time
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ModelCard(BaseModel):
    """A single model entry in the /v1/models list."""
    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "kiro"


class ModelList(BaseModel):
    """Response body for GET /v1/models."""
    object: Literal["list"] = "list"
    data: List[ModelCard] = Field(default_factory=list)


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[dict]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    tools: Optional[List[dict]] = None
    tool_choice: Optional[object] = None
    system: Optional[str] = None


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: dict
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)
