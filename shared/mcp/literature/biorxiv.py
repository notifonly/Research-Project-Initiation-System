from __future__ import annotations

from typing import Any

from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class BioRxivMCP(BaseMCP):
    """bioRxiv/medRxiv API - preprint search for latest unpublished findings."""

    name = "biorxiv"
    base_url = "https://api.biorxiv.org/details"
    requires_api_key = False

    async def health(self) -> MCPResult:
        return await self._request("GET", "biorxiv/2024/2024-01-01/2024-01-02/0")

    async def search_by_date_range(self, server: str, from_date: str, to_date: str, cursor: int = 0) -> MCPResult:
        server = server if server in ("biorxiv", "medrxiv") else "biorxiv"
        return await self._request("GET", f"{server}/{from_date}/{to_date}/{cursor}")

    async def search_by_doi(self, doi: str) -> MCPResult:
        server = "biorxiv" if "biorxiv" in doi.lower() else "medrxiv"
        return await self._request("GET", f"{server}/{doi}")

    async def search_by_query(self, query: str, limit: int = 20) -> MCPResult:
        """Search bioRxiv/medRxiv content by keyword via content-detail API."""
        params = {"query": query, "format": "json", "limit": limit}
        return await self._request("GET", "content/biorxiv", params=params)

    async def get_details_by_interval(self, server: str, interval: str, cursor: int = 0) -> MCPResult:
        server = server if server in ("biorxiv", "medrxiv") else "biorxiv"
        return await self._request("GET", f"{server}/{interval}/{cursor}")


class OpenReviewMCP(BaseMCP):
    """OpenReview API - ML/AI conference paper search (NeurIPS, ICML, ICLR workshops)."""

    name = "openreview"
    base_url = "https://api2.openreview.net"
    requires_api_key = False

    async def health(self) -> MCPResult:
        return await self._request("GET", "venues")

    async def search_notes(self, content_query: str, limit: int = 20, offset: int = 0) -> MCPResult:
        params: dict[str, Any] = {
            "content": content_query,
            "limit": limit,
            "offset": offset,
        }
        return await self._request("GET", "notes/search", params=params)

    async def get_notes_by_invitation(self, invitation: str, limit: int = 100, offset: int = 0) -> MCPResult:
        params = {"invitation": invitation, "limit": limit, "offset": offset}
        return await self._request("GET", "notes", params=params)

    async def get_venues(self) -> MCPResult:
        return await self._request("GET", "venues")

    async def get_venue_info(self, venue_id: str) -> MCPResult:
        return await self._request("GET", f"venues/{venue_id}")
