from __future__ import annotations

from typing import Optional

from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class COREMCP(BaseMCP):
    """CORE API v3 - OA repository aggregator for full-text download."""

    name = "core"
    base_url = "https://api.core.ac.uk/v3"
    requires_api_key = True

    def __init__(self, api_key: Optional[str] = None, semaphore=None) -> None:
        from shared.core.config import settings
        super().__init__(api_key or settings.core_api_key, semaphore)

    async def search(self, query: str, *, limit: int = 20) -> MCPResult:
        params = {"q": query, "limit": limit}
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        return await self._request("GET", "search", params=params, headers=headers)

    async def download_pdf(self, core_id: str) -> MCPResult:
        url = f"https://api.core.ac.uk/v3/outputs/{core_id}/download"
        return await self._request_raw(url)

    async def health(self) -> MCPResult:
        return await self.search("test", limit=1)
