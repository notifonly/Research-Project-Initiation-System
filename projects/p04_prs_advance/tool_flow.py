"""P04: Polygenic risk score methodology advance.

Archetype B (Statistical genetics methods). Divergent Step 6
(s6a_prs_method_search) searches GWAS Catalog + PapersWithCode + GitHub for
PRS method implementations (LDpred2, PRS-CS, lassosum, SBayesR) and
benchmarking suites.
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


class PRSMethodSearchInput(SkillInput):
    traits: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    reading_list: list[dict[str, Any]] = Field(default_factory=list)


class PRSMethodHit(BaseModel):
    name: str = ""
    repository: str = ""
    url: str = ""
    method_family: str = ""
    has_weights: bool = False
    has_benchmark: bool = False
    description: str = ""


class PRSMethodSearchOutput(SkillOutput):
    methods: list[PRSMethodHit] = Field(default_factory=list)
    benchmark_suites: list[PRSMethodHit] = Field(default_factory=list)
    methods_by_family: dict[str, list[str]] = Field(default_factory=dict)


class PRSMethodSearchSkill(BaseSkill):
    """Divergent Step 6 for P04: search PRS method repos + benchmarking suites."""

    name = "s6a_prs_method_search"
    description = "Search GWAS Catalog + PapersWithCode + GitHub for PRS method implementations & benchmarks"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = PRSMethodSearchInput
    output_schema = PRSMethodSearchOutput

    async def execute(self, inp: PRSMethodSearchInput, ctx: SkillContext) -> PRSMethodSearchOutput:
        reg = ctx.mcp_registry
        params = ctx.archetype_config.get("parameters", {})
        methods_of_interest = params.get("prs_methods_of_interest", ["LDpred2", "PRS-CS", "lassosum"])

        methods: list[PRSMethodHit] = []
        benchmarks: list[PRSMethodHit] = []
        by_family: dict[str, list[str]] = {}

        if not reg:
            return PRSMethodSearchOutput(skill_name=self.name, methods=methods)

        pwc = reg.papers_with_code()
        github = reg.github()
        gwas = reg.gwas_catalog()

        for mname in methods_of_interest:
            try:
                resp = await pwc.search_methods(mname)
                if resp.success and resp.data:
                    for item in resp.data.get("results", [])[:3]:
                        if not isinstance(item, dict):
                            continue
                        methods.append(PRSMethodHit(
                            name=str(item.get("name", mname)),
                            repository="PapersWithCode",
                            url=str(item.get("url", "")),
                            method_family=mname,
                            description=str(item.get("description", "")),
                        ))
                        by_family.setdefault(mname, []).append(str(item.get("name", mname)))
            except Exception as e:
                self.logger.debug(f"PwC search_methods({mname}) failed: {e}")

            q = f"{mname} PRS polygenic risk score"
            try:
                resp = await github.search_repositories(q, per_page=3)
                if resp.success and resp.data:
                    for item in resp.data.get("items", [])[:3]:
                        if not isinstance(item, dict):
                            continue
                        full = str(item.get("full_name", ""))
                        methods.append(PRSMethodHit(
                            name=full,
                            repository="GitHub",
                            url=str(item.get("html_url", "")),
                            method_family=mname,
                            has_weights=bool(item.get("topics", [])),
                            description=str(item.get("description", "")),
                        ))
                        by_family.setdefault(mname, []).append(full)
            except Exception as e:
                self.logger.debug(f"GitHub search({q}) failed: {e}")

        bq = "PRS benchmark polygenic"
        try:
            resp = await github.search_repositories(bq, per_page=5)
            if resp.success and resp.data:
                for item in resp.data.get("items", [])[:5]:
                    if not isinstance(item, dict):
                        continue
                    benchmarks.append(PRSMethodHit(
                        name=str(item.get("full_name", "")),
                        repository="GitHub",
                        url=str(item.get("html_url", "")),
                        has_benchmark=True,
                        description=str(item.get("description", "")),
                    ))
        except Exception as e:
            self.logger.debug(f"GitHub benchmark search failed: {e}")

        for trait in inp.traits[:5]:
            try:
                resp = await gwas.search_studies(trait=trait, size=3)
                if resp.success and resp.data:
                    studies = resp.data.get("_embedded", {}).get("studies", [])
                    self._metrics[f"gwas_studies_{trait}"] = len(studies)
            except Exception as e:
                self.logger.debug(f"GWAS search_studies({trait}) failed: {e}")

        self._metrics.update({
            "methods_found": len(methods),
            "benchmark_suites": len(benchmarks),
            "method_families": len(by_family),
        })
        return PRSMethodSearchOutput(
            skill_name=self.name,
            methods=methods,
            benchmark_suites=benchmarks,
            methods_by_family=by_family,
        )


EXTRA_SKILLS: dict[str, type[BaseSkill]] = {
    "s6a_prs_method_search": PRSMethodSearchSkill,
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
