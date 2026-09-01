from __future__ import annotations


from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class PMCMCP(BaseMCP):
    """PubMed Central MCP - search & download OA full-text articles."""

    name = "pmc"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    requires_api_key = False

    async def search(self, query: str, *, limit: int = 20) -> MCPResult:
        params = {"term": query, "retmax": limit, "retmode": "json", "db": "pmc"}
        return await self._request("GET", "esearch.fcgi", params=params)

    async def download_pdf(self, pmcid: str) -> MCPResult:
        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
        return await self._request_raw(url)

    async def health(self) -> MCPResult:
        return await self.search("test", limit=1)
