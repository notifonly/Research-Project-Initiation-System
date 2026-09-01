from __future__ import annotations


from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class ArxivMCP(BaseMCP):
    """arXiv API - preprint search via OAI-PMH/export interface."""

    name = "arxiv"
    base_url = "https://export.arxiv.org/api"
    requires_api_key = False

    async def search(self, query: str, *, limit: int = 20, offset: int = 0) -> MCPResult:
        params = {"search_query": f"all:{query}", "start": offset, "max_results": min(limit, 100)}
        return await self._request("GET", "query", params=params)

    async def search_by_id(self, arxiv_id: str) -> MCPResult:
        return await self._request("GET", f"query?id_list={arxiv_id}")

    async def download_pdf(self, arxiv_id: str) -> MCPResult:
        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        return await self._request_raw(url)

    async def health(self) -> MCPResult:
        return await self.search("test", limit=1)
