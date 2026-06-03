# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/ankitcharolia/kiro-gateway
#
# Licensed under the GNU Affero General Public License v3.0
# See LICENSE for details.

"""
Kiro Gateway - ACP-compliant proxy for the Kiro CLI.

This package translates OpenAI / Anthropic API requests into
ACP (JSON-RPC 2.0 over stdio) calls forwarded to the official
kiro CLI subprocess.  Authentication is fully delegated to the
kiro CLI; no credentials are stored or managed here.

Modules:
    - config: Configuration and constants
    - models_openai / models_anthropic: Pydantic request/response models
    - acp_client: JSON-RPC 2.0 transport to the kiro CLI subprocess
    - shim_service: Orchestration + tool-call round-trips
    - cache: Model metadata cache
    - converters_*: Format conversion (OpenAI/Anthropic <-> ACP)
    - parsers: AWS SSE stream parsers
    - streaming_*: Response streaming logic
    - http_client: HTTP client with retry logic
    - routes_openai / routes_anthropic: FastAPI route handlers
    - compliance: Single-account enforcement
    - exceptions: Exception handlers
"""

# Version is imported from config.py — the single source of truth
from kiro.config import APP_VERSION as __version__

__author__ = "ankitcharolia"

# Main components for convenient import
# NOTE: KiroAuthManager has been removed — authentication is fully delegated
#       to the kiro CLI subprocess via kiro/acp_client.py.
from kiro.cache import ModelInfoCache
from kiro.http_client import KiroHttpClient
from kiro.routes_openai import router
from kiro.model_resolver import ModelResolver, normalize_model_name, get_model_id_for_kiro

# Configuration
from kiro.config import (
    PROXY_API_KEY,
    REGION,
    HIDDEN_MODELS,
    APP_VERSION,
)

# Models
from kiro.models_openai import (
    ChatCompletionRequest,
    ChatMessage,
    OpenAIModel,
    ModelList,
)

# Converters
from kiro.converters_openai import build_kiro_payload
from kiro.converters_core import (
    extract_text_content,
    merge_adjacent_messages,
)

# Parsers
from kiro.parsers import (
    AwsEventStreamParser,
    parse_bracket_tool_calls,
)

# Streaming
from kiro.streaming_openai import (
    stream_kiro_to_openai,
    collect_stream_response,
)

# Exceptions
from kiro.exceptions import (
    validation_exception_handler,
    sanitize_validation_errors,
)

__all__ = [
    # Version
    "__version__",

    # Main classes (KiroAuthManager intentionally absent — auth lives in kiro CLI)
    "ModelInfoCache",
    "KiroHttpClient",
    "ModelResolver",
    "router",

    # Configuration
    "PROXY_API_KEY",
    "REGION",
    "HIDDEN_MODELS",
    "APP_VERSION",

    # Model resolution
    "normalize_model_name",
    "get_model_id_for_kiro",

    # Models
    "ChatCompletionRequest",
    "ChatMessage",
    "OpenAIModel",
    "ModelList",

    # Converters
    "build_kiro_payload",
    "extract_text_content",
    "merge_adjacent_messages",

    # Parsers
    "AwsEventStreamParser",
    "parse_bracket_tool_calls",

    # Streaming
    "stream_kiro_to_openai",
    "collect_stream_response",

    # Exceptions
    "validation_exception_handler",
    "sanitize_validation_errors",
]
