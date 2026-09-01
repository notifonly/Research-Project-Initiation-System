from __future__ import annotations

from typing import Any, Optional

from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class ENCODEMCP(BaseMCP):
    """ENCODE REST API - cCRE, ATAC-seq, ChIP-seq dataset search for functional genomics."""

    name = "encode"
    base_url = "https://www.encodeproject.org"
    requires_api_key = False

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "User-Agent": "AIscience/0.1"}

    async def health(self) -> MCPResult:
        return await self._request("GET", "search", params={"type": "Experiment", "limit": 1})

    async def search_experiments(
        self,
        *,
        biosample: Optional[str] = None,
        assay: Optional[str] = None,
        target: Optional[str] = None,
        assembly: Optional[str] = None,
        limit: int = 20,
    ) -> MCPResult:
        params: dict[str, Any] = {"type": "Experiment", "limit": min(limit, 100), "format": "json"}
        if biosample:
            params["biosample_ontology.term_name"] = biosample
        if assay:
            params["assay_title"] = assay
        if target:
            params["target.label"] = target
        if assembly:
            params["assembly"] = assembly
        return await self._request("GET", "search", params=params)

    async def get_experiment(self, accession: str) -> MCPResult:
        return await self._request("GET", f"experiments/{accession}")

    async def search_ccres(self, assembly: str = "GRCh38", biosample: Optional[str] = None, limit: int = 20) -> MCPResult:
        params: dict[str, Any] = {"type": "CandidateCisRegulatoryElement", "assembly": assembly, "limit": min(limit, 100), "format": "json"}
        if biosample:
            params["biosample_ontology.term_name"] = biosample
        return await self._request("GET", "search", params=params)

    async def search_biosamples(self, query: str = "", limit: int = 50) -> MCPResult:
        params: dict[str, Any] = {"type": "Biosample", "limit": min(limit, 100), "format": "json"}
        if query:
            params["biosample_ontology.term_name"] = query
        return await self._request("GET", "search", params=params)


class CellxGeneMCP(BaseMCP):
    """Chan-Zuckerberg CellxGene Census - single-cell dataset catalog (spatial & scRNA)."""

    name = "cellxgene"
    base_url = "https://api.cellxgene.cziscience.com"
    requires_api_key = False

    async def health(self) -> MCPResult:
        return await self._request("GET", "curation/v1/datasets/index")

    async def list_datasets(self) -> MCPResult:
        return await self._request("GET", "curation/v1/datasets/index")

    async def get_dataset(self, dataset_id: str) -> MCPResult:
        return await self._request("GET", f"curation/v1/datasets/{dataset_id}")

    async def search_genes(self, gene_symbol: str) -> MCPResult:
        params: dict[str, Any] = {"gene_symbol": gene_symbol}
        return await self._request("GET", "curation/v1/genes", params=params)

    async def list_cell_types(self) -> MCPResult:
        return await self._request("GET", "curation/v1/cell-types")


class scPerturbMCP(BaseMCP):
    """scPerturb catalog - perturb-seq / CRISPR screen dataset search (P01 specific)."""

    name = "scperturb"
    base_url = "https://api.scperturb.org"
    requires_api_key = False

    async def health(self) -> MCPResult:
        return await self._request("GET", "datasets", params={"limit": 1})

    async def search_datasets(
        self,
        *,
        perturbation: Optional[str] = None,
        gene: Optional[str] = None,
        organism: Optional[str] = None,
        technology: Optional[str] = None,
        limit: int = 20,
    ) -> MCPResult:
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if perturbation:
            params["perturbation"] = perturbation
        if gene:
            params["gene"] = gene
        if organism:
            params["organism"] = organism
        if technology:
            params["technology"] = technology
        return await self._request("GET", "datasets", params=params)

    async def get_dataset(self, dataset_id: str) -> MCPResult:
        return await self._request("GET", f"datasets/{dataset_id}")

    async def search_by_gene(self, gene_symbol: str) -> MCPResult:
        return await self.search_datasets(gene=gene_symbol)
