"""Pydantic models for ACP (Agent Client Protocol) JSON-RPC payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

class ACPUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Tool-use / tool-result blocks
# ---------------------------------------------------------------------------

class ACPToolUseBlock(BaseModel):
    """A tool-use request block returned by the model."""
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


# Backward-compat aliases
ACPToolCall = ACPToolUseBlock
ACPTool = ACPToolUseBlock  # alias expected by converters_core tests


class ACPToolResultBlock(BaseModel):
    """A tool-result block sent back to the model."""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: bool = False


# Alias expected by converters_* and acp_client tests
ACPToolResult = ACPToolResultBlock


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------

class ACPTextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ACPThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None


ACPContentBlock = Union[ACPTextBlock, ACPThinkingBlock, ACPToolUseBlock, ACPToolResultBlock]


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

class ACPMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[ACPContentBlock]]


# PromptMessage — generic role (includes "system") used by tests
class PromptMessage(BaseModel):
    """Generic prompt message supporting user / assistant / system roles."""
    role: str
    content: str


# ---------------------------------------------------------------------------
# JSON-RPC envelope models (used by acp_client)
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    """A JSON-RPC 2.0 request envelope."""
    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[str, int]
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None


# Backward-compat alias
ACPRequest = JsonRpcRequest


# ---------------------------------------------------------------------------
# Full ACP response
# ---------------------------------------------------------------------------

class ACPResponse(BaseModel):
    """Full ACP message response (non-streaming)."""
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    model: str = ""
    content: List[ACPContentBlock] = Field(default_factory=list)
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: ACPUsage = Field(default_factory=ACPUsage)

    # JSON-RPC envelope fields
    jsonrpc: Optional[str] = None
    error: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Streaming events
# ---------------------------------------------------------------------------

class ACPStreamEvent(BaseModel):
    event: str
    data: Dict[str, Any] = Field(default_factory=dict)
