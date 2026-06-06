"""OpenAI-compatible Pydantic models for /v1/models and related endpoints."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Chat message
# ---------------------------------------------------------------------------

class Message(BaseModel):
    """A single chat message (user / assistant / system / tool)."""
    role: str
    content: Optional[Union[str, List[Dict[str, Any]]]] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List["ToolCall"]] = None


# ChatMessage — alias used by newer tests
ChatMessage = Message


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

class FunctionDefinition(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


# ToolFunction — alias expected by tests
ToolFunction = FunctionDefinition


class Tool(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class FunctionCall(BaseModel):
    name: str
    arguments: str  # JSON string


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Any] = None
    system: Optional[str] = None
    thinking: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)


# ---------------------------------------------------------------------------
# Streaming chunk models
# ---------------------------------------------------------------------------

class ChatCompletionChunkDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChunkChoice]


# ---------------------------------------------------------------------------
# Models list
# ---------------------------------------------------------------------------

class OpenAIModel(BaseModel):
    """A single model entry in the /v1/models list."""
    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "kiro"


# ModelCard — backward-compat alias
ModelCard = OpenAIModel


class ModelList(BaseModel):
    """Response body for GET /v1/models."""
    object: Literal["list"] = "list"
    data: List[OpenAIModel] = Field(default_factory=list)
