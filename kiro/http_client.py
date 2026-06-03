"""Thin wrapper around httpx.AsyncClient with retry logic."""
from __future__ import annotations
import asyncio
from typing import Any, Optional

import httpx


class KiroHttpClient:
    """Shared or per-request HTTP client.

    Pass ``shared_client=None`` for a fresh per-request client (streaming).
    Pass a live ``httpx.AsyncClient`` for connection-pool reuse (non-streaming).
    """

    def __init__(
        self,
        *,
        shared_client: Optional[httpx.AsyncClient] = None,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self._shared = shared_client
        self._owned: Optional[httpx.AsyncClient] = None
        self._timeout = timeout
        self._max_retries = max_retries

    async def _client(self) -> httpx.AsyncClient:
        if self._shared is not None:
            return self._shared
        if self._owned is None:
            self._owned = httpx.AsyncClient(timeout=self._timeout)
        return self._owned

    async def request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        client = await self._client()
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                return await client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    async def close(self) -> None:
        if self._owned is not None:
            await self._owned.aclose()
            self._owned = None
