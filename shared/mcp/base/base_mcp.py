from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from shared.core.config import settings
from shared.core.logging_setup import get_logger

_logger = get_logger("mcp.base")


@dataclass
class MCPResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    source: str = ""
    raw_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseMCP(ABC):
    """Base class for all MCP tool servers. Each MCP defines its own methods."""

    name: str = "base"
    base_url: str = ""
    requires_api_key: bool = False

    def __init__(self, api_key: Optional[str] = None, semaphore: Optional[asyncio.Semaphore] = None) -> None:
        self._api_key = api_key
        self._semaphore = semaphore or asyncio.Semaphore(settings.mcp_concurrency)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = self._default_headers()
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=settings.request_timeout,
            )
        return self._client

    def _default_headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "User-Agent": "AIscience/0.1"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def _request_raw(self, url: str) -> MCPResult:
        """Download binary content (e.g. PDF) from a URL. Returns bytes in data."""
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=settings.request_timeout, follow_redirects=True) as client:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    content = resp.content
                    if b"%PDF" in content[:8]:
                        return MCPResult(success=True, data=content, source=self.name)
                    content_type = resp.headers.get("content-type", "")
                    _logger.warning(f"Unexpected content-type for PDF download: {content_type}")
                    return MCPResult(success=False, error=f"Not a PDF: content_type={content_type}", source=self.name)
                except Exception as e:
                    return MCPResult(success=False, error=str(e), source=self.name)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> MCPResult:
        async with self._semaphore:
            client = await self._get_client()
            try:
                resp = await client.request(method, url, params=params, json=json_body, headers=headers)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text
                return MCPResult(success=True, data=data, source=self.name, raw_count=self._count(data))
            except httpx.HTTPStatusError as e:
                return MCPResult(success=False, error=f"HTTP {e.response.status_code}: {e}", source=self.name)
            except Exception as e:
                return MCPResult(success=False, error=str(e), source=self.name)

    def _count(self, data: Any) -> int:
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            for k in ("total", "count", "results", "data", "hits"):
                v = data.get(k)
                if isinstance(v, int):
                    return v
                if isinstance(v, list):
                    return len(v)
        return 1

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abstractmethod
    async def health(self) -> MCPResult:
        """Check if the MCP service is reachable."""
        ...
