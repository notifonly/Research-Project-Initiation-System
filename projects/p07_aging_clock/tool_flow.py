"""P07: Multi-omics aging clock.

Archetype D (Multi-omics phenotypic scoring). Divergent Step 6
(s6a_aging_clock_search) searches GEO + GitHub + PapersWithCode for aging
cohort datasets and epigenetic-clock method implementations (Horvath,
GrimAge, PhenoAge, DunedinPACE).
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


class AgingClockSearchInput(SkillInput):
    key_terms: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    reading_list: list[dict[str, Any]] = Field(default_factory=list)


class AgingDatasetHit(BaseModel):
    accession: str = ""
    repository: str = ""
    omics_layer: str = ""
    assay: str = ""
    age_range: str = ""
    n_samples: int = 0
    url: str = ""
    description: str = ""


class AgingClockMethodHit(BaseModel):
    name: str = ""
    repository: str = ""
    url: str = ""
    clock_family: str = ""
    has_weights: bool = False
    description: str = ""


class AgingClockSearchOutput(SkillOutput):
    datasets: list[AgingDatasetHit] = Field(default_factory=list)
    clock_methods: list[AgingClockMethodHit] = Field(default_factory=list)
    clocks_by_family: dict[str, list[str]] = Field(default_factory=dict)


class AgingClockSearchSkill(BaseSkill):
    """Divergent Step 6 for P07: search aging cohort datasets & epigenetic clock methods."""

    name = "s6a_aging_clock_search"
    description = "Search GEO + GitHub + PapersWithCode for aging cohort datasets & epigenetic clock methods"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = AgingClockSearchInput
    output_schema = AgingClockSearchOutput

    async def execute(self, inp: AgingClockSearchInput, ctx: SkillContext) -> AgingClockSearchOutput:
        reg = ctx.mcp_registry
        params = ctx.archetype_config.get("parameters", {})
        omics_layers = params.get("omics_layers_of_interest", ["dna_methylation", "transcriptome", "proteomics"])
        clocks = params.get("aging_clocks_of_interest", ["Horvath", "GrimAge", "PhenoAge", "DunedinPACE"])

        datasets: list[AgingDatasetHit] = []
        methods: list[AgingClockMethodHit] = []
        by_family: dict[str, list[str]] = {}

        if not reg:
            return AgingClockSearchOutput(skill_name=self.name, datasets=datasets)

        geo = reg.geo()
        github = reg.github()
        pwc = reg.papers_with_code()

        for layer in omics_layers[:3]:
            query = f"aging {layer} cohort"
            try:
                resp = await geo.search_datasets(query, retmax=5)
                if resp.success and resp.data:
                    idlist = resp.data.get("esearchresult", {}).get("idlist", [])
                    for gse in idlist[:3]:
                        datasets.append(AgingDatasetHit(
                            accession=gse,
                            repository="GEO",
                            omics_layer=layer,
                            assay=layer,
                            url=f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse}",
                            description=query,
                        ))
            except Exception as e:
                self.logger.debug(f"GEO search({query}) failed: {e}")

        for clock in clocks:
            try:
                resp = await pwc.search_methods(clock)
                if resp.success and resp.data:
                    for item in resp.data.get("results", [])[:2]:
                        if not isinstance(item, dict):
                            continue
                        methods.append(AgingClockMethodHit(
                            name=str(item.get("name", clock)),
                            repository="PapersWithCode",
                            url=str(item.get("url", "")),
                            clock_family=clock,
                            description=str(item.get("description", "")),
                        ))
                        by_family.setdefault(clock, []).append(str(item.get("name", clock)))
            except Exception as e:
                self.logger.debug(f"PwC search_methods({clock}) failed: {e}")

            q = f"{clock} epigenetic clock aging"
            try:
                resp = await github.search_repositories(q, per_page=3)
                if resp.success and resp.data:
                    for item in resp.data.get("items", [])[:3]:
                        if not isinstance(item, dict):
                            continue
                        full = str(item.get("full_name", ""))
                        methods.append(AgingClockMethodHit(
                            name=full,
                            repository="GitHub",
                            url=str(item.get("html_url", "")),
                            clock_family=clock,
                            has_weights="clock" in str(item.get("description", "")).lower(),
                            description=str(item.get("description", "")),
                        ))
                        by_family.setdefault(clock, []).append(full)
            except Exception as e:
                self.logger.debug(f"GitHub search({q}) failed: {e}")

        self._metrics.update({
            "datasets_found": len(datasets),
            "clock_methods": len(methods),
            "clock_families": len(by_family),
        })
        return AgingClockSearchOutput(
            skill_name=self.name,
            datasets=datasets,
            clock_methods=methods,
            clocks_by_family=by_family,
        )


EXTRA_SKILLS: dict[str, type[BaseSkill]] = {
    "s6a_aging_clock_search": AgingClockSearchSkill,
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
