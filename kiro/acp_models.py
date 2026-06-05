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


# Backward-compat alias used by some shim modules.
ACPToolCall = ACPToolUseBlock


class ACPToolResultBlock(BaseModel):
    """A tool-result block sent back to the model."""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: bool = False


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


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ACPRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[str, int]
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response
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

    # JSON-RPC envelope fields (optional — present when wrapping a raw RPC response)
    jsonrpc: Optional[str] = None
    error: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Streaming events
# ---------------------------------------------------------------------------

class ACPStreamEvent(BaseModel):
    event: str
    data: Dict[str, Any] = Field(default_factory=dict)
