# -*- coding: utf-8 -*-
"""
Pydantic models for ACP (Agent Client Protocol) JSON-RPC 2.0 messages.

This module contains two layers:
  1. JSON-RPC 2.0 envelope types (JsonRpcRequest, JsonRpcResponse, ...)
  2. Higher-level ACP request/response/content-block types used by the
     converter, streaming, and shim modules.

ACP spec: https://agentclientprotocol.com
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[str, int] = Field(default_factory=lambda: str(uuid.uuid4()))
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


class JsonRpcNotification(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ACP capability types
# ---------------------------------------------------------------------------

class FilesystemRoot(BaseModel):
    uri: str
    name: Optional[str] = None
    read: bool = True
    write: bool = False


class TerminalCapability(BaseModel):
    allowed_commands: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    timeout_seconds: int = 30


class GatewayCapabilities(BaseModel):
    filesystem: List[FilesystemRoot] = Field(default_factory=list)
    terminal: Optional[TerminalCapability] = None
    tools: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ACP session
# ---------------------------------------------------------------------------

class SessionInitParams(BaseModel):
    capabilities: GatewayCapabilities = Field(default_factory=GatewayCapabilities)
    client_info: Dict[str, str] = Field(default_factory=lambda: {
        "name": "kiro-gateway",
        "version": "2.1.0",
    })


class SessionInitResult(BaseModel):
    session_id: str
    server_capabilities: Dict[str, Any] = Field(default_factory=dict)
    server_info: Dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ACP prompt / completion (JSON-RPC layer)
# ---------------------------------------------------------------------------

class PromptMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False


class PromptParams(BaseModel):
    session_id: str
    messages: List[PromptMessage]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[ToolResult] = Field(default_factory=list)
    stream: bool = True


# ---------------------------------------------------------------------------
# ACP progress events (notifications from kiro-cli)
# ---------------------------------------------------------------------------

class ProgressParams(BaseModel):
    session_id: str
    type: str
    delta: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    finish_reason: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


# ---------------------------------------------------------------------------
# Capability mediation requests (kiro-cli -> gateway)
# ---------------------------------------------------------------------------

class ReadFileParams(BaseModel):
    uri: str


class WriteFileParams(BaseModel):
    uri: str
    content: str


class RunCommandParams(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    timeout_seconds: int = 30


class ListDirectoryParams(BaseModel):
    uri: str


# ---------------------------------------------------------------------------
# Native ACP HTTP request/response models (legacy)
# ---------------------------------------------------------------------------

class ACPChatRequest(BaseModel):
    messages: List[PromptMessage]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    stream: bool = False
    filesystem_roots: List[FilesystemRoot] = Field(default_factory=list)
    terminal: Optional[TerminalCapability] = None


class ACPChatResponse(BaseModel):
    session_id: str
    content: str
    tool_calls: List[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = Field(default_factory=dict)


# ===========================================================================
# Higher-level ACP types used by converter / streaming / shim modules
# ===========================================================================

# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------

class ACPTextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str = ""


class ACPThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    signature: Optional[str] = None


class ACPRedactedThinkingBlock(BaseModel):
    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str = ""


class ACPToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str = Field(default_factory=lambda: f"toolu_{uuid.uuid4().hex[:12]}")
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


class ACPToolResult(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str = ""
    is_error: bool = False


class ACPImageBlock(BaseModel):
    type: Literal["image"] = "image"
    source: Dict[str, Any] = Field(default_factory=dict)


# Union of all content block types
ACPContentBlock = Union[
    ACPTextBlock,
    ACPThinkingBlock,
    ACPRedactedThinkingBlock,
    ACPToolUseBlock,
    ACPToolResult,
    ACPImageBlock,
]


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

class ACPTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

class ACPMessage(BaseModel):
    role: str  # "user" | "assistant" | "system" | "tool"
    content: List[ACPContentBlock] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

class ACPUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Top-level request / response
# ---------------------------------------------------------------------------

class ACPRequest(BaseModel):
    model: str
    messages: List[ACPMessage]
    system: Optional[str] = None
    max_tokens: int = 4096
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: bool = False
    tools: Optional[List[ACPTool]] = None
    stop_sequences: Optional[List[str]] = None
    thinking: Optional[Dict[str, Any]] = None
    tool_choice: Optional[Dict[str, Any]] = None


class ACPResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex}")
    type: str = "message"
    role: str = "assistant"
    model: str
    content: List[ACPContentBlock] = Field(default_factory=list)
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: Optional[ACPUsage] = None
