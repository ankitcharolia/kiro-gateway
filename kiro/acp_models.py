# -*- coding: utf-8 -*-
"""
Pydantic models for ACP (Agent Client Protocol) JSON-RPC 2.0 messages.

ACP spec: https://agentclientprotocol.com
"""
from __future__ import annotations

import uuid
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[str, int] = Field(default_factory=lambda: str(uuid.uuid4()))
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


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
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ACP capability types
# ---------------------------------------------------------------------------

class FilesystemRoot(BaseModel):
    uri: str                        # e.g. "file:///home/user/project"
    name: Optional[str] = None
    read: bool = True
    write: bool = False


class TerminalCapability(BaseModel):
    allowed_commands: list[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    timeout_seconds: int = 30


class GatewayCapabilities(BaseModel):
    filesystem: list[FilesystemRoot] = Field(default_factory=list)
    terminal: Optional[TerminalCapability] = None
    tools: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ACP session
# ---------------------------------------------------------------------------

class SessionInitParams(BaseModel):
    capabilities: GatewayCapabilities = Field(default_factory=GatewayCapabilities)
    client_info: dict[str, str] = Field(default_factory=lambda: {
        "name": "kiro-gateway",
        "version": "2.0.0",
    })


class SessionInitResult(BaseModel):
    session_id: str
    server_capabilities: dict[str, Any] = Field(default_factory=dict)
    server_info: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ACP prompt / completion
# ---------------------------------------------------------------------------

class PromptMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False


class PromptParams(BaseModel):
    session_id: str
    messages: list[PromptMessage]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    stream: bool = True


# ---------------------------------------------------------------------------
# ACP progress events (notifications from kiro-cli)
# ---------------------------------------------------------------------------

class ProgressParams(BaseModel):
    session_id: str
    type: str           # "text" | "tool_call" | "thinking" | "done" | "error"
    delta: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    finish_reason: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[dict[str, int]] = None


# ---------------------------------------------------------------------------
# Capability mediation requests (kiro-cli → gateway)
# ---------------------------------------------------------------------------

class ReadFileParams(BaseModel):
    uri: str


class WriteFileParams(BaseModel):
    uri: str
    content: str


class RunCommandParams(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    timeout_seconds: int = 30


class ListDirectoryParams(BaseModel):
    uri: str


# ---------------------------------------------------------------------------
# Native ACP HTTP request/response models
# ---------------------------------------------------------------------------

class ACPChatRequest(BaseModel):
    messages: list[PromptMessage]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    stream: bool = False
    filesystem_roots: list[FilesystemRoot] = Field(default_factory=list)
    terminal: Optional[TerminalCapability] = None


class ACPChatResponse(BaseModel):
    session_id: str
    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = Field(default_factory=dict)
