from __future__ import annotations

import asyncio
from typing import Optional

from shared.core.config import settings
from shared.core.logging_setup import get_logger
from shared.mcp.base.base_mcp import BaseMCP, MCPResult
from shared.mcp.code_tool.github import GitHubMCP, HuggingFaceMCP, PapersWithCodeMCP
from shared.mcp.database.encode import ENCODEMCP, CellxGeneMCP, scPerturbMCP
from shared.mcp.database.ensembl import EnsemblMCP
from shared.mcp.database.geo import GEOMCP
from shared.mcp.database.gwas_catalog import GWASCatalogMCP
from shared.mcp.database.open_targets import OpenTargetsGeneticsMCP
from shared.mcp.literature.arxiv import ArxivMCP
from shared.mcp.literature.biorxiv import BioRxivMCP, OpenReviewMCP
from shared.mcp.literature.core import COREMCP
from shared.mcp.literature.crossref import CrossrefMCP
from shared.mcp.literature.europe_pmc import EuropePMCMCP
from shared.mcp.literature.pmc import PMCMCP
from shared.mcp.literature.pubmed import PubMedMCP
from shared.mcp.literature.semantic_scholar import SemanticScholarMCP

logger = get_logger()


class MCPRegistry:
    """Central registry for all MCP tool instances. One per project, sharing global semaphore."""

    def __init__(self, project_id: str, semaphore: Optional[asyncio.Semaphore] = None) -> None:
        self.project_id = project_id
        self._semaphore = semaphore or asyncio.Semaphore(settings.mcp_concurrency)
        self._mcps: dict[str, BaseMCP] = {}
        self._init_all()

    def _init_all(self) -> None:
        registry: list[type[BaseMCP]] = [
            SemanticScholarMCP,
            PubMedMCP,
            GWASCatalogMCP,
            OpenTargetsGeneticsMCP,
            GEOMCP,
            EnsemblMCP,
            BioRxivMCP,
            OpenReviewMCP,
            GitHubMCP,
            PapersWithCodeMCP,
            HuggingFaceMCP,
            ENCODEMCP,
            CellxGeneMCP,
            scPerturbMCP,
            ArxivMCP,
            PMCMCP,
            CrossrefMCP,
            EuropePMCMCP,
            COREMCP,
        ]
        for cls in registry:
            try:
                instance = cls(semaphore=self._semaphore)
                self._mcps[instance.name] = instance
            except Exception as e:
                logger.warning(f"Failed to init MCP {cls.__name__}: {e}")

    def get(self, name: str) -> Optional[BaseMCP]:
        return self._mcps.get(name)

    def semantic_scholar(self) -> SemanticScholarMCP:
        return self._mcps["semantic_scholar"]  # type: ignore[return-value]

    def pubmed(self) -> PubMedMCP:
        return self._mcps["pubmed"]  # type: ignore[return-value]

    def gwas_catalog(self) -> GWASCatalogMCP:
        return self._mcps["gwas_catalog"]  # type: ignore[return-value]

    def open_targets(self) -> OpenTargetsGeneticsMCP:
        return self._mcps["open_targets_genetics"]  # type: ignore[return-value]

    def geo(self) -> GEOMCP:
        return self._mcps["geo"]  # type: ignore[return-value]

    def ensembl(self) -> EnsemblMCP:
        return self._mcps["ensembl"]  # type: ignore[return-value]

    def biorxiv(self) -> BioRxivMCP:
        return self._mcps["biorxiv"]  # type: ignore[return-value]

    def openreview(self) -> OpenReviewMCP:
        return self._mcps["openreview"]  # type: ignore[return-value]

    def github(self) -> GitHubMCP:
        return self._mcps["github"]  # type: ignore[return-value]

    def papers_with_code(self) -> PapersWithCodeMCP:
        return self._mcps["papers_with_code"]  # type: ignore[return-value]

    def huggingface(self) -> HuggingFaceMCP:
        return self._mcps["huggingface"]  # type: ignore[return-value]

    def encode(self) -> ENCODEMCP:
        return self._mcps["encode"]  # type: ignore[return-value]

    def cellxgene(self) -> CellxGeneMCP:
        return self._mcps["cellxgene"]  # type: ignore[return-value]

    def scperturb(self) -> scPerturbMCP:
        return self._mcps["scperturb"]  # type: ignore[return-value]

    def arxiv(self) -> ArxivMCP:
        return self._mcps["arxiv"]  # type: ignore[return-value]

    def pmc(self) -> PMCMCP:
        return self._mcps["pmc"]  # type: ignore[return-value]

    def crossref(self) -> CrossrefMCP:
        return self._mcps["crossref"]  # type: ignore[return-value]

    def europe_pmc(self) -> EuropePMCMCP:
        return self._mcps["europe_pmc"]  # type: ignore[return-value]

    def core(self) -> COREMCP:
        return self._mcps["core"]  # type: ignore[return-value]

    async def health_check_all(self) -> dict[str, MCPResult]:
        results: dict[str, MCPResult] = {}
        tasks = {name: mcp.health() for name, mcp in self._mcps.items()}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                results[name] = MCPResult(success=False, error=str(e), source=name)
        return results

    async def aclose_all(self) -> None:
        for mcp in self._mcps.values():
            try:
                await mcp.aclose()
            except Exception:
                pass

    def names(self) -> list[str]:
        return list(self._mcps.keys())
