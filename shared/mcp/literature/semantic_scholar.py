from __future__ import annotations

from typing import Any, Optional

from shared.core.config import settings
from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class SemanticScholarMCP(BaseMCP):
    """Semantic Scholar Graph API - literature search, paper details, citations, references."""

    name = "semantic_scholar"
    base_url = "https://api.semanticscholar.org/graph/v1"
    requires_api_key = True

    def __init__(self, semaphore: Optional[Any] = None) -> None:
        super().__init__(api_key=settings.semantic_scholar_api_key, semaphore=semaphore)

    def _default_headers(self) -> dict[str, str]:
        h = super()._default_headers()
        if self._api_key:
            h["x-api-key"] = self._api_key
        h.pop("Authorization", None)
        return h

    async def health(self) -> MCPResult:
        return await self._request("GET", "paper/batch", params={"fields": "title"})

    async def search(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        year_range: Optional[str] = None,
        fields: str = "title,authors,year,venue,abstract,externalIds,citationCount,openAccessPdf,fieldsOfStudy",
    ) -> MCPResult:
        params: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 100),
            "offset": offset,
            "fields": fields,
        }
        if year_range:
            params["year"] = year_range
        return await self._request("GET", "paper/search", params=params)

    async def get_paper(self, paper_id: str, fields: str = "title,abstract,authors,year,venue,externalIds,citationCount,referenceCount,openAccessPdf,tldr") -> MCPResult:
        return await self._request("GET", f"paper/{paper_id}", params={"fields": fields})

    async def get_citations(self, paper_id: str, limit: int = 100, offset: int = 0) -> MCPResult:
        return await self._request(
            "GET", f"paper/{paper_id}/citations",
            params={"fields": "title,authors,year,venue,externalIds", "limit": min(limit, 1000), "offset": offset},
        )

    async def get_references(self, paper_id: str, limit: int = 100, offset: int = 0) -> MCPResult:
        return await self._request(
            "GET", f"paper/{paper_id}/references",
            params={"fields": "title,authors,year,venue,externalIds", "limit": min(limit, 1000), "offset": offset},
        )

    async def batch_get_papers(self, paper_ids: list[str], fields: str = "title,abstract,authors,year,venue,externalIds") -> MCPResult:
        return await self._request("POST", "paper/batch", params={"fields": fields}, json_body={"ids": paper_ids})

    async def find_by_doi(self, doi: str) -> MCPResult:
        return await self.get_paper(f"DOI:{doi}")
