from __future__ import annotations

from typing import Any, Optional

from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class GEOMCP(BaseMCP):
    """NCBI GEO (Gene Expression Omnibus) - dataset and series search for raw data availability."""

    name = "geo"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    requires_api_key = False

    async def health(self) -> MCPResult:
        return await self._request("GET", "esearch.fcgi", params={"db": "gds", "term": "test", "retmax": 1, "retmode": "json"})

    async def search_datasets(
        self,
        query: str,
        *,
        retmax: int = 20,
        retstart: int = 0,
    ) -> MCPResult:
        params: dict[str, Any] = {
            "db": "gds",
            "term": f"{query} AND (\"gse\"[Entry Type] OR \"gds\"[Entry Type])",
            "retmax": retmax,
            "retstart": retstart,
            "retmode": "json",
        }
        return await self._request("GET", "esearch.fcgi", params=params)

    async def fetch_summaries(self, ids: list[str]) -> MCPResult:
        params: dict[str, Any] = {"db": "gds", "id": ",".join(ids), "retmode": "json"}
        return await self._request("GET", "esummary.fcgi", params=params)

    async def search_by_organism_and_platform(self, organism: str, platform: Optional[str] = None, retmax: int = 20) -> MCPResult:
        query = f"{organism}[Organism]"
        if platform:
            query += f" AND {platform}[Platform]"
        return await self.search_datasets(query, retmax=retmax)

    async def get_gse_summary(self, gse_id: str) -> MCPResult:
        return await self.fetch_summaries([gse_id])
