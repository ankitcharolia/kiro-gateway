"""Pydantic models for the OpenAI-compatible API layer."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------

class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageUrlContent(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: Dict[str, str]  # {"url": "..."}


ContentPart = Union[TextContent, ImageUrlContent, Dict[str, Any]]


# ---------------------------------------------------------------------------
# Tool / function definitions
# ---------------------------------------------------------------------------

class FunctionDefinition(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class OpenAITool(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDefinition


# Alias expected by conftest / tests
Tool = OpenAITool


class FunctionCall(BaseModel):
    """Represents a function call within a tool_call (name + arguments string)."""
    name: str
    arguments: str = "{}"


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class Message(BaseModel):
    """A single chat message (OpenAI schema)."""
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Optional[Union[str, List[ContentPart]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


# Alias for backwards compat
OpenAIMessage = Message


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------

class ChatCompletionRequest(BaseModel):
    """OpenAI /v1/chat/completions request body."""
    model: str
    messages: List[Message]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: Optional[bool] = None
    tools: Optional[List[OpenAITool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    stop: Optional[Union[str, List[str]]] = None
    n: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    user: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    thinking: Optional[Dict[str, Any]] = None  # {"type": "enabled", "budget_tokens": N}


# Aliases expected by various tests
OpenAIRequest = ChatCompletionRequest
OpenAIModel = ChatCompletionRequest


class OpenAIUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIChoice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: Optional[str] = None


class OpenAIResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: OpenAIUsage = Field(default_factory=OpenAIUsage)


class ModelData(BaseModel):
    """A single model entry in the /v1/models listing."""
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "kiro"


class ModelList(BaseModel):
    """Response body for GET /v1/models."""
    object: str = "list"
    data: List[ModelData] = Field(default_factory=list)
