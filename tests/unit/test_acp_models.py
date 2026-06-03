"""
Unit tests for ACP Pydantic models.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from kiro.acp_models import PromptMessage


def test_prompt_message_user():
    msg = PromptMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


def test_prompt_message_assistant():
    msg = PromptMessage(role="assistant", content="Hi")
    assert msg.role == "assistant"


def test_prompt_message_system():
    msg = PromptMessage(role="system", content="Be helpful")
    assert msg.role == "system"


def test_prompt_message_empty_content_allowed():
    """Empty content should be allowed (e.g. tool placeholder messages)."""
    msg = PromptMessage(role="user", content="")
    assert msg.content == ""


def test_prompt_message_serialises_to_dict():
    msg = PromptMessage(role="user", content="test")
    d = msg.model_dump()
    assert d["role"] == "user"
    assert d["content"] == "test"
