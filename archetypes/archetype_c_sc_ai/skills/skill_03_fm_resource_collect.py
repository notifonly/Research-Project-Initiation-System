"""S3 FMResourceCollect (Archetype C-specific) - collect single-cell foundation model resources."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s3_fm_resource_collect")


class FMResourceRecord(BaseModel):
    model_name: str = ""
    model_type: str = ""
    tissue: str = ""
    species: str = ""
    n_cells_trained: Optional[int] = None
    n_genes: Optional[int] = None
    architecture: str = ""
    pretraining_data: str = ""
    supported_tasks: list[str] = Field(default_factory=list)
    benchmark_datasets: list[str] = Field(default_factory=list)
    source: str = ""
    doi: Optional[str] = None
    url: Optional[str] = None


class FMResourceCollectInput(SkillInput):
    traits: list[str] = Field(default_factory=list)
    genes: list[str] = Field(default_factory=list)
    max_per_trait: int = 50


class FMResourceCollectOutput(SkillOutput):
    resources: list[FMResourceRecord] = Field(default_factory=list)
    distinct_models: list[str] = Field(default_factory=list)
    distinct_tissues: list[str] = Field(default_factory=list)
    per_trait_counts: dict[str, int] = Field(default_factory=dict)


class FMResourceCollect(BaseSkill):
    """S3 (Archetype C): Collect single-cell foundation model resources from literature + huggingface."""

    name = "fm_resource_collect"
    description = "Collect single-cell foundation model resources, datasets, and benchmarks for target traits"
    uses_llm = False
    budget_phase = BudgetPhase.SCOPING
    input_schema = FMResourceCollectInput
    output_schema = FMResourceCollectOutput

    async def execute(self, inp: FMResourceCollectInput, ctx: SkillContext) -> FMResourceCollectOutput:
        reg = ctx.mcp_registry
        resources: list[FMResourceRecord] = []
        per_trait: dict[str, int] = {}

        if not reg:
            return FMResourceCollectOutput(skill_name=self.name)

        hf = reg.huggingface() if hasattr(reg, "huggingface") else None

        if hf:
            for trait in inp.traits:
                try:
                    resp = await hf.search_models(query=f"single-cell foundation model {trait}", limit=20)
                    if resp.success and resp.data:
                        models = resp.data if isinstance(resp.data, list) else []
                        for m in models[:inp.max_per_trait]:
                            resources.append(FMResourceRecord(
                                model_name=m.get("modelId", m.get("id", "")),
                                model_type="huggingface",
                                source="huggingface",
                                url=m.get("url", m.get("sibling", {}).get("rfilename", "")),
                            ))
                            per_trait[trait] = per_trait.get(trait, 0) + 1
                except Exception:
                    pass

        deduped = self._deduplicate(resources)
        distinct_models = sorted({r.model_name for r in deduped if r.model_name})
        distinct_tissues = sorted({r.tissue for r in deduped if r.tissue})

        self._metrics.update({
            "resources": len(deduped),
            "distinct_models": len(distinct_models),
            "distinct_tissues": len(distinct_tissues),
        })
        return FMResourceCollectOutput(
            skill_name=self.name,
            resources=deduped,
            distinct_models=distinct_models,
            distinct_tissues=distinct_tissues,
            per_trait_counts=per_trait,
        )

    def _deduplicate(self, resources: list[FMResourceRecord]) -> list[FMResourceRecord]:
        seen: set[str] = set()
        dedup: list[FMResourceRecord] = []
        for r in resources:
            key = r.model_name
            if key and key not in seen:
                seen.add(key)
                dedup.append(r)
        return dedup
