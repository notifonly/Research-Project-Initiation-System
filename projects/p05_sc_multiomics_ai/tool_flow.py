"""P05: Single-cell multi-omics foundation models.

Archetype C (Foundation models). Divergent Step 6 (s6a_scfm_search) searches
HuggingFace + GitHub + PapersWithCode for single-cell foundation model
weights, training repos, and benchmark suites (scVI, scGPT, Geneformer,
scFoundation, UCE, MultiVI).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from archetypes.archetype_c_sc_ai.skills.skill_07_scfm_card_extract import SCFMCardExtract

from shared.core.orchestrator import Orchestrator, ProjectResult
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.yaml"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class SCFMSearchInput(SkillInput):
    key_terms: list[str] = Field(default_factory=list)
    sub_questions: list[str] = Field(default_factory=list)
    reading_list: list[dict[str, Any]] = Field(default_factory=list)


class SCFMHit(BaseModel):
    name: str = ""
    repository: str = ""
    url: str = ""
    model_family: str = ""
    has_weights: bool = False
    has_benchmark: bool = False
    n_downloads: int = 0
    description: str = ""


class SCFMSearchOutput(SkillOutput):
    models: list[SCFMHit] = Field(default_factory=list)
    benchmark_suites: list[SCFMHit] = Field(default_factory=list)
    models_by_family: dict[str, list[str]] = Field(default_factory=dict)


class SCFMSearchSkill(BaseSkill):
    """Divergent Step 6 for P05: search single-cell foundation models & benchmark suites."""

    name = "s6a_scfm_search"
    description = "Search HuggingFace + GitHub + PapersWithCode for sc foundation models (scVI, scGPT, Geneformer)"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = SCFMSearchInput
    output_schema = SCFMSearchOutput

    async def execute(self, inp: SCFMSearchInput, ctx: SkillContext) -> SCFMSearchOutput:
        reg = ctx.mcp_registry
        params = ctx.archetype_config.get("parameters", {})
        fms = params.get("foundation_models_of_interest", ["scVI", "scGPT", "Geneformer"])

        models: list[SCFMHit] = []
        benchmarks: list[SCFMHit] = []
        by_family: dict[str, list[str]] = {}

        if not reg:
            return SCFMSearchOutput(skill_name=self.name, models=models)

        hf = reg.huggingface()
        github = reg.github()
        pwc = reg.papers_with_code()

        for fm in fms:
            try:
                resp = await hf.search_models(fm, limit=3)
                if resp.success and resp.data:
                    rows = resp.data if isinstance(resp.data, list) else []
                    for item in rows[:3]:
                        if not isinstance(item, dict):
                            continue
                        mid = str(item.get("id", item.get("modelId", "")))
                        models.append(SCFMHit(
                            name=mid,
                            repository="HuggingFace",
                            url=str(item.get("url", f"https://huggingface.co/{mid}")),
                            model_family=fm,
                            has_weights=True,
                            n_downloads=int(item.get("downloads", 0) or 0),
                            description=str(item.get("pipeline_tag", "")),
                        ))
                        by_family.setdefault(fm, []).append(mid)
            except Exception as e:
                self.logger.debug(f"HF search_models({fm}) failed: {e}")

            q = f"{fm} single-cell foundation model"
            try:
                resp = await github.search_repositories(q, per_page=3)
                if resp.success and resp.data:
                    for item in resp.data.get("items", [])[:3]:
                        if not isinstance(item, dict):
                            continue
                        full = str(item.get("full_name", ""))
                        models.append(SCFMHit(
                            name=full,
                            repository="GitHub",
                            url=str(item.get("html_url", "")),
                            model_family=fm,
                            description=str(item.get("description", "")),
                        ))
                        by_family.setdefault(fm, []).append(full)
            except Exception as e:
                self.logger.debug(f"GitHub search({q}) failed: {e}")

        bq = "single-cell benchmark foundation model"
        try:
            resp = await pwc.search_papers(bq, items_per_page=5)
            if resp.success and resp.data:
                for item in resp.data.get("results", [])[:5]:
                    if not isinstance(item, dict):
                        continue
                    benchmarks.append(SCFMHit(
                        name=str(item.get("title", "")),
                        repository="PapersWithCode",
                        url=str(item.get("url", "")),
                        has_benchmark=True,
                        description=str(item.get("abstract", ""))[:200],
                    ))
        except Exception as e:
            self.logger.debug(f"PwC benchmark search failed: {e}")

        self._metrics.update({
            "models_found": len(models),
            "benchmark_suites": len(benchmarks),
            "model_families": len(by_family),
        })
        return SCFMSearchOutput(
            skill_name=self.name,
            models=models,
            benchmark_suites=benchmarks,
            models_by_family=by_family,
        )


EXTRA_SKILLS: dict[str, type[BaseSkill]] = {
    "s6a_scfm_search": SCFMSearchSkill,
    "s7_evidence_card_extract": SCFMCardExtract,
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
