"""Re-run S11+S12 for p05 (scAI), p06 (immune), p07 (aging).
Converts cards from v2g schema to correct archetype schema, then runs gap analysis
with archetype-specific patterns and hypothesis generation with LLM.
"""

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from archetypes import load_archetype
from archetypes.archetype_c_sc_ai.gap_patterns import ARCHETYPE_C_GAP_PATTERNS
from archetypes.archetype_d_omics_score.gap_patterns import ARCHETYPE_D_GAP_PATTERNS
from archetypes.archetype_c_sc_ai.evidence_card import SCFMEvidenceCard
from archetypes.archetype_d_omics_score.evidence_card import OmicsScoreEvidenceCard
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


PROJECTS = [
    {
        "project_id": "p05_sc_multiomics_ai",
        "archetype_id": "archetype_c_sc_ai",
        "card_class": SCFMEvidenceCard,
        "archetype_str": "sc_fm",
        "gap_patterns": ARCHETYPE_C_GAP_PATTERNS,
    },
    {
        "project_id": "p06_digital_immune",
        "archetype_id": "archetype_d_omics_score",
        "card_class": OmicsScoreEvidenceCard,
        "archetype_str": "omics_score",
        "gap_patterns": ARCHETYPE_D_GAP_PATTERNS,
    },
    {
        "project_id": "p07_aging_clock",
        "archetype_id": "archetype_d_omics_score",
        "card_class": OmicsScoreEvidenceCard,
        "archetype_str": "omics_score",
        "gap_patterns": ARCHETYPE_D_GAP_PATTERNS,
    },
]


def load_and_convert_cards(project_id: str, archetype_id: str, card_class):
    template = load_archetype(archetype_id)
    axes = template.config.get("coverage_axes", [])

    warm_path = PROJECT_ROOT / "data" / "l1_warm" / project_id / "cards.jsonl"
    output_path = PROJECT_ROOT / "projects" / project_id / "output" / "evidence_cards.jsonl"

    path = output_path if output_path.exists() else warm_path
    if not path.exists():
        print(f"  WARNING: no cards.jsonl found at {path}")
        return [], axes

    cards = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)

            raw.setdefault("source_paper", {})
            raw.setdefault("source_location", {})
            for prefix, target in [("paper_", "source_paper"), ("loc_", "source_location")]:
                obj = {}
                for k in list(raw.keys()):
                    if k.startswith(prefix):
                        obj[k[len(prefix):]] = raw.pop(k)
                if obj:
                    src = raw.get(target, {})
                    if isinstance(src, dict):
                        src.update(obj)
                        raw[target] = src

            for drop_key in ("tags_str", "_search_text"):
                raw.pop(drop_key, None)

            raw["archetype"] = card_class.model_fields.get("archetype", type(None))
            default = getattr(card_class.model_fields.get("archetype", None), "default", None) if "archetype" in card_class.model_fields else None
            if default is not None:
                raw["archetype"] = default

            try:
                card = card_class.model_validate(raw)
                cards.append(card)
            except Exception as e:
                pass

    print(f"  Converted {len(cards)} cards to {card_class.__name__}")
    return cards, axes


def save_cards_jsonl(project_id: str, cards: list) -> None:
    output_path = PROJECT_ROOT / "projects" / project_id / "output" / "evidence_cards.jsonl"
    warm_path = PROJECT_ROOT / "data" / "l1_warm" / project_id / "cards.jsonl"
    for p in (output_path, warm_path):
        p.parent.mkdir(parents=True, exist_ok=True)
    for p in (output_path, warm_path):
        with p.open("w", encoding="utf-8") as f:
            for c in cards:
                flat = c.to_flat_dict()
                f.write(json.dumps(flat, ensure_ascii=False, default=str) + "\n")
    print(f"  Saved {len(cards)} cards to {output_path}")


def build_coverage_matrix(cards: list, axes: list) -> CoverageMatrix:
    matrix = CoverageMatrix(axes=axes)
    for c in cards:
        matrix.add_card(c)
    return matrix


def load_research_direction(project_id: str) -> str:
    import yaml
    cfg_path = PROJECT_ROOT / "projects" / project_id / "config.yaml"
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        return cfg.get("research_direction", "")
    return ""


async def run_s11(cards: list, coverage_matrix: CoverageMatrix,
                  gap_patterns: list, project_id: str) -> GapAnalysisOutput:
    skill = GapAnalysis()
    inp = GapAnalysisInput(
        cards=cards,
        coverage_matrix=coverage_matrix,
        gap_patterns=gap_patterns,
    )
    ctx = SkillContext(
        project_id=project_id,
        mcp_registry=None,
        card_store=None,
        context=None,
        budget=TokenBudget(project_id=project_id),
        archetype_config={},
    )
    result = await skill.execute(inp, ctx)
    print(f"  S11: {len(result.gaps)} gaps identified")
    for g in result.gaps:
        print(f"    [{g.pattern_id}] {g.description[:80]} (score={g.score:.2f})")
    return result


