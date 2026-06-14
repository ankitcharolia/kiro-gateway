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
ACPToolCall = ACPToolUseBlock        # alias expected by converters_core

# ToolCall alias expected by shim_service and tests
ToolCall = ACPToolUseBlock

# ToolResult alias expected by shim_service
ToolResult = ACPToolResultBlock

ContentBlock = Union[
    ACPTextBlock, ACPImageBlock, ACPToolUseBlock,
    ACPToolResultBlock, ACPThinkingBlock,
]

# ACPContentBlock — top-level Union used by converters_core and tests
ACPContentBlock = ContentBlock


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


class ACPToolDef(BaseModel):
    """Tool definition model (input schema variant)."""
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


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object — must be defined before JsonRpcResponse."""
    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response envelope."""
    jsonrpc: str = "2.0"
    id: Union[str, int, None] = None
    result: Optional[Any] = None
    # Typed as JsonRpcError (not Dict) so Pydantic coerces the incoming dict
    # and acp_client._call can access .code / .message / .data as attributes.
    error: Optional[JsonRpcError] = None


# Notification is a request that expects no response (no id required in reply)
JsonRpcNotification = JsonRpcRequest


# ---------------------------------------------------------------------------
# ACP session bootstrap models (used by acp_client)
# ---------------------------------------------------------------------------

class GatewayCapabilities(BaseModel):
    """Capabilities the gateway advertises during session initialisation."""
    readFile: bool = True
    writeFile: bool = True
    runCommand: bool = False
    listDirectory: bool = True
    filesystem: Optional[List[Any]] = Field(default_factory=list)
    terminal: Optional[Any] = None


class FilesystemRoot(BaseModel):
    """A filesystem root exposed to kiro-cli."""
    path: str
    read_only: bool = False


class TerminalCapability(BaseModel):
    """Terminal capability descriptor."""
    enabled: bool = True
    allowed_commands: Optional[List[str]] = None


class SessionInitParams(BaseModel):
    capabilities: GatewayCapabilities = Field(default_factory=GatewayCapabilities)


class SessionInitResult(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    protocol_version: str = "1.0"


class PromptParams(BaseModel):
    session_id: str
    messages: List[PromptMessage] = Field(default_factory=list)
    model: Optional[str] = None
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: Optional[List[ACPToolDefinition]] = None
    tool_results: Optional[List[ACPToolResultBlock]] = None


class ProgressParams(BaseModel):
    """ACP progress notification payload."""
    session_id: str
    type: str  # e.g. 'text_delta', 'done', 'error'
    data: Optional[Dict[str, Any]] = None


# Capability request param models
class ReadFileParams(BaseModel):
    path: str


class WriteFileParams(BaseModel):
    path: str
    content: str


class RunCommandParams(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)
    cwd: Optional[str] = None


class ListDirectoryParams(BaseModel):
    path: str
    recursive: bool = False


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
    top_p: Optional[float] = None
    stop_sequences: Optional[List[str]] = None
    thinking: Optional[Dict[str, Any]] = None
    tool_choice: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class ACPUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ACPResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    type: str = "message"
    role: Literal["assistant"] = "assistant"
    # Accept typed content blocks OR raw dicts (for JSON deserialization)
    content: List[Union[
        ACPTextBlock, ACPImageBlock, ACPToolUseBlock,
        ACPToolResultBlock, ACPThinkingBlock, Dict[str, Any]
    ]] = Field(default_factory=list)
    model: Optional[str] = None
    stop_reason: Optional[str] = None
    usage: ACPUsage = Field(default_factory=ACPUsage)


# ---------------------------------------------------------------------------
# ACP HTTP chat models (used by routes_acp)
# ---------------------------------------------------------------------------

class ACPChatRequest(BaseModel):
    """Request body for POST /acp/chat and POST /acp/chat/stream."""
    messages: List[PromptMessage]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: Optional[List[ACPToolDefinition]] = None
    filesystem_roots: Optional[List[Dict[str, Any]]] = None
    terminal: Optional[Dict[str, Any]] = None
    stream: bool = False
    thinking: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class ACPChatResponse(BaseModel):
    """Response body for POST /acp/chat."""
    session_id: str = ""
    content: str = ""
    tool_calls: List[ACPToolUseBlock] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, Any] = Field(default_factory=dict)
