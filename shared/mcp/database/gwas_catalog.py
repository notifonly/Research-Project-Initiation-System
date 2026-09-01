from __future__ import annotations

from typing import Any, Optional

from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class GWASCatalogMCP(BaseMCP):
    """GWAS Catalog REST API - associations, studies, traits, regions for V2G evidence."""

    name = "gwas_catalog"
    base_url = "https://www.ebi.ac.uk/gwas/rest/api"
    requires_api_key = False

    def __init__(self, semaphore: Optional[Any] = None) -> None:
        super().__init__(api_key=None, semaphore=semaphore)

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "User-Agent": "AIscience/0.1"}

    async def health(self) -> MCPResult:
        return await self._request("GET", "efoTraits", params={"size": 1})

    async def search_associations(
        self,
        *,
        rsid: Optional[str] = None,
        gene: Optional[str] = None,
        trait: Optional[str] = None,
        efo: Optional[str] = None,
        chrom: Optional[str] = None,
        bp_start: Optional[int] = None,
        bp_end: Optional[int] = None,
        p_value_max: Optional[float] = None,
        size: int = 20,
    ) -> MCPResult:
        params: dict[str, Any] = {"size": min(size, 1000)}
        if rsid:
            params["variantId"] = rsid
        if gene:
            params["gene"] = gene
        if trait:
            params["trait"] = trait
        if efo:
            params["efoTrait"] = efo
        if chrom and bp_start is not None and bp_end is not None:
            params["chromosomeLocation"] = f"{chrom}:{bp_start}-{bp_end}"
        if p_value_max is not None:
            params["pValueMax"] = p_value_max
        return await self._request("GET", "associations", params=params)

    async def get_association(self, association_id: str) -> MCPResult:
        return await self._request("GET", f"associations/{association_id}")

    async def search_studies(self, *, trait: Optional[str] = None, gene: Optional[str] = None, size: int = 20) -> MCPResult:
        params: dict[str, Any] = {"size": min(size, 1000)}
        if trait:
            params["diseaseTrait"] = trait
        if gene:
            params["gene"] = gene
        return await self._request("GET", "studies", params=params)

    async def get_study(self, study_id: str) -> MCPResult:
        return await self._request("GET", f"studies/{study_id}")

    async def search_efo_traits(self, query: str, size: int = 20) -> MCPResult:
        return await self._request("GET", "efoTraits/search", params={"q": query, "size": size})

    async def search_by_gene(self, gene: str, size: int = 100) -> MCPResult:
        return await self.search_associations(gene=gene, size=size)

    async def search_by_region(self, chrom: str, bp_start: int, bp_end: int, size: int = 100) -> MCPResult:
        return await self.search_associations(chrom=chrom, bp_start=bp_start, bp_end=bp_end, size=size)
