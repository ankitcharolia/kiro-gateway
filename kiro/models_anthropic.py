"""Anthropic-compatible Pydantic models."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------

class TextContentBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolUseContentBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


class ToolResultContentBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: bool = False


class ThinkingContentBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None


class ImageContentBlock(BaseModel):
    """Image block with base64 source."""
    type: Literal["image"] = "image"
    source: Dict[str, Any]


class ToolReferenceContentBlock(BaseModel):
    """Reference to a previously defined tool (used in some Anthropic API versions)."""
    type: Literal["tool_reference"] = "tool_reference"
    id: str
    name: str


AnthropicContentBlock = Union[
    TextContentBlock,
    ToolUseContentBlock,
    ToolResultContentBlock,
    ThinkingContentBlock,
    ImageContentBlock,
    ToolReferenceContentBlock,
]


# ---------------------------------------------------------------------------
# Message request / response
# ---------------------------------------------------------------------------

class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[Dict[str, Any]]]


class AnthropicRequest(BaseModel):
    model: str
    messages: List[AnthropicMessage]
    max_tokens: int = 8192
    system: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    stream: bool = False
    temperature: Optional[float] = None


class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicResponse(BaseModel):
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: List[Dict[str, Any]] = Field(default_factory=list)
    model: str
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage = Field(default_factory=AnthropicUsage)
