"""S3 PRSStudyCollect (Archetype B-specific) - collect PRS studies/methods from PGS Catalog + literature."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s3_prs_study_collect")


class PRSStudyRecord(BaseModel):
    trait: str = ""
    efo: str = ""
    method_name: str = ""
    training_cohort: str = ""
    validation_cohorts: list[str] = Field(default_factory=list)
    ancestry_groups: list[str] = Field(default_factory=list)
    sample_size_training: Optional[int] = None
    n_snps: Optional[int] = None
    p_value_threshold: Optional[float] = None
    r_squared: Optional[float] = None
    calibration_reported: bool = False
    clinical_cutoff: Optional[str] = None
    source: str = ""
    doi: Optional[str] = None


class PRSStudyCollectInput(SkillInput):
    traits: list[str] = Field(default_factory=list)
    efo_ids: list[str] = Field(default_factory=list)
    genes: list[str] = Field(default_factory=list)
    max_per_trait: int = 50


class PRSStudyCollectOutput(SkillOutput):
    studies: list[PRSStudyRecord] = Field(default_factory=list)
    distinct_methods: list[str] = Field(default_factory=list)
    distinct_cohorts: list[str] = Field(default_factory=list)
    per_trait_counts: dict[str, int] = Field(default_factory=dict)


class PRSStudyCollect(BaseSkill):
    """S3 (Archetype B): Collect PRS studies/methods from PGS Catalog and literature."""

    name = "prs_study_collect"
    description = "Collect PRS studies, methods, and training/validation cohorts for target traits"
    uses_llm = False
    budget_phase = BudgetPhase.SCOPING
    input_schema = PRSStudyCollectInput
    output_schema = PRSStudyCollectOutput

    async def execute(self, inp: PRSStudyCollectInput, ctx: SkillContext) -> PRSStudyCollectOutput:
        reg = ctx.mcp_registry
        studies: list[PRSStudyRecord] = []
        per_trait: dict[str, int] = {}

        if not reg:
            return PRSStudyCollectOutput(skill_name=self.name)

        gwas = reg.gwas_catalog()

        for trait in inp.traits:
            try:
                resp = await gwas.search_associations(trait=trait)
                if resp.success and resp.data:
                    for assoc in resp.data.get("_embedded", {}).get("associations", [])[:inp.max_per_trait]:
                        studies.append(PRSStudyRecord(
                            trait=trait,
                            method_name=assoc.get("methodName", ""),
                            training_cohort=assoc.get("cohort", ""),
                            source="gwas_catalog",
                        ))
                        per_trait[trait] = per_trait.get(trait, 0) + 1
            except Exception as e:
                logger.warning(f"GWAS catalog search failed for {trait}: {e}")

        for efo in inp.efo_ids:
            try:
                resp = await gwas.search_associations(efo=efo)
                if resp.success and resp.data:
                    for assoc in resp.data.get("_embedded", {}).get("associations", [])[:inp.max_per_trait]:
                        studies.append(PRSStudyRecord(
                            trait=efo,
                            method_name=assoc.get("methodName", ""),
                            training_cohort=assoc.get("cohort", ""),
                            source="gwas_catalog_efo",
                        ))
                        per_trait[efo] = per_trait.get(efo, 0) + 1
            except Exception:
                pass

        deduped = self._deduplicate(studies)
        distinct_methods = sorted({s.method_name for s in deduped if s.method_name})
        distinct_cohorts = sorted({s.training_cohort for s in deduped if s.training_cohort})

        self._metrics.update({
            "studies": len(deduped),
            "distinct_methods": len(distinct_methods),
            "distinct_cohorts": len(distinct_cohorts),
        })
        return PRSStudyCollectOutput(
            skill_name=self.name,
            studies=deduped,
            distinct_methods=distinct_methods,
            distinct_cohorts=distinct_cohorts,
            per_trait_counts=per_trait,
        )

    def _deduplicate(self, studies: list[PRSStudyRecord]) -> list[PRSStudyRecord]:
        seen: set[str] = set()
        dedup: list[PRSStudyRecord] = []
        for s in studies:
            key = f"{s.trait}|{s.method_name}|{s.training_cohort}"
            if key not in seen:
                seen.add(key)
                dedup.append(s)
        return dedup
