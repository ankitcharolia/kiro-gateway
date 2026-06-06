"""Anthropic-compatible Pydantic models."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Image source models
# ---------------------------------------------------------------------------

class Base64ImageSource(BaseModel):
    """Base64-encoded image source for Anthropic image blocks."""
    type: Literal["base64"] = "base64"
    media_type: str  # e.g. "image/jpeg"
    data: str        # base64-encoded bytes


class URLImageSource(BaseModel):
    """URL-referenced image source."""
    type: Literal["url"] = "url"
    url: str


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
    type: Literal["image"] = "image"
    source: Union[Base64ImageSource, URLImageSource, Dict[str, Any]]


class ToolReferenceContentBlock(BaseModel):
    type: Literal["tool_reference"] = "tool_reference"
    id: str
    name: str


# Union alias used by tests
ContentBlock = Union[
    TextContentBlock,
    ToolUseContentBlock,
    ToolResultContentBlock,
    ThinkingContentBlock,
    ImageContentBlock,
    ToolReferenceContentBlock,
]

# Backward-compat alias
AnthropicContentBlock = ContentBlock


# ---------------------------------------------------------------------------
# System prompt block
# ---------------------------------------------------------------------------

class SystemContentBlock(BaseModel):
    """A typed system-prompt content block (Anthropic extended format)."""
    type: Literal["text"] = "text"
    text: str


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

class AnthropicTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool choice
# ---------------------------------------------------------------------------

class ToolChoiceAuto(BaseModel):
    type: Literal["auto"] = "auto"


class ToolChoiceAny(BaseModel):
    type: Literal["any"] = "any"


class ToolChoiceTool(BaseModel):
    type: Literal["tool"] = "tool"
    name: str


ToolChoice = Union[ToolChoiceAuto, ToolChoiceAny, ToolChoiceTool]


# ---------------------------------------------------------------------------
# Thinking config
# ---------------------------------------------------------------------------

class ThinkingConfig(BaseModel):
    """Extended thinking configuration block."""
    type: Literal["enabled", "disabled"] = "enabled"
    budget_tokens: Optional[int] = None


# ---------------------------------------------------------------------------
# Message request / response
# ---------------------------------------------------------------------------

class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[Dict[str, Any]]]


class AnthropicRequest(BaseModel):
    """Anthropic /v1/messages request (legacy name kept for compat)."""
    model: str
    messages: List[AnthropicMessage]
    max_tokens: int = 8192
    system: Optional[Union[str, List[SystemContentBlock]]] = None
    tools: Optional[List[AnthropicTool]] = None
    tool_choice: Optional[Any] = None
    stream: bool = False
    temperature: Optional[float] = None
    thinking: Optional[ThinkingConfig] = None


class AnthropicMessagesRequest(AnthropicRequest):
    """Alias matching the newer test import name."""
    pass


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
