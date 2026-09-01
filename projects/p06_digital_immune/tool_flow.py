"""P06: Digital immune phenotype scoring.

Archetype D (Multi-omics phenotypic scoring). Divergent Step 6
(s6a_immune_dataset_search) searches GEO + CellxGene + PapersWithCode for
immune cell datasets and immune-score method implementations.
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


class ImmuneDatasetSearchInput(SkillInput):
    key_terms: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    cell_types: list[str] = Field(default_factory=list)
    reading_list: list[dict[str, Any]] = Field(default_factory=list)


class ImmuneDatasetHit(BaseModel):
    accession: str = ""
    repository: str = ""
    cell_type: str = ""
    omics_layer: str = ""
    assay: str = ""
    n_samples: int = 0
    url: str = ""
    description: str = ""


class ImmuneDatasetSearchOutput(SkillOutput):
    datasets: list[ImmuneDatasetHit] = Field(default_factory=list)
    score_methods: list[str] = Field(default_factory=list)
    cell_types_covered: list[str] = Field(default_factory=list)


class ImmuneDatasetSearchSkill(BaseSkill):
    """Divergent Step 6 for P06: search immune cell datasets & immune-score methods."""

    name = "s6a_immune_dataset_search"
    description = "Search GEO + CellxGene + PapersWithCode for immune cell datasets & immune-score methods"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = ImmuneDatasetSearchInput
    output_schema = ImmuneDatasetSearchOutput

    async def execute(self, inp: ImmuneDatasetSearchInput, ctx: SkillContext) -> ImmuneDatasetSearchOutput:
        reg = ctx.mcp_registry
        params = ctx.archetype_config.get("parameters", {})
        omics_layers = params.get("omics_layers_of_interest", ["flow_cytometry", "CyTOF", "transcriptome"])
        cell_types = inp.cell_types or params.get("immune_cell_types", ["CD4_T", "CD8_T", "B_cell"])

        hits: list[ImmuneDatasetHit] = []
        score_methods: list[str] = []
        cells_covered: set[str] = set()

        if not reg:
            return ImmuneDatasetSearchOutput(skill_name=self.name, datasets=hits)

        geo = reg.geo()
        cxg = reg.cellxgene()
        pwc = reg.papers_with_code()

        for layer in omics_layers[:3]:
            for ct in cell_types[:5]:
                query = f"immune {ct} {layer}"
                try:
                    resp = await geo.search_datasets(query, retmax=3)
                    if resp.success and resp.data:
                        idlist = resp.data.get("esearchresult", {}).get("idlist", [])
                        for gse in idlist[:2]:
                            hits.append(ImmuneDatasetHit(
                                accession=gse,
                                repository="GEO",
                                cell_type=ct,
                                omics_layer=layer,
                                assay=layer,
                                url=f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse}",
                                description=query,
                            ))
                            cells_covered.add(ct)
                except Exception as e:
                    self.logger.debug(f"GEO search({query}) failed: {e}")

        try:
            ct_resp = await cxg.list_cell_types()
            if ct_resp.success and ct_resp.data:
                rows = ct_resp.data if isinstance(ct_resp.data, list) else ct_resp.data.get("cell_types", [])
                for row in rows[:20]:
                    if isinstance(row, dict):
                        ctname = str(row.get("label", row.get("name", "")))
                        if any(k in ctname.lower() for k in ("t cell", "b cell", "nk", "monocyte", "dc", "neutrophil")):
                            cells_covered.add(ctname)
                            hits.append(ImmuneDatasetHit(
                                accession=str(row.get("id", "")),
                                repository="CellxGene",
                                cell_type=ctname,
                                omics_layer="transcriptome",
                                assay="scRNA-seq",
                                url=str(row.get("url", "")),
                                description=ctname,
                            ))
        except Exception as e:
            self.logger.debug(f"CellxGene list_cell_types failed: {e}")

        for q in ("immune score", "immunophenoscore", "digital immune"):
            try:
                resp = await pwc.search_methods(q)
                if resp.success and resp.data:
                    for item in resp.data.get("results", [])[:2]:
                        if isinstance(item, dict):
                            score_methods.append(str(item.get("name", q)))
            except Exception as e:
                self.logger.debug(f"PwC search_methods({q}) failed: {e}")

        self._metrics.update({
            "datasets_found": len(hits),
            "cell_types_covered": len(cells_covered),
            "score_methods": len(score_methods),
        })
        return ImmuneDatasetSearchOutput(
            skill_name=self.name,
            datasets=hits,
            score_methods=score_methods,
            cell_types_covered=sorted(cells_covered),
        )


EXTRA_SKILLS: dict[str, type[BaseSkill]] = {
    "s6a_immune_dataset_search": ImmuneDatasetSearchSkill,
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
