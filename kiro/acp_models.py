# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field
from typing import Any, Literal


JsonValue = Any


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class InitializeParams(BaseModel):
    protocolVersion: str = "0.5"
    clientInfo: dict[str, Any] = Field(default_factory=dict)
    clientCapabilities: dict[str, Any] = Field(default_factory=dict)


class SessionPromptParams(BaseModel):
    sessionId: str
    prompt: list[dict[str, Any]] = Field(default_factory=list)


class SessionNewParams(BaseModel):
    cwd: str | None = None
    mcpServers: list[dict[str, Any]] = Field(default_factory=list)
    mode: str | None = None
    _meta: dict[str, Any] = Field(default_factory=dict)
