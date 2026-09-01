from __future__ import annotations


from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class EuropePMCMCP(BaseMCP):
    """Europe PMC REST API - full-text search & OA PDF download."""

    name = "europe_pmc"
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    requires_api_key = False

    async def search(self, query: str, *, limit: int = 20) -> MCPResult:
        params = {"query": query, "pageSize": limit, "format": "json", "resultType": "core"}
        return await self._request("GET", "search", params=params)

    async def download_pdf(self, pmcid: str) -> MCPResult:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextPDF"
        return await self._request_raw(url)

    async def health(self) -> MCPResult:
        return await self.search("test", limit=1)
