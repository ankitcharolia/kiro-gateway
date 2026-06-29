"""
Unit tests for kiro.model_validation (issue #42).

Requested models are validated against the live catalogue: strict raises,
warn logs + falls back, off / empty / unknown-catalogue are no-ops.
"""
from __future__ import annotations

import pytest

from kiro.model_validation import ModelNotAvailableError, validate_model

CATALOGUE = [
    {"id": "auto", "name": "auto"},
    {"id": "claude-opus-4.8", "name": "Claude Opus 4.8"},
    {"id": "claude-sonnet-4.6", "name": "Claude Sonnet 4.6"},
]


class TestValidateModel:
    def test_known_model_passes_in_strict(self):
        # No exception → known model accepted.
        validate_model("claude-opus-4.8", CATALOGUE, "strict")

    def test_unknown_model_raises_in_strict(self):
        with pytest.raises(ModelNotAvailableError) as ei:
            validate_model("gpt-4o", CATALOGUE, "strict")
        assert ei.value.requested == "gpt-4o"
        assert ei.value.available == ["auto", "claude-opus-4.8", "claude-sonnet-4.6"]
        assert "gpt-4o" in str(ei.value)

    def test_unknown_model_warn_does_not_raise(self, caplog):
        # warn mode must not raise; it logs (loguru, not captured by caplog, but
        # the key contract is "no exception + fall through").
        validate_model("gpt-4o", CATALOGUE, "warn")  # no raise

    def test_off_mode_skips_even_unknown(self):
        validate_model("gpt-4o", CATALOGUE, "off")  # no raise

    def test_empty_requested_is_skipped(self):
        validate_model(None, CATALOGUE, "strict")
        validate_model("", CATALOGUE, "strict")

    def test_empty_catalogue_is_skipped_even_strict(self):
        # Cold start: nothing to validate against → never raises.
        validate_model("gpt-4o", [], "strict")

    def test_unknown_mode_defaults_to_warn(self):
        # An unexpected mode string behaves like warn (no raise).
        validate_model("gpt-4o", CATALOGUE, "bogus")

    def test_catalogue_without_ids_is_skipped(self):
        validate_model("gpt-4o", [{"name": "x"}], "strict")

    def test_message_lists_available_models(self):
        err = ModelNotAvailableError("x", ["a", "b"])
        assert "a, b" in str(err)

    def test_message_handles_empty_available(self):
        err = ModelNotAvailableError("x", [])
        assert "none discovered" in str(err)
