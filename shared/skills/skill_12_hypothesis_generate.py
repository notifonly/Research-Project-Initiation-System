"""S12 HypothesisGenerate - generate research hypotheses addressing identified gaps."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.core.token_budget import BudgetPhase
from shared.evidence.base_card import (
    BaseEvidenceCard,
    ARCHETYPE_V2G,
    ARCHETYPE_PRS,
    ARCHETYPE_SC_FM,
    ARCHETYPE_OMICS_SCORE,
)
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput
from shared.skills.skill_11_gap_analysis import IdentifiedGap


class HypothesisGenerateInput(SkillInput):
    gaps: list[IdentifiedGap] = Field(default_factory=list)
    cards: list[BaseEvidenceCard] = Field(default_factory=list)
    research_direction: str = ""
    archetype: str = ARCHETYPE_V2G
    max_hypotheses: int = 5


class Hypothesis(BaseModel):
    hypothesis_id: str = ""
    statement: str = ""
    addresses_gap: str = ""
    rationale: str = ""
    required_methods: list[str] = Field(default_factory=list)
    required_datasets: list[str] = Field(default_factory=list)
    novelty_score: float = 0.0
    feasibility_score: float = 0.0
    expected_impact: str = ""


class HypothesisGenerateOutput(SkillOutput):
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    top_hypothesis: Optional[Hypothesis] = None


class HypothesisGenerate(BaseSkill):
    """S12: Generate research hypotheses that address identified gaps."""

    name = "hypothesis_generate"
    description = "Generate testable research hypotheses addressing identified evidence gaps"
    uses_llm = True
    budget_phase = BudgetPhase.SYNTHESIS
    input_schema = HypothesisGenerateInput
    output_schema = HypothesisGenerateOutput

    async def execute(self, inp: HypothesisGenerateInput, ctx: SkillContext) -> HypothesisGenerateOutput:
        if not inp.gaps:
            return HypothesisGenerateOutput(skill_name=self.name, error="no gaps to address")

        def _gval(g: Any, key: str, default: Any = "") -> Any:
            return g.get(key, default) if isinstance(g, dict) else getattr(g, key, default)

        gap_summaries = [
            f"[{_gval(g, 'gap_id')}] {_gval(g, 'pattern_id')}: {_gval(g, 'description')} "
            f"(score={float(_gval(g, 'score', 0)):.2f}, feasibility={float(_gval(g, 'feasibility', 0)):.2f})"
            for g in inp.gaps[:10]
        ]
        card_findings = []
        for c in inp.cards[:15]:
            card = _gval(c, "key_finding") or ""
            if inp.archetype == ARCHETYPE_SC_FM:
                extra = f"{_gval(c, 'task')} | {_gval(c, 'model_family')} | {_gval(c, 'tissue')} | {_gval(c, 'model_architecture')}"
            elif inp.archetype == ARCHETYPE_OMICS_SCORE:
                extra = f"{_gval(c, 'omics_layer')} | {_gval(c, 'trait_label')} | {_gval(c, 'model_type')}"
            elif inp.archetype == ARCHETYPE_PRS:
                extra = f"{_gval(c, 'trait_label')} | {_gval(c, 'method_name')} | {_gval(c, 'population_ancestry')}"
            elif _gval(c, 'trait_label'):
                extra = f"{_gval(c, 'trait_label')}, {_gval(c, 'functional_modality')}, {_gval(c, 'locus_genes')}"
            else:
                extra = _gval(c, 'method_brief', '')[:60]
            card_findings.append(f"- {card} ({extra})")

        available_accessions = sorted(set(
            _gval(c, 'raw_data_accession') for c in (inp.cards or [])
            if _gval(c, 'raw_data_accession')
        ))
        dataset_hint = (
            f"Available datasets (from evidence cards, use only what is listed): "
            f"{', '.join(available_accessions[:15])}"
        ) if available_accessions else "No dataset accessions recorded in evidence."

        prompt = f"""You are a bioinformatics research strategist generating a 开题 (research proposal) hypothesis.
Research direction: {inp.research_direction}
Archetype: {inp.archetype}

Identified gaps:
{chr(10).join(gap_summaries)}

Key existing evidence:
{chr(10).join(card_findings)}

{dataset_hint}

CRITICAL: Each hypothesis MUST explicitly address at least one of the identified gaps above.
The hypothesis domain must stay within the archetype's evidence space ({inp.archetype}).
Do NOT propose disease-specific hypotheses unless the gaps explicitly reference diseases.

Generate up to {inp.max_hypotheses} testable, novel hypotheses that directly address the gaps.
Return JSON: a list of objects with fields:
- statement (str): the hypothesis
- addresses_gap (str): gap_id it addresses (single gap_id per hypothesis)
- rationale (str): why this is novel and how evidence supports/contradicts
- required_methods (list[str])
- required_datasets (list[str]): use ONLY datasets from the available list above
- novelty_score (0-1), feasibility_score (0-1), expected_impact (str)"""

        result = await self._llm(prompt, ctx, structured=list)
        if isinstance(result, dict):
            for v in result.values():
                if isinstance(v, list):
                    result = v
                    break
        hypotheses: list[Hypothesis] = []
        if isinstance(result, list):
            for i, item in enumerate(result):
                if not isinstance(item, dict):
                    continue
                hypotheses.append(Hypothesis(
                    hypothesis_id=f"H{i+1}",
                    statement=item.get("statement", ""),
                    addresses_gap=item.get("addresses_gap", ""),
                    rationale=item.get("rationale", ""),
                    required_methods=item.get("required_methods", []) or [],
                    required_datasets=item.get("required_datasets", []) or [],
                    novelty_score=float(item.get("novelty_score", 0.0)),
                    feasibility_score=float(item.get("feasibility_score", 0.0)),
                    expected_impact=item.get("expected_impact", ""),
                ))

        hypotheses.sort(key=lambda h: (h.novelty_score + h.feasibility_score), reverse=True)
        top = hypotheses[0] if hypotheses else None
        self._metrics.update({
            "hypotheses": len(hypotheses),
            "avg_novelty": round(sum(h.novelty_score for h in hypotheses) / max(1, len(hypotheses)), 3),
        })
        return HypothesisGenerateOutput(
            skill_name=self.name,
            hypotheses=hypotheses,
            top_hypothesis=top,
        )
