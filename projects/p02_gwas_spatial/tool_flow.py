"""P02: GWAS + spatial transcriptomics V2G.

Independent loop_flow. Divergent Step 6 (s6a_spatial_dataset_search) searches
CellxGene + GEO for spatial transcriptomics datasets (Visium, Slide-seq,
Stereo-seq, MERFISH) matching GWAS lead-locus genes and trait-relevant tissues.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from shared.core.orchestrator import Orchestrator, ProjectResult
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.yaml"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class SpatialSearchInput(SkillInput):
    locus_genes: list[str] = Field(default_factory=list)
    cell_types: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    tissues: list[str] = Field(default_factory=list)


class SpatialDatasetHit(BaseModel):
    accession: str = ""
    repository: str = ""
    gene: str = ""
    tissue: str = ""
    assay: str = ""
    technology: str = ""
    organism: str = ""
    url: str = ""
    description: str = ""


class SpatialSearchOutput(SkillOutput):
    datasets: list[SpatialDatasetHit] = Field(default_factory=list)
    genes_with_spatial_data: list[str] = Field(default_factory=list)
    genes_without_spatial_data: list[str] = Field(default_factory=list)
    tissues_covered: list[str] = Field(default_factory=list)


class SpatialDatasetSearchSkill(BaseSkill):
    """Divergent Step 6 for P02: search spatial transcriptomics datasets per locus gene / tissue."""

    name = "s6a_spatial_dataset_search"
    description = "Search CellxGene + GEO for spatial transcriptomics datasets matching GWAS locus genes & tissues"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = SpatialSearchInput
    output_schema = SpatialSearchOutput

    async def execute(self, inp: SpatialSearchInput, ctx: SkillContext) -> SpatialSearchOutput:
        reg = ctx.mcp_registry
        params = ctx.archetype_config.get("parameters", {})
        max_genes = int(params.get("spatial_search_max_genes", 30))
        assay_kw = params.get("spatial_assay_keywords", ["spatial transcriptomics", "Visium"])
        tissue_priority = params.get("spatial_tissue_priority", [])
        genes = inp.locus_genes[:max_genes]
        tissues = inp.tissues or tissue_priority or ["brain"]

        hits: list[SpatialDatasetHit] = []
        covered: list[str] = []
        uncovered: list[str] = []
        tissues_covered: set[str] = set()

        if not reg:
            return SpatialSearchOutput(
                skill_name=self.name,
                datasets=hits,
                genes_with_spatial_data=covered,
                genes_without_spatial_data=genes,
            )

        cxg = reg.cellxgene()
        geo = reg.geo()

        try:
            ds_resp = await cxg.list_datasets()
            cxg_rows: list[dict[str, Any]] = []
            if ds_resp.success and ds_resp.data:
                cxg_rows = ds_resp.data if isinstance(ds_resp.data, list) else ds_resp.data.get("datasets", [])
            for row in cxg_rows[:20]:
                if not isinstance(row, dict):
                    continue
                tech = str(row.get("technology", row.get("assay", ""))).lower()
                if "spatial" not in tech and "visium" not in tech and "slide" not in tech:
                    continue
                tissue = str(row.get("tissue", row.get("tissue_general", "")))
                tissues_covered.add(tissue)
                hits.append(SpatialDatasetHit(
                    accession=str(row.get("dataset_id", row.get("id", ""))),
                    repository="CellxGene",
                    tissue=tissue,
                    assay="spatial transcriptomics",
                    technology=str(row.get("technology", "")),
                    organism=str(row.get("organism", "Homo sapiens")),
                    url=str(row.get("url", "")),
                    description=str(row.get("title", row.get("name", ""))),
                ))
        except Exception as e:
            self.logger.debug(f"CellxGene list_datasets failed: {e}")

        for gene in genes:
            found = bool(any(h.gene == gene for h in hits))
            if not found:
                for tissue in tissues[:3]:
                    for kw in assay_kw[:2]:
                        query = f"{gene} {kw} {tissue}"
                        try:
                            resp = await geo.search_datasets(query, retmax=3)
                            if resp.success and resp.data:
                                idlist = resp.data.get("esearchresult", {}).get("idlist", [])
                                for gse in idlist[:2]:
                                    hits.append(SpatialDatasetHit(
                                        accession=gse,
                                        repository="GEO",
                                        gene=gene,
                                        tissue=tissue,
                                        assay=kw,
                                        technology=kw,
                                        organism="Homo sapiens",
                                        url=f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse}",
                                        description=query,
                                    ))
                                    found = True
                                    tissues_covered.add(tissue)
                        except Exception as e:
                            self.logger.debug(f"GEO search({query}) failed: {e}")
                        if found:
                            break
                    if found:
                        break
            if found:
                covered.append(gene)
            else:
                uncovered.append(gene)

        self._metrics.update({
            "datasets_found": len(hits),
            "genes_covered": len(covered),
            "genes_uncovered": len(uncovered),
            "tissues_covered": len(tissues_covered),
        })
        return SpatialSearchOutput(
            skill_name=self.name,
            datasets=hits,
            genes_with_spatial_data=covered,
            genes_without_spatial_data=uncovered,
            tissues_covered=sorted(tissues_covered),
        )


EXTRA_SKILLS: dict[str, type[BaseSkill]] = {
    "s6a_spatial_dataset_search": SpatialDatasetSearchSkill,
}


async def run_project(
    global_semaphore: Any = None,
    breakpoint_handler: Any = None,
) -> ProjectResult:
    cfg = load_config()
    orch = Orchestrator(
        project_id=cfg["project_id"],
        project_dir=PROJECT_DIR,
        archetype_id=cfg["archetype_id"],
        research_direction=cfg["research_direction"],
        global_semaphore=global_semaphore,
        breakpoint_handler=breakpoint_handler,
        project_config=cfg,
        extra_skills=EXTRA_SKILLS,
    )
    return await orch.run()
