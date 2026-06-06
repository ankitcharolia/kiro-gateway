"""Pydantic models for the Anthropic-compatible API layer."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class UrlImageSource(BaseModel):
    type: Literal["url"] = "url"
    url: str


# Alias: tests expect URLImageSource (capital URL)
URLImageSource = UrlImageSource


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


ImageContentBlock = ImageBlock


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
    signature: Optional[str] = ""

    @property
    def signature_value(self) -> str:
        return self.signature or ""


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


# ---------------------------------------------------------------------------
# System content
# ---------------------------------------------------------------------------

class SystemContentBlock(BaseModel):
    """System prompt content block (type='text')."""
    type: Literal["text"] = "text"
    text: str


# ---------------------------------------------------------------------------
# Tool models
# ---------------------------------------------------------------------------

class ThinkingConfig(BaseModel):
    """Controls extended-thinking (budget_tokens) on Anthropic requests."""
    type: Literal["enabled", "disabled"] = "enabled"
    budget_tokens: int = 10_000


class AnthropicTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class ToolChoiceAuto(BaseModel):
    type: Literal["auto"] = "auto"


class ToolChoiceAny(BaseModel):
    type: Literal["any"] = "any"


class ToolChoiceTool(BaseModel):
    type: Literal["tool"] = "tool"
    name: str


ToolChoice = Union[ToolChoiceAuto, ToolChoiceAny, ToolChoiceTool]


# ---------------------------------------------------------------------------
# Message and request models
# ---------------------------------------------------------------------------

class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[Any]]


class AnthropicRequest(BaseModel):
    model: str
    messages: List[AnthropicMessage]
    max_tokens: int = 4096
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    tools: Optional[List[AnthropicTool]] = None
    tool_choice: Optional[Any] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: Optional[bool] = None
    thinking: Optional[ThinkingConfig] = None
    metadata: Optional[Dict[str, Any]] = None
    stop_sequences: Optional[List[str]] = None


# Alias: tests use AnthropicMessagesRequest
AnthropicMessagesRequest = AnthropicRequest


# ---------------------------------------------------------------------------
# Usage and response models
# ---------------------------------------------------------------------------

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


# Alias: tests use AnthropicMessagesResponse
AnthropicMessagesResponse = AnthropicResponse


# ---------------------------------------------------------------------------
# Streaming event models
# ---------------------------------------------------------------------------

class MessageStartEvent(BaseModel):
    type: Literal["message_start"] = "message_start"
    message: Dict[str, Any] = Field(default_factory=dict)


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str = ""


class ThinkingDelta(BaseModel):
    type: Literal["thinking_delta"] = "thinking_delta"
    thinking: str = ""


class InputJsonDelta(BaseModel):
    type: Literal["input_json_delta"] = "input_json_delta"
    partial_json: str = ""


class ContentBlockStartEvent(BaseModel):
    type: Literal["content_block_start"] = "content_block_start"
    index: int = 0
    content_block: Dict[str, Any] = Field(default_factory=dict)


class ContentBlockDeltaEvent(BaseModel):
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int = 0
    delta: Union[TextDelta, ThinkingDelta, InputJsonDelta, Dict[str, Any]]


class ContentBlockStopEvent(BaseModel):
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int = 0


class MessageDeltaUsage(BaseModel):
    output_tokens: int = 0


class MessageDeltaEvent(BaseModel):
    type: Literal["message_delta"] = "message_delta"
    delta: Dict[str, Any] = Field(default_factory=dict)
    usage: MessageDeltaUsage = Field(default_factory=MessageDeltaUsage)


class MessageStopEvent(BaseModel):
    type: Literal["message_stop"] = "message_stop"


class PingEvent(BaseModel):
    type: Literal["ping"] = "ping"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Error models
# ---------------------------------------------------------------------------

class AnthropicErrorDetail(BaseModel):
    type: str
    message: str


class AnthropicErrorResponse(BaseModel):
    type: Literal["error"] = "error"
    error: AnthropicErrorDetail
