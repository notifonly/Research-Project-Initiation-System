from __future__ import annotations

from typing import Any, Optional

from shared.core.config import settings
from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class PubMedMCP(BaseMCP):
    """NCBI PubMed E-utilities - literature search via esearch + efetch + esummary."""

    name = "pubmed"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    requires_api_key = False

    def __init__(self, semaphore: Optional[Any] = None) -> None:
        super().__init__(api_key=settings.ncbi_api_key, semaphore=semaphore)

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "User-Agent": "AIscience/0.1"}

    def _common_params(self) -> dict[str, Any]:
        p: dict[str, Any] = {"retmode": "json"}
        if settings.ncbi_api_key:
            p["api_key"] = settings.ncbi_api_key
        if settings.gwas_catalog_email:
            p["email"] = settings.gwas_catalog_email
        return p

    async def health(self) -> MCPResult:
        params = self._common_params()
        params["db"] = "pubmed"
        params["term"] = "test"
        params["retmax"] = 1
        return await self._request("GET", "esearch.fcgi", params=params)

    async def search(
        self,
        query: str,
        *,
        retmax: int = 20,
        retstart: int = 0,
        sort: str = "relevance",
        date_range: Optional[str] = None,
    ) -> MCPResult:
        params = self._common_params()
        params.update({"db": "pubmed", "term": query, "retmax": retmax, "retstart": retstart, "sort": sort})
        if date_range:
            params["datetype"] = "pdat"
            params["reldate"] = date_range
        return await self._request("GET", "esearch.fcgi", params=params)

    async def fetch_summaries(self, pmids: list[str]) -> MCPResult:
        params = self._common_params()
        params.update({"db": "pubmed", "id": ",".join(pmids)})
        return await self._request("GET", "esummary.fcgi", params=params)

    async def fetch_abstracts(self, pmids: list[str]) -> MCPResult:
        params = self._common_params()
        params.update({"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "text"})
        return await self._request("GET", "efetch.fcgi", params=params)

    async def fetch_full_records(self, pmids: list[str]) -> MCPResult:
        params = self._common_params()
        params.update({"db": "pubmed", "id": ",".join(pmids), "rettype": "medline", "retmode": "text"})
        return await self._request("GET", "efetch.fcgi", params=params)
