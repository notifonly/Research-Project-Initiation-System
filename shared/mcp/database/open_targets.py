from __future__ import annotations

from typing import Any, Optional

from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class OpenTargetsGeneticsMCP(BaseMCP):
    """Open Targets Genetics Platform API - locus-to-gene, colocalization, GWAS study info."""

    name = "open_targets_genetics"
    base_url = "https://api.genetics.opentargets.org/graphql"
    requires_api_key = False

    async def health(self) -> MCPResult:
        query = {"query": "{ __typename }"}
        return await self._request("POST", "", json_body=query)

    async def _gql(self, query: str, variables: Optional[dict] = None) -> MCPResult:
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        return await self._request("POST", "", json_body=body)

    async def search_studies(self, query_str: str, size: int = 20) -> MCPResult:
        q = """
        query($q: String!, $size: Int!) {
          studies(queryString: $q, size: $size) {
            total hits { id studyId traitReported traitCategory nSamples nCases nControls }
          }
        }
        """
        return await self._gql(q, {"q": query_str, "size": size})

    async def locus_to_gene(self, study_id: str, variant_id: str, page_size: int = 20) -> MCPResult:
        q = """
        query($studyId: String!, $variantId: String!, $pageSize: Int!) {
          locusToGene(studyId: $studyId, variantId: $variantId, pageSize: $pageSize) {
            total rows {
              gene { id symbol } variant { id rsId chromosome position } yProbaModel l2gScore
            }
          }
        }
        """
        return await self._gql(q, {"studyId": study_id, "variantId": variant_id, "pageSize": page_size})

    async def colocalization(self, study_id: str, variant_id: str) -> MCPResult:
        q = """
        query($studyId: String!, $variantId: String!) {
          colocalisation(studyId: $studyId, variantId: $variantId) {
            total colocalisations {
              leftVariant rightVariant leftStudy rightStudy h3 h4 qtlStudyId phenotype
            }
          }
        }
        """
        return await self._gql(q, {"studyId": study_id, "variantId": variant_id})

    async def study_info(self, study_id: str) -> MCPResult:
        q = """
        query($studyId: String!) {
          studyInfo(studyId: $studyId) {
            studyId traitReported traitCategory nSamples nCases nControls pubAuthor pubDate pubJournal
          }
        }
        """
        return await self._gql(q, {"studyId": study_id})

    async def search_by_gene(self, gene_symbol: str, size: int = 20) -> MCPResult:
        q = """
        query($gene: String!, $size: Int!) {
          gene(gene_symbol: $gene) { id symbol studies(size: $size) { total hits { studyId traitReported nSamples } }
          }
        }
        """
        return await self._gql(q, {"gene": gene_symbol, "size": size})
