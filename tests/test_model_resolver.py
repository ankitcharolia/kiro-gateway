"""Tests for model alias resolution."""
from __future__ import annotations

import pytest

from kiro.model_resolver import resolve_model, get_capabilities, list_models


class TestModelResolver:
    def test_exact_canonical_passthrough(self):
        assert resolve_model("claude-sonnet-4-5") == "claude-sonnet-4-5"

    def test_gpt4o_maps_to_sonnet(self):
        assert resolve_model("gpt-4o") == "claude-sonnet-4-5"

    def test_gpt4o_mini_maps_to_haiku(self):
        assert resolve_model("gpt-4o-mini") == "claude-haiku-3-5"

    def test_o1_maps_to_opus(self):
        assert resolve_model("o1") == "claude-opus-4"

    def test_old_sonnet_alias(self):
        assert resolve_model("claude-3-5-sonnet-20241022") == "claude-sonnet-4-5"

    def test_unknown_model_passthrough(self):
        assert resolve_model("some-unknown-model") == "some-unknown-model"

    def test_sonnet_supports_thinking(self):
        cap = get_capabilities("claude-sonnet-4-5")
        assert cap.supports_thinking is True

    def test_haiku_no_thinking(self):
        cap = get_capabilities("claude-haiku-3-5")
        assert cap.supports_thinking is False

    def test_list_models_nonempty(self):
        models = list_models()
        assert len(models) > 0
        assert all("id" in m for m in models)
