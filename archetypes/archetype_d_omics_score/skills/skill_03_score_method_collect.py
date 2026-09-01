"""S3 ScoreMethodCollect (Archetype D-specific) - collect omics scoring methods."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s3_score_method_collect")


class ScoreMethodRecord(BaseModel):
    method_name: str = ""
    score_type: str = ""
    trait: str = ""
    tissue: str = ""
    n_features: Optional[int] = None
    training_cohort: str = ""
    validation_cohorts: list[str] = Field(default_factory=list)
    performance_metric: Optional[str] = None
    performance_value: Optional[float] = None
    source: str = ""
    doi: Optional[str] = None


class ScoreMethodCollectInput(SkillInput):
    traits: list[str] = Field(default_factory=list)
    genes: list[str] = Field(default_factory=list)
    max_per_trait: int = 50


class ScoreMethodCollectOutput(SkillOutput):
    methods: list[ScoreMethodRecord] = Field(default_factory=list)
    distinct_score_types: list[str] = Field(default_factory=list)
    distinct_cohorts: list[str] = Field(default_factory=list)
    per_trait_counts: dict[str, int] = Field(default_factory=dict)


class ScoreMethodCollect(BaseSkill):
    """S3 (Archetype D): Collect omics scoring methods (polygenic scores, pathway scores, aging clocks)."""

    name = "score_method_collect"
    description = "Collect multi-omics phenotypic scoring methods for target traits"
    uses_llm = False
    budget_phase = BudgetPhase.SCOPING
    input_schema = ScoreMethodCollectInput
    output_schema = ScoreMethodCollectOutput

    async def execute(self, inp: ScoreMethodCollectInput, ctx: SkillContext) -> ScoreMethodCollectOutput:
        reg = ctx.mcp_registry
        methods: list[ScoreMethodRecord] = []
        per_trait: dict[str, int] = {}

        if not reg:
            return ScoreMethodCollectOutput(skill_name=self.name)

        gwas = reg.gwas_catalog()

        for trait in inp.traits:
            try:
                resp = await gwas.search_associations(trait=trait)
                if resp.success and resp.data:
                    for assoc in resp.data.get("_embedded", {}).get("associations", [])[:inp.max_per_trait]:
                        methods.append(ScoreMethodRecord(
                            method_name=assoc.get("methodName", ""),
                            score_type=assoc.get("scoreType", "polygenic"),
                            trait=trait,
                            source="gwas_catalog",
                        ))
                        per_trait[trait] = per_trait.get(trait, 0) + 1
            except Exception as e:
                logger.warning(f"GWAS catalog search failed for {trait}: {e}")

        deduped = self._deduplicate(methods)
        distinct_score_types = sorted({m.score_type for m in deduped if m.score_type})
        distinct_cohorts = sorted({m.training_cohort for m in deduped if m.training_cohort})

        self._metrics.update({
            "methods": len(deduped),
            "distinct_score_types": len(distinct_score_types),
            "distinct_cohorts": len(distinct_cohorts),
        })
        return ScoreMethodCollectOutput(
            skill_name=self.name,
            methods=deduped,
            distinct_score_types=distinct_score_types,
            distinct_cohorts=distinct_cohorts,
            per_trait_counts=per_trait,
        )

    def _deduplicate(self, methods: list[ScoreMethodRecord]) -> list[ScoreMethodRecord]:
        seen: set[str] = set()
        dedup: list[ScoreMethodRecord] = []
        for m in methods:
            key = f"{m.method_name}|{m.trait}"
            if key not in seen:
                seen.add(key)
                dedup.append(m)
        return dedup
