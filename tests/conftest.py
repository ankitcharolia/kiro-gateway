from __future__ import annotations
import os
import pytest

os.environ.setdefault("PROXY_API_KEY", "test-proxy-key")
os.environ.setdefault("KIRO_CLI_PATH", "kiro")
os.environ.setdefault("COMPLIANCE_MODE", "true")
os.environ.setdefault("ACCOUNT_SYSTEM", "false")
os.environ.setdefault("TRUNCATION_RECOVERY", "true")
os.environ.setdefault("DEBUG_MODE", "false")

@pytest.fixture()
def proxy_key() -> str:
    return "test-proxy-key"

@pytest.fixture()
def auth_headers(proxy_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {proxy_key}"}

@pytest.fixture()
def sample_openai_request() -> dict:
    return {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    }

@pytest.fixture()
def sample_anthropic_request() -> dict:
    return {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 1024,
        "stream": False,
    }

@pytest.fixture(autouse=True)
def reset_truncation_state():
    from kiro import truncation_state
    truncation_state.clear_all()
    yield
    truncation_state.clear_all()
