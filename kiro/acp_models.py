"""ACP (Agent Communication Protocol) Pydantic models."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Primitive content blocks
# ---------------------------------------------------------------------------

class ACPTextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ACPImageBlock(BaseModel):
    """Image content block carried in ACP messages."""
    type: Literal["image"] = "image"
    source: Dict[str, Any]  # {type, media_type, data} or {type, url}


class ACPToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str = Field(default_factory=lambda: f"tool_{uuid.uuid4().hex[:8]}")
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


class ACPToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: bool = False


class ACPThinkingBlock(BaseModel):
    """Extended-thinking block in an ACP message."""
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None


# Backward-compat aliases
ACPToolResult = ACPToolResultBlock
ACPTool = ACPToolUseBlock

ContentBlock = Union[
    ACPTextBlock, ACPImageBlock, ACPToolUseBlock,
    ACPToolResultBlock, ACPThinkingBlock,
]


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class PromptMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: Union[str, List[Dict[str, Any]]]


# Alias: tests and conftest use ACPMessage
ACPMessage = PromptMessage


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

class ACPToolDefinition(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Union[str, int] = Field(default_factory=lambda: str(uuid.uuid4()))
    method: str
    params: Optional[Dict[str, Any]] = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response envelope."""
    jsonrpc: str = "2.0"
    id: Union[str, int, None] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


# ---------------------------------------------------------------------------
# ACP request / response
# ---------------------------------------------------------------------------

class ACPRequest(BaseModel):
    messages: List[PromptMessage]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    tools: Optional[List[ACPToolDefinition]] = None
    system: Optional[str] = None
    stream: bool = False
    temperature: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class ACPUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ACPResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    type: str = "message"
    role: Literal["assistant"] = "assistant"
    content: List[Dict[str, Any]] = Field(default_factory=list)
    model: Optional[str] = None
    stop_reason: Optional[str] = None
    usage: ACPUsage = Field(default_factory=ACPUsage)
