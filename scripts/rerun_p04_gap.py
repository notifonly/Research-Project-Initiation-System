"""B2.2: Re-run S11 (gap_analysis) + S12 (hypothesis_generate) for p04 PRS project.
Uses enhanced S11 with PRS-specific gap patterns, then calls LLM for hypotheses.
"""

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from archetypes import load_archetype
from archetypes.archetype_b_prs.gap_patterns import ARCHETYPE_B_GAP_PATTERNS
from shared.core.config import settings
from shared.core.token_budget import BudgetPhase, TokenBudget
from shared.evidence.coverage_matrix import CoverageMatrix
from shared.skills.base_skill import SkillContext, SkillInput
from shared.skills.skill_11_gap_analysis import (
    GapAnalysis, GapAnalysisInput, GapAnalysisOutput, GapPattern,
)
from shared.skills.skill_12_hypothesis_generate import (
    HypothesisGenerate, HypothesisGenerateInput, HypothesisGenerateOutput,
)


PROJECT_ID = "p04_prs_advance"
ARCHETYPE_ID = "archetype_b_prs"
CARDS_PATH = PROJECT_ROOT / "projects" / PROJECT_ID / "output" / "evidence_cards.jsonl"
CONFIG_PATH = PROJECT_ROOT / "projects" / PROJECT_ID / "config.yaml"
FINAL_REPORT_PATH = PROJECT_ROOT / "projects" / PROJECT_ID / "output" / "final_report.json"
SUMMARY_PATH = PROJECT_ROOT / "projects" / PROJECT_ID / "output" / "summary.json"

# Also check warm-start
WARM_CARDS_PATH = PROJECT_ROOT / "data" / "l1_warm" / PROJECT_ID / "cards.jsonl"


def load_cards() -> list:
    template = load_archetype(ARCHETYPE_ID)
    card_class = template.evidence_card_class

    path = CARDS_PATH if CARDS_PATH.exists() else WARM_CARDS_PATH
    cards = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            if "paper_doi" in raw or "paper_title" in raw:
                raw.setdefault("source_paper", {})
                raw.setdefault("source_location", {})
                for prefix, target in [("paper_", "source_paper"), ("loc_", "source_location")]:
                    obj = {}
                    for k in list(raw.keys()):
                        if k.startswith(prefix):
                            obj[k[len(prefix):]] = raw.pop(k)
                    if obj:
                        raw[target] = obj
                for drop_key in ("tags_str", "_search_text"):
                    raw.pop(drop_key, None)
            try:
                card = card_class.model_validate(raw)
                cards.append(card)
            except Exception:
                pass
    return cards


def load_research_direction() -> str:
    import yaml
    if CONFIG_PATH.exists():
        cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        return cfg.get("research_direction", "")
    return ""


def build_coverage_matrix(cards: list) -> CoverageMatrix:
    template = load_archetype(ARCHETYPE_ID)
    axes = template.config.get("coverage_axes", [])
    matrix = CoverageMatrix(axes=axes)
    for c in cards:
        matrix.add_card(c)
    return matrix


async def run_s11(cards: list, coverage_matrix: CoverageMatrix) -> GapAnalysisOutput:
    skill = GapAnalysis()
    inp = GapAnalysisInput(
        cards=cards,
        coverage_matrix=coverage_matrix,
        gap_patterns=ARCHETYPE_B_GAP_PATTERNS,
    )
    ctx = SkillContext(
        project_id=PROJECT_ID,
        mcp_registry=None,
        card_store=None,
        context=None,
        budget=TokenBudget(project_id=PROJECT_ID),
        archetype_config={},
    )
    result = await skill.execute(inp, ctx)
    print(f"  S11: {len(result.gaps)} gaps identified")
    for g in result.gaps:
        print(f"    [{g.pattern_id}] {g.description[:80]} (score={g.score:.2f})")
    return result


async def run_s12(
    cards: list,
    gaps_output: GapAnalysisOutput,
    research_direction: str,
) -> HypothesisGenerateOutput:
    skill = HypothesisGenerate()
    gap_list = [g.model_dump() if hasattr(g, "model_dump") else g for g in gaps_output.gaps]
    inp = HypothesisGenerateInput(
        gaps=gap_list,
        cards=cards,
        research_direction=research_direction,
        archetype="prs",
        max_hypotheses=5,
    )
    ctx = SkillContext(
        project_id=PROJECT_ID,
        mcp_registry=None,
        card_store=None,
        context=None,
        budget=TokenBudget(project_id=PROJECT_ID),
        archetype_config={},
    )
    result = await skill.execute(inp, ctx)
    print(f"  S12: {len(result.hypotheses)} hypotheses generated")
    for h in result.hypotheses:
        print(f"    {h.hypothesis_id}: {h.statement[:100]} (novelty={h.novelty_score:.2f}, feasibility={h.feasibility_score:.2f})")
    return result


def save_output(
    cards: list,
    matrix: CoverageMatrix,
    gaps_output: GapAnalysisOutput,
    hyp_output: HypothesisGenerateOutput,
    research_direction: str,
) -> None:
    gaps_list = [g.model_dump() if hasattr(g, "model_dump") else g for g in gaps_output.gaps]
    hyps_list = [h.model_dump() if hasattr(h, "model_dump") else h for h in hyp_output.hypotheses]

    # Update final_report.json
    if FINAL_REPORT_PATH.exists():
        report = json.loads(FINAL_REPORT_PATH.read_text(encoding="utf-8"))
    else:
        report = {
            "project_id": PROJECT_ID,
            "archetype_id": ARCHETYPE_ID,
            "research_direction": research_direction,
            "success": True,
            "converged": False,
            "convergence_reasons": ["max_rounds"],
            "total_cards": len(cards),
            "coverage_summary": matrix.summary(),
            "inner_loop_rounds": [],
            "budget": {},
            "duration_s": 0.0,
        }

    report["gaps"] = gaps_list
    report["hypotheses"] = hyps_list
    FINAL_REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"  Updated: {FINAL_REPORT_PATH}")

    # Update summary.json
    summary = {
        "project_id": PROJECT_ID,
        "archetype_id": ARCHETYPE_ID,
        "converged": False,
        "total_cards": len(cards),
        "gap_count": len(gaps_list),
        "hypothesis_count": len(hyps_list),
        "coverage_cells": len(matrix.all_cells()),
        "duration_s": 0.0,
        "budget_used": 0,
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"  Updated: {SUMMARY_PATH}")


async def main():
    settings.ensure_dirs()

    print(f"B2.2: Re-running S11 + S12 for {PROJECT_ID}")
    print(f"  LLM: {settings.llm_model}")

    research_direction = load_research_direction()
    print(f"  Direction: {research_direction[:80]}...")

    cards = load_cards()
    print(f"  Loaded {len(cards)} cards")

    matrix = build_coverage_matrix(cards)
    print(f"  Coverage: {len(matrix.all_cells())} cells")

    gaps_output = await run_s11(cards, matrix)
    hyp_output = await run_s12(cards, gaps_output, research_direction)
    save_output(cards, matrix, gaps_output, hyp_output, research_direction)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
