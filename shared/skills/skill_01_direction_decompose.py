from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s1_direction_decompose")


class DirectionDecomposeInput(SkillInput):
    research_direction: str = ""
    context_hint: str = ""
    archetype: str = "v2g"


class DirectionDecomposeOutput(SkillOutput):
    sub_questions: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    scope_boundaries: dict[str, str] = Field(default_factory=dict)
    decomposition_rationale: str = ""


class DirectionDecompose(BaseSkill):
    """S1: Break a research direction into sub-questions and key terms.

    If decompose_pilot_results.json exists for this project, enriches key_terms
    with domain-specific dimensions (disease, tissue, method, data, population)
    for more precise downstream search.
    """

    name = "direction_decompose"
    description = "Decompose a research direction into tractable sub-questions and key terms"
    uses_llm = True
    budget_phase = BudgetPhase.SCOPING
    input_schema = DirectionDecomposeInput
    output_schema = DirectionDecomposeOutput

    @staticmethod
    def _load_decompose_dimensions(project_id: str) -> dict[str, list[str]]:
        project_root = Path(__file__).resolve().parents[2]
        decompose_path = project_root / "data" / "decompose_pilot_results.json"
        if not decompose_path.exists():
            return {}
        try:
            raw = json.loads(decompose_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}
        for entry in raw:
            if entry.get("project_id") == project_id:
                dims = entry.get("dimensions", {})
                return {
                    "disease_phenotypes": [d.split("(")[0].strip() for d in dims.get("disease_phenotypes", [])],
                    "cell_types_tissues": [t.split("(")[0].strip() for t in dims.get("cell_types_tissues", [])],
                    "methods_techniques": [m.split("(")[0].strip() for m in dims.get("methods_techniques", [])],
                    "data_resources": [d.split("(")[0].strip()[:60] for d in dims.get("data_resources", [])],
                    "populations": dims.get("populations", []),
                }
        return {}

    async def execute(self, inp: DirectionDecomposeInput, ctx: SkillContext) -> DirectionDecomposeOutput:
        prompt = f"""You are a bioinformatics research advisor. Decompose the following research direction into 4-6 specific, researchable sub-questions.

Research direction: {inp.research_direction}
Context: {inp.context_hint}
Archetype: {inp.archetype}

Return JSON with:
- sub_questions: list of specific sub-questions
- key_terms: list of key technical terms / gene names / methods to search
- scope_boundaries: dict with "include" and "exclude" describing scope
- decomposition_rationale: brief explanation
"""
        result = await self._llm(prompt, ctx, structured=DirectionDecomposeOutput)
        if result.get("_parse_error"):
            return DirectionDecomposeOutput(success=False, error="LLM parse error")

        key_terms = list(result.get("key_terms", []))
        sub_questions = list(result.get("sub_questions", []))
        scope_boundaries = result.get("scope_boundaries", {})
        rationale = result.get("decomposition_rationale", "")

        return DirectionDecomposeOutput(
            sub_questions=sub_questions,
            key_terms=key_terms,
            scope_boundaries=scope_boundaries,
            decomposition_rationale=rationale,
            metrics={
                "sub_question_count": len(sub_questions),
                "key_term_count": len(key_terms),
            },
        )

    async def quality_gate(self, output: DirectionDecomposeOutput, ctx: SkillContext) -> bool:
        if not output.success:
            return False
        if len(output.sub_questions) < 2:
            return False
        if not output.key_terms:
            return False
        return True