async def run_s12(cards: list, gaps_output: GapAnalysisOutput,
                  research_direction: str, archetype_str: str,
                  project_id: str) -> HypothesisGenerateOutput:
    skill = HypothesisGenerate()
    gap_list = [g.model_dump() if hasattr(g, "model_dump") else g for g in gaps_output.gaps]
    inp = HypothesisGenerateInput(
        gaps=gap_list,
        cards=cards,
        research_direction=research_direction,
        archetype=archetype_str,
        max_hypotheses=5,
    )
    ctx = SkillContext(
        project_id=project_id,
        mcp_registry=None,
        card_store=None,
        context=None,
        budget=TokenBudget(project_id=project_id),
        archetype_config={},
    )
    result = await skill.execute(inp, ctx)
    print(f"  S12: {len(result.hypotheses)} hypotheses generated")
    for h in result.hypotheses:
        print(f"    {h.hypothesis_id}: {h.statement[:100]} (novelty={h.novelty_score:.2f}, feasibility={h.feasibility_score:.2f})")
    return result


def save_output(project_id: str, archetype_id: str, cards: list,
                matrix: CoverageMatrix, gaps_output: GapAnalysisOutput,
                hyp_output: HypothesisGenerateOutput,
                research_direction: str) -> None:
    out_dir = PROJECT_ROOT / "projects" / project_id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    gaps_list = [g.model_dump() if hasattr(g, "model_dump") else g for g in gaps_output.gaps]
    hyps_list = [h.model_dump() if hasattr(h, "model_dump") else h for h in hyp_output.hypotheses]

    report_path = out_dir / "final_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        report = {
            "project_id": project_id,
            "archetype_id": archetype_id,
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
    report["total_cards"] = len(cards)
    report["coverage_summary"] = matrix.summary()
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"  Updated: {report_path}")

    summary_path = out_dir / "summary.json"
    existing_summary = {}
    if summary_path.exists():
        try:
            existing_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    summary = {
        "project_id": project_id,
        "archetype_id": archetype_id,
        "converged": report.get("converged", False),
        "total_cards": len(cards),
        "gap_count": len(gaps_list),
        "hypothesis_count": len(hyps_list),
        "coverage_cells": len(matrix.all_cells()),
        "duration_s": existing_summary.get("duration_s", report.get("duration_s", 0.0)),
        "budget_used": existing_summary.get("budget_used", report.get("budget", {}).get("total_used", 0)),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"  Updated: {summary_path}")

    save_coverage_map(project_id, matrix)


def save_coverage_map(project_id: str, matrix: CoverageMatrix) -> None:
    cmap_path = PROJECT_ROOT / "projects" / project_id / "output" / "coverage_map.json"
    cells = matrix.all_cells()
    cmap: list = []
    axes = matrix.AXES
    for key, cell in cells.items():
        entry = {ax: val for ax, val in zip(axes, key)}
        entry.update({
            "card_count": cell.card_count,
            "has_fine_mapping": cell.has_fine_mapping,
            "has_colocalization": cell.has_colocalization,
            "has_replication": cell.has_replication,
            "data_available": cell.data_available,
        })
        cmap.append(entry)
    cmap_path.write_text(
        json.dumps(cmap, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"  Saved coverage_map.json ({len(cells)} cells)")


async def process_project(cfg: dict) -> None:
    project_id = cfg["project_id"]
    print(f"\n{'='*60}")
    print(f"Processing: {project_id} ({cfg['archetype_str']})")
    print(f"{'='*60}")

    research_direction = load_research_direction(project_id)
    print(f"  Direction: {research_direction[:80]}...")

    cards, axes = load_and_convert_cards(
        project_id, cfg["archetype_id"], cfg["card_class"]
    )
    if not cards:
        print(f"  SKIPPED: no cards found")
        return

    save_cards_jsonl(project_id, cards)

    matrix = build_coverage_matrix(cards, axes)
    print(f"  Coverage: {len(matrix.all_cells())} occupied cells, {matrix.summary().get('total_cells', 0)} total")

    gaps_output = await run_s11(cards, matrix, cfg["gap_patterns"], project_id)
    hyp_output = await run_s12(cards, gaps_output, research_direction,
                               cfg["archetype_str"], project_id)

    save_output(project_id, cfg["archetype_id"], cards, matrix,
                gaps_output, hyp_output, research_direction)
    print(f"  DONE: {len(gaps_output.gaps)} gaps, {len(hyp_output.hypotheses)} hypotheses")


async def main():
    settings.ensure_dirs()
    print(f"Re-running S11+S12 for p05, p06, p07")
    print(f"  LLM: {settings.llm_model}")

    for cfg in PROJECTS:
        await process_project(cfg)

    print(f"\n{'='*60}")
    print("All done. Run 'python dashboard/build_data.py' to rebuild data.json.")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
