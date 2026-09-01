"""P01: GWAS + perturb-seq causal gene mapping.

Independent loop_flow for this sub-project. The divergent Step 6
(s6a_perturb_seq_search) searches scPerturb + GEO + GEARS for perturb-seq
datasets matching GWAS lead-locus genes, then feeds results into the shared
evidence-card extraction (s7).
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


class PerturbSeqSearchInput(SkillInput):
    locus_genes: list[str] = Field(default_factory=list)
    cell_types: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    reading_list: list[dict[str, Any]] = Field(default_factory=list)


class PerturbSeqDatasetHit(BaseModel):
    accession: str = ""
    repository: str = ""
    gene_perturbed: str = ""
    assay: str = ""
    n_cells: Optional[int] = None
    organism: str = ""
    url: str = ""
    description: str = ""


class PerturbSeqSearchOutput(SkillOutput):
    datasets: list[PerturbSeqDatasetHit] = Field(default_factory=list)
    genes_with_perturb_data: list[str] = Field(default_factory=list)
    genes_without_perturb_data: list[str] = Field(default_factory=list)
    gears_models_found: list[str] = Field(default_factory=list)


class PerturbSeqSearchSkill(BaseSkill):
    """Divergent Step 6 for P01: search perturb-seq datasets per locus gene."""

    name = "s6a_perturb_seq_search"
    description = "Search scPerturb + GEO + GEARS for perturb-seq datasets matching GWAS locus genes"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = PerturbSeqSearchInput
    output_schema = PerturbSeqSearchOutput

    async def execute(self, inp: PerturbSeqSearchInput, ctx: SkillContext) -> PerturbSeqSearchOutput:
        reg = ctx.mcp_registry
        params = ctx.archetype_config.get("parameters", {})
        max_genes = int(params.get("perturb_seq_search_max_genes", 30))
        assay_kw = params.get("perturb_seq_assay_keywords", ["perturb-seq", "CRISPRi"])
        genes = inp.locus_genes[:max_genes]

        hits: list[PerturbSeqDatasetHit] = []
        covered: list[str] = []
        uncovered: list[str] = []
        gears_models: list[str] = []

        if not reg:
            return PerturbSeqSearchOutput(
                skill_name=self.name,
                datasets=hits,
                genes_with_perturb_data=covered,
                genes_without_perturb_data=genes,
            )

        scperturb = reg.scperturb()
        geo = reg.geo()
        pwc = reg.papers_with_code()
        github = reg.github()

        for gene in genes:
            found = False
            try:
                resp = await scperturb.search_by_gene(gene)
                if resp.success and resp.data:
                    rows = resp.data if isinstance(resp.data, list) else resp.data.get("datasets", [])
                    for row in rows[:3]:
                        if not isinstance(row, dict):
                            continue
                        hits.append(PerturbSeqDatasetHit(
                            accession=str(row.get("id", row.get("accession", ""))),
                            repository="scPerturb",
                            gene_perturbed=gene,
                            assay=str(row.get("assay", "perturb-seq")),
                            n_cells=row.get("n_cells"),
                            organism=str(row.get("organism", "Homo sapiens")),
                            url=str(row.get("url", "")),
                            description=str(row.get("description", row.get("title", ""))),
                        ))
                        found = True
            except Exception as e:
                self.logger.debug(f"scPerturb search_by_gene({gene}) failed: {e}")

            if not found:
                for kw in assay_kw[:2]:
                    query = f"{gene} {kw}"
                    try:
                        resp = await geo.search_datasets(query, retmax=3)
                        if resp.success and resp.data:
                            idlist = resp.data.get("esearchresult", {}).get("idlist", [])
                            for gse in idlist[:2]:
                                hits.append(PerturbSeqDatasetHit(
                                    accession=gse,
                                    repository="GEO",
                                    gene_perturbed=gene,
                                    assay=kw,
                                    organism="Homo sapiens",
                                    url=f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse}",
                                    description=query,
                                ))
                                found = True
                    except Exception as e:
                        self.logger.debug(f"GEO search({query}) failed: {e}")
                    if found:
                        break

            if found:
                covered.append(gene)
            else:
                uncovered.append(gene)

        if params.get("gears_model_check", True):
            try:
                resp = await pwc.search_methods("GEARS")
                if resp.success and resp.data:
                    for item in resp.data.get("results", [])[:3]:
                        if isinstance(item, dict):
                            gears_models.append(str(item.get("name", item.get("title", ""))))
            except Exception as e:
                self.logger.debug(f"PwC GEARS search failed: {e}")
            try:
                resp = await github.search_repositories("GEARS perturb-seq", per_page=3)
                if resp.success and resp.data:
                    for item in resp.data.get("items", [])[:3]:
                        if isinstance(item, dict):
                            gears_models.append(str(item.get("full_name", "")))
            except Exception as e:
                self.logger.debug(f"GitHub GEARS search failed: {e}")

        self._metrics.update({
            "datasets_found": len(hits),
            "genes_covered": len(covered),
            "genes_uncovered": len(uncovered),
            "gears_models": len(gears_models),
        })
        return PerturbSeqSearchOutput(
            skill_name=self.name,
            datasets=hits,
            genes_with_perturb_data=covered,
            genes_without_perturb_data=uncovered,
            gears_models_found=gears_models,
        )


EXTRA_SKILLS: dict[str, type[BaseSkill]] = {
    "s6a_perturb_seq_search": PerturbSeqSearchSkill,
}


async def run_project(
    global_semaphore: Any = None,
    breakpoint_handler: Any = None,
) -> ProjectResult:
    """Entry point: build and run the P01 orchestrator with project-specific divergent skill."""
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
