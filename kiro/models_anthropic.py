"""Pydantic models for the Anthropic-compatible API surface."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Thinking / budget config
# ---------------------------------------------------------------------------

class ThinkingConfig(BaseModel):
    type: Literal["enabled", "disabled"] = "enabled"
    budget_tokens: Optional[int] = None


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

class AnthropicTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class AnthropicToolChoiceAuto(BaseModel):
    type: Literal["auto"] = "auto"
    disable_parallel_tool_use: Optional[bool] = None


class AnthropicToolChoiceAny(BaseModel):
    type: Literal["any"] = "any"
    disable_parallel_tool_use: Optional[bool] = None


class AnthropicToolChoiceTool(BaseModel):
    type: Literal["tool"] = "tool"
    name: str
    disable_parallel_tool_use: Optional[bool] = None


AnthropicToolChoice = Union[
    AnthropicToolChoiceAuto,
    AnthropicToolChoiceAny,
    AnthropicToolChoiceTool,
]


# ---------------------------------------------------------------------------
# Content blocks — request side
# ---------------------------------------------------------------------------

class TextContentBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ThinkingContentBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None


class RedactedThinkingContentBlock(BaseModel):
    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str


class ToolUseContentBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


class ToolResultContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolResultContentBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Optional[Union[str, List[ToolResultContent]]] = None
    is_error: Optional[bool] = None


class ImageSource(BaseModel):
    type: Literal["base64", "url"] = "base64"
    media_type: Optional[str] = None
    data: Optional[str] = None
    url: Optional[str] = None


class ImageContentBlock(BaseModel):
    type: Literal["image"] = "image"
    source: ImageSource


class DocumentSource(BaseModel):
    type: Literal["base64", "text", "url"] = "base64"
    media_type: Optional[str] = None
    data: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None


class DocumentContentBlock(BaseModel):
    type: Literal["document"] = "document"
    source: DocumentSource
    title: Optional[str] = None
    context: Optional[str] = None
    citations: Optional[Dict[str, Any]] = None


RequestContentBlock = Union[
    TextContentBlock,
    ThinkingContentBlock,
    RedactedThinkingContentBlock,
    ToolUseContentBlock,
    ToolResultContentBlock,
    ImageContentBlock,
    DocumentContentBlock,
]


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[RequestContentBlock]]


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class AnthropicRequest(BaseModel):
    model: str
    messages: List[AnthropicMessage]
    max_tokens: int = 4096
    system: Optional[Union[str, List[TextContentBlock]]] = None
    tools: Optional[List[AnthropicTool]] = None
    tool_choice: Optional[AnthropicToolChoice] = None
    thinking: Optional[ThinkingConfig] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = False
    metadata: Optional[Dict[str, Any]] = None
    extra_headers: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# Response — non-streaming
# ---------------------------------------------------------------------------

class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None


ResponseContentBlock = Union[
    TextContentBlock,
    ThinkingContentBlock,
    RedactedThinkingContentBlock,
    ToolUseContentBlock,
]


class AnthropicResponse(BaseModel):
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    model: str
    content: List[ResponseContentBlock] = Field(default_factory=list)
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage = Field(default_factory=AnthropicUsage)


# ---------------------------------------------------------------------------
# Streaming event models
# ---------------------------------------------------------------------------

class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ThinkingDelta(BaseModel):
    type: Literal["thinking_delta"] = "thinking_delta"
    thinking: str


class SignatureDelta(BaseModel):
    type: Literal["signature_delta"] = "signature_delta"
    signature: str


class InputJsonDelta(BaseModel):
    type: Literal["input_json_delta"] = "input_json_delta"
    partial_json: str


ContentBlockDelta = Union[TextDelta, ThinkingDelta, SignatureDelta, InputJsonDelta]


class ContentBlockStart(BaseModel):
    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: ResponseContentBlock


class ContentBlockStop(BaseModel):
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class MessageDelta(BaseModel):
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None


class MessageDeltaUsage(BaseModel):
    output_tokens: int = 0


# SSE event wrapper types
class MessageStartEvent(BaseModel):
    type: Literal["message_start"] = "message_start"
    message: AnthropicResponse


class MessageDeltaEvent(BaseModel):
    type: Literal["message_delta"] = "message_delta"
    delta: MessageDelta
    usage: Optional[MessageDeltaUsage] = None


class MessageStopEvent(BaseModel):
    type: Literal["message_stop"] = "message_stop"


class ContentBlockStartEvent(BaseModel):
    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: ResponseContentBlock


class ContentBlockDeltaEvent(BaseModel):
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: ContentBlockDelta


class ContentBlockStopEvent(BaseModel):
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


StreamEvent = Union[
    MessageStartEvent,
    MessageDeltaEvent,
    MessageStopEvent,
    ContentBlockStartEvent,
    ContentBlockDeltaEvent,
    ContentBlockStopEvent,
]
