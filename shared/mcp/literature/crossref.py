from __future__ import annotations


from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class CrossrefMCP(BaseMCP):
    """Crossref REST API - metadata search & DOI resolution with OA link discovery."""

    name = "crossref"
    base_url = "https://api.crossref.org"
    requires_api_key = False

    async def search(self, query: str, *, limit: int = 20, offset: int = 0) -> MCPResult:
        params = {"query": query, "rows": limit, "offset": offset}
        return await self._request("GET", "works", params=params)

    async def resolve_doi(self, doi: str) -> MCPResult:
        return await self._request("GET", f"works/{doi}")

    async def health(self) -> MCPResult:
        return await self.search("test", limit=1)
