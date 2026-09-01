"""P03: GWAS + scATAC-seq regulatory V2G.

Independent loop_flow. Divergent Step 6 (s6a_scatac_dataset_search) searches
ENCODE cCRE + scATAC-seq experiments + ChromBPNet model resources (GitHub /
HuggingFace) matching GWAS lead-locus regulatory regions and cell types.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


class ScATACSearchInput(SkillInput):
    locus_genes: list[str] = Field(default_factory=list)
    cell_types: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    genomic_positions: list[dict[str, Any]] = Field(default_factory=list)


class ScATACDatasetHit(BaseModel):
    accession: str = ""
    repository: str = ""
    gene: str = ""
    cell_type: str = ""
    assay: str = ""
    assembly: str = "GRCh38"
    url: str = ""
    description: str = ""


class ScATACSearchOutput(SkillOutput):
    datasets: list[ScATACDatasetHit] = Field(default_factory=list)
    ccres_found: int = 0
    genes_with_accessibility_data: list[str] = Field(default_factory=list)
    genes_without_accessibility_data: list[str] = Field(default_factory=list)
    chrombpnet_models_found: list[str] = Field(default_factory=list)


class ScATACDatasetSearchSkill(BaseSkill):
    """Divergent Step 6 for P03: search ENCODE cCRE + scATAC + ChromBPNet resources."""

    name = "s6a_scatac_dataset_search"
    description = "Search ENCODE cCRE + scATAC-seq + ChromBPNet models matching GWAS locus regions & cell types"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = ScATACSearchInput
    output_schema = ScATACSearchOutput

    async def execute(self, inp: ScATACSearchInput, ctx: SkillContext) -> ScATACSearchOutput:
        reg = ctx.mcp_registry
        params = ctx.archetype_config.get("parameters", {})
        max_regions = int(params.get("scatac_search_max_regions", 30))
        genes = inp.locus_genes[:max_regions]
        cell_types = inp.cell_types[:10] or ["K562", "GM12878"]

        hits: list[ScATACDatasetHit] = []
        covered: list[str] = []
        uncovered: list[str] = []
        ccres_found = 0
        cbp_models: list[str] = []

        if not reg:
            return ScATACSearchOutput(
                skill_name=self.name,
                datasets=hits,
                genes_without_accessibility_data=genes,
            )

        encode = reg.encode()
        geo = reg.geo()
        github = reg.github()
        hf = reg.huggingface()

        for ct in cell_types[:5]:
            try:
                resp = await encode.search_ccres(assembly="GRCh38", biosample=ct, limit=10)
                if resp.success and resp.data:
                    rows = resp.data.get("@graph", resp.data if isinstance(resp.data, list) else [])
                    if isinstance(rows, list):
                        ccres_found += len(rows)
                        for row in rows[:3]:
                            if not isinstance(row, dict):
                                continue
                            hits.append(ScATACDatasetHit(
                                accession=str(row.get("accession", "")),
                                repository="ENCODE-cCRE",
                                cell_type=ct,
                                assay="cCRE",
                                url=str(row.get("url", "")),
                                description=str(row.get("description", "")),
                            ))
            except Exception as e:
                self.logger.debug(f"ENCODE search_ccres({ct}) failed: {e}")

            try:
                resp = await encode.search_experiments(biosample=ct, assay="ATAC-seq", limit=10)
                if resp.success and resp.data:
                    rows = resp.data.get("@graph", resp.data if isinstance(resp.data, list) else [])
                    if isinstance(rows, list):
                        for row in rows[:3]:
                            if not isinstance(row, dict):
                                continue
                            hits.append(ScATACDatasetHit(
                                accession=str(row.get("accession", "")),
                                repository="ENCODE-ATAC",
                                cell_type=ct,
                                assay="scATAC-seq",
                                url=str(row.get("url", "")),
                                description=str(row.get("description", row.get("assay_title", ""))),
                            ))
            except Exception as e:
                self.logger.debug(f"ENCODE search_experiments({ct}) failed: {e}")

        for gene in genes:
            found = bool(any(h.gene == gene for h in hits))
            if not found:
                query = f"{gene} scATAC-seq"
                try:
                    resp = await geo.search_datasets(query, retmax=3)
                    if resp.success and resp.data:
                        idlist = resp.data.get("esearchresult", {}).get("idlist", [])
                        for gse in idlist[:2]:
                            hits.append(ScATACDatasetHit(
                                accession=gse,
                                repository="GEO",
                                gene=gene,
                                assay="scATAC-seq",
                                url=f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse}",
                                description=query,
                            ))
                            found = True
                except Exception as e:
                    self.logger.debug(f"GEO search({query}) failed: {e}")
            if found:
                covered.append(gene)
            else:
                uncovered.append(gene)

        if params.get("chrombpnet_model_check", True):
            for q in ("ChromBPNet", "chrombpnet"):
                try:
                    resp = await github.search_repositories(q, per_page=3)
                    if resp.success and resp.data:
                        for item in resp.data.get("items", [])[:3]:
                            if isinstance(item, dict):
                                cbp_models.append(str(item.get("full_name", "")))
                except Exception as e:
                    self.logger.debug(f"GitHub search({q}) failed: {e}")
                try:
                    resp = await hf.search_models(q, limit=3)
                    if resp.success and resp.data:
                        for item in (resp.data if isinstance(resp.data, list) else [])[:3]:
                            if isinstance(item, dict):
                                cbp_models.append(str(item.get("id", item.get("modelId", ""))))
                except Exception as e:
                    self.logger.debug(f"HF search({q}) failed: {e}")

        self._metrics.update({
            "datasets_found": len(hits),
            "ccres_found": ccres_found,
            "genes_covered": len(covered),
            "genes_uncovered": len(uncovered),
            "chrombpnet_models": len(cbp_models),
        })
        return ScATACSearchOutput(
            skill_name=self.name,
            datasets=hits,
            ccres_found=ccres_found,
            genes_with_accessibility_data=covered,
            genes_without_accessibility_data=uncovered,
            chrombpnet_models_found=cbp_models,
        )


EXTRA_SKILLS: dict[str, type[BaseSkill]] = {
    "s6a_scatac_dataset_search": ScATACDatasetSearchSkill,
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
