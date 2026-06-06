"""Pydantic models for the OpenAI-compatible API layer."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageUrlContent(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: Dict[str, str]


ContentPart = Union[TextContent, ImageUrlContent, Dict[str, Any]]


class FunctionDefinition(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolFunction(BaseModel):
    """Function spec inside a tool definition."""
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class OpenAITool(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDefinition


Tool = OpenAITool


class FunctionCall(BaseModel):
    name: str
    arguments: str = "{}"


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Optional[Union[str, List[ContentPart]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


OpenAIMessage = Message
ChatMessage = Message


class ChatCompletionRequest(BaseModel):
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
    thinking: Optional[Dict[str, Any]] = None


OpenAIRequest = ChatCompletionRequest
OpenAIModel = ChatCompletionRequest


class OpenAIUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# Alias: tests and converters expect ChatCompletionUsage
ChatCompletionUsage = OpenAIUsage


class OpenAIChoice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: Optional[str] = None


# Alias: tests expect ChatCompletionChoice
ChatCompletionChoice = OpenAIChoice


class OpenAIResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: OpenAIUsage = Field(default_factory=OpenAIUsage)


class ChatCompletionResponse(BaseModel):
    """Alias for OpenAIResponse — used by tests and converters."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: OpenAIUsage = Field(default_factory=OpenAIUsage)


class ModelData(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "kiro"


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelData] = Field(default_factory=list)
