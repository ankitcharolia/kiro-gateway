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


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: Dict[str, Any]  # {name, arguments}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class OpenAIMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Optional[Union[str, List[ContentPart]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------

class OpenAIRequest(BaseModel):
    model: str
    messages: List[OpenAIMessage]
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


class OpenAIUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIChoice(BaseModel):
    index: int = 0
    message: OpenAIMessage
    finish_reason: Optional[str] = None


class OpenAIResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: OpenAIUsage = Field(default_factory=OpenAIUsage)


# ---------------------------------------------------------------------------
# Backward-compat alias expected by tests
# ---------------------------------------------------------------------------

OpenAIModel = OpenAIRequest
