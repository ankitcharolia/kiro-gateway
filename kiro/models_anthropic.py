"""Pydantic models for the Anthropic-compatible API layer."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class UrlImageSource(BaseModel):
    type: Literal["url"] = "url"
    url: str


class Base64ImageSource(BaseModel):
    """Base-64 encoded image source for Anthropic vision requests."""
    type: Literal["base64"] = "base64"
    media_type: str
    data: str


ImageSource = Union[UrlImageSource, Base64ImageSource]


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


TextContentBlock = TextBlock


class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    source: Union[UrlImageSource, Base64ImageSource, Dict[str, Any]]


class ToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


ToolUseContentBlock = ToolUseBlock


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: bool = False


ToolResultContentBlock = ToolResultBlock


class ThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None


ThinkingContentBlock = ThinkingBlock


class RedactedThinkingBlock(BaseModel):
    """Redacted thinking block — returned when thinking is hidden by Anthropic."""
    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str


RedactedThinkingContentBlock = RedactedThinkingBlock


class ToolReferenceBlock(BaseModel):
    """Claude Code deferred tool reference block."""
    type: Literal["tool_reference"] = "tool_reference"
    tool_name: str


ToolReferenceContentBlock = ToolReferenceBlock


ContentBlock = Union[
    TextBlock, ImageBlock, ToolUseBlock, ToolResultBlock,
    ThinkingBlock, RedactedThinkingBlock, ToolReferenceBlock,
]


class ThinkingConfig(BaseModel):
    """Controls extended-thinking (budget_tokens) on Anthropic requests."""
    type: Literal["enabled", "disabled"] = "enabled"
    budget_tokens: int = 10_000


class AnthropicTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[Dict[str, Any]]]


class AnthropicRequest(BaseModel):
    model: str
    messages: List[AnthropicMessage]
    max_tokens: int = 4096
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    tools: Optional[List[AnthropicTool]] = None
    temperature: Optional[float] = None
    stream: Optional[bool] = None
    thinking: Optional[ThinkingConfig] = None
    metadata: Optional[Dict[str, Any]] = None
    stop_sequences: Optional[List[str]] = None


class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicResponse(BaseModel):
    id: str
    type: str = "message"
    role: Literal["assistant"] = "assistant"
    content: List[Dict[str, Any]] = Field(default_factory=list)
    model: str
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage = Field(default_factory=AnthropicUsage)
