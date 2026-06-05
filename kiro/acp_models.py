"""Pydantic models for ACP (Agent Client Protocol) JSON-RPC payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


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
# Request / Response
# ---------------------------------------------------------------------------

class ACPRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[str, int]
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ACPResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[str, int]
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Streaming events
# ---------------------------------------------------------------------------

class ACPStreamEvent(BaseModel):
    event: str
    data: Dict[str, Any] = Field(default_factory=dict)
