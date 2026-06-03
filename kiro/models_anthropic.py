"""Pydantic models for the Anthropic-compatible API surface."""
from __future__ import annotations
from typing import Any, Optional, Union
from pydantic import BaseModel, field_validator


class AnthropicContentBlock(BaseModel):
    type: str
    text: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[dict[str, Any]] = None
    tool_use_id: Optional[str] = None
    content: Optional[Any] = None


class AnthropicMessage(BaseModel):
    role: str
    content: Union[str, list[AnthropicContentBlock]]


class AnthropicTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: dict[str, Any] = {}


class AnthropicRequest(BaseModel):
    model: str
    messages: list[AnthropicMessage]
    max_tokens: int = 4096
    system: Optional[str] = None
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    tools: Optional[list[AnthropicTool]] = None
    tool_choice: Optional[Any] = None

    @field_validator("messages")
    @classmethod
    def messages_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("messages must not be empty")
        return v


class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    model: str
    content: list[AnthropicContentBlock]
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage
