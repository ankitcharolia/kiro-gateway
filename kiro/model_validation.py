# -*- coding: utf-8 -*-
"""
Requested-model validation against the live kiro-cli catalogue (issue #42).

``kiro-cli`` does not validate the model id on ``session/set_model``: an unknown
or foreign id (a typo, or a client defaulting to ``gpt-4o``) is accepted
silently and the session simply stays on its default model — so the caller
believes they are using the requested model but are not.

The gateway therefore validates the requested id against the live
``availableModels`` catalogue (discovered from ``session/new`` and cached on the
``ACPClient``). Behaviour is governed by ``MODEL_VALIDATION``:

* ``warn`` (default) — log a WARNING and fall back to the session default. This
  is **non-silent** yet never breaks a harness that sends a non-matching default
  id (e.g. ``gpt-4o``).
* ``strict`` — raise :class:`ModelNotAvailableError`, which the routes return as
  a ``404`` in each API's native error shape.
* ``off`` — legacy behaviour: forward the id and stay silent.

Validation is skipped when the requested id is empty or the catalogue has not
been discovered yet (before the first session), since there is nothing to
validate against.
"""
from __future__ import annotations

from typing import Optional, Sequence

from loguru import logger


class ModelNotAvailableError(Exception):
    """Raised in ``strict`` mode when a requested model is not in the catalogue.

    Attributes:
        requested: The model id the client asked for.
        available: The sorted list of available model ids.
    """

    def __init__(self, requested: str, available: list[str]):
        self.requested = requested
        self.available = available
        available_str = ", ".join(available) if available else "(none discovered yet)"
        super().__init__(
            f"The model '{requested}' does not exist or is not available through "
            f"this gateway. Available models: {available_str}."
        )


def validate_model(
    requested: Optional[str],
    available_models: Sequence[dict],
    mode: str,
) -> None:
    """Validate a requested model id against the live catalogue.

    Args:
        requested: The model id from the request (may be ``None``/empty).
        available_models: The live catalogue (``{"id", "name", ...}`` dicts),
            typically ``ShimService.available_models()``.
        mode: ``off`` | ``warn`` | ``strict`` (see module docstring).

    Raises:
        ModelNotAvailableError: When *mode* is ``strict`` and *requested* is a
            non-empty id absent from a non-empty catalogue.

    Returns:
        ``None``. In ``warn`` mode a mismatch is logged (not raised); in ``off``
        mode, or when validation cannot be performed, nothing happens.
    """
    mode = (mode or "warn").lower()
    if mode == "off" or not requested:
        return

    ids = {m.get("id") for m in available_models if isinstance(m, dict) and m.get("id")}
    if not ids:
        # Catalogue not discovered yet (cold start) — nothing to validate against.
        logger.debug(
            f"Model validation skipped for '{requested}': live catalogue not yet known"
        )
        return

    if requested in ids:
        return

    available = sorted(ids)
    if mode == "strict":
        raise ModelNotAvailableError(requested, available)

    # Default 'warn': surface the fallback explicitly instead of swapping models
    # silently. kiro-cli will keep the session default for the unknown id.
    logger.warning(
        f"Requested model '{requested}' is not in the live kiro-cli catalogue "
        f"({', '.join(available)}); falling back to the session default. Set "
        "MODEL_VALIDATION=strict to reject unknown models, or =off to silence."
    )
