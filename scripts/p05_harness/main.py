#!/usr/bin/env python3
"""Research Plan Quality Harness — Entry Point.

Runs the critique-refine loop for candidate research plans.
Generates enriched plans, acceptance report, and dashboard data.

Usage:
    python scripts/p05_harness/main.py                    # Full run (top 10 deep + 30 summaries)
    python scripts/p05_harness/main.py --deep-only         # Top 10 deep analysis only
    python scripts/p05_harness/main.py --max-candidates 5  # Only first 5 candidates
    python scripts/p05_harness/main.py --candidates T006,T004  # Specific candidates
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from shared.core.config import PROJECT_ROOT
from shared.core.llm_client import get_llm

sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="P05 Research Plan Quality Harness")
    parser.add_argument("--deep-only", action="store_true", help="Only deep analysis (top 10)")
    parser.add_argument("--max-candidates", type=int, default=0, help="Max candidates to process")
    parser.add_argument("--candidates", type=str, default="", help="Comma-separated candidate IDs")
    parser.add_argument("--candidates-file", type=str, default="", help="JSON file with custom candidates to merge (prepended before decompose)")
    parser.add_argument("--skip-mcp", action="store_true", help="Skip MCP search (LLM only)")
    parser.add_argument("--output-dir", type=str, default="", help="Output directory")
    parser.add_argument("--run-name", type=str, default="", help="Run name (default: auto-timestamp)")
    parser.add_argument("--merge", type=str, default="", help="Comma-separated run names to merge into aggregate")
    parser.add_argument("--list-runs", action="store_true", help="List all saved runs")
    parser.add_argument("--recover", type=str, default="", help="Recover/continue from a specific run name")
    args = parser.parse_args()

    if get_llm() is None:
        print("ERROR: litellm not available. Please install: pip install litellm")
        sys.exit(1)

    import os
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("AISCIENCE_LLM_API_KEY") and not os.environ.get("LLM_API_KEY"):
        print("WARNING: No API key found in environment (OPENAI_API_KEY / AISCIENCE_LLM_API_KEY / LLM_API_KEY). LLM calls will fail.")

    asyncio.run(run_harness(args))


async def run_harness(args) -> None:
    from scripts.p05_harness.domain_prompts import get_prompts, set_prompts
    from scripts.p05_harness.loop_runner import HarnessResult, LoopRunner
    from scripts.p05_harness.report import generate_report
    from scripts.p05_harness.config_schema import load_harness_config

    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}")
        return
    try:
        config_model = load_harness_config(str(config_path))
        print(f"Config validated: {config_model.harness_name}")
    except Exception as e:
        print(f"ERROR loading config: {e}")
        return

    config = config_model.model_dump()

    # Setup output
    output_dir = PROJECT_ROOT / config.get("output", {}).get("dir", "data/harness_output")
    if args.output_dir:
        output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # --list-runs: just print and exit
    if args.list_runs:
        list_saved_runs(runs_dir)
        return

    # --merge: aggregate runs without running new loop
    if args.merge:
        run_names = [r.strip() for r in args.merge.split(",") if r.strip()]
        merge_runs(runs_dir, run_names, output_dir)
        return

    harness_name = config.get("harness_name", "")
    print("=" * 60)
    print(f"  {harness_name}")
    print("  Critique-Refine Loop with MCP Literature Search")
    print("=" * 60)

    run_name = args.run_name or f"run_{int(__import__('time').time())}"
    if args.recover:
        run_name = args.recover
        run_path = runs_dir / run_name
        if not run_path.exists():
            print(f"ERROR: run '{run_name}' not found for recovery")
            return
        print(f"\nRecovering from run: {run_name}")
    print(f"\nRun: {run_name}")
    print(f"Output: {output_dir}")

    # Load custom candidates
    custom_candidates = []
    if args.candidates_file:
        custom_candidates = load_custom_candidates(args.candidates_file)
        if custom_candidates:
            print(f"  Custom candidates loaded: {len(custom_candidates)}")

    # Load data
    project_id = config.get("project_id", "")
    print(f"\n[1/5] Loading data for {project_id}...")
    candidates, evidence_maps, gaps, hypotheses = load_project_data(config)

    # Merge custom candidates (prepend so they get deep-analyzed)
    if custom_candidates:
        for c in custom_candidates:
            c.setdefault("scores", {})["combined"] = c.get("scores", {}).get("combined", 0.99)
        candidates = list(custom_candidates) + candidates

    # Filter candidates
    candidates = filter_candidates(candidates, args, config, evidence_maps)
    deep_count = config.get("candidates", {}).get("deep_analysis_count", 10)
    top_10 = candidates[:deep_count]
    remaining = candidates[deep_count:]

    print(f"  Candidates: {len(candidates)} total ({len(top_10)} deep analysis, {len(remaining)} summaries)")

    # Build MCP search engine
    search_engine = None
    if not args.skip_mcp:
        from scripts.p05_harness.mcp.search_engine import SearchEngine
        mcp_cfg = config.get("mcp", {})
        search_engine = SearchEngine(
            sources=mcp_cfg.get("search_sources"),
            max_per_source=mcp_cfg.get("max_per_source", 10),
            year_range=mcp_cfg.get("year_range"),
        )
        print("  MCP search engine: ready")
    else:
        print("  MCP search: SKIPPED")

    # Run loop
    print(f"\n[2/5] Running critique-refine loop ({len(top_10)} candidates)...")
    runner = LoopRunner(config=config, output_dir=output_dir, search_engine=search_engine, run_name=run_name, skip_mcp=args.skip_mcp)

    harness_result = await runner.run(
        candidates=top_10,
        evidence_cards_by_candidate=evidence_maps,
        gaps=gaps,
        hypotheses=hypotheses,
    )

    # Add summaries for remaining candidates
    print(f"\n[3/5] Building summaries for {len(remaining)} remaining candidates...")
    add_summaries(remaining, harness_result)

    # Generate report in run directory
    print("\n[4/5] Generating acceptance report...")
    run_report_path = runs_dir / run_name / "acceptance_report.md"
    run_report_path.parent.mkdir(parents=True, exist_ok=True)
    generate_report(harness_result, run_report_path)
    print(f"  Report saved: {run_report_path}")

    # Summary
    print("\n[5/5] Done!")
    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"  {'='*60}")
    print(f"  Total candidates:    {len(harness_result.candidates)}")
    print(f"  Passed:              {harness_result.passed_count}")
    print(f"  Failed:              {harness_result.failed_count}")
    print(f"  Total LLM calls:     {harness_result.total_llm_calls}")
    print(f"  Total MCP calls:     {harness_result.total_mcp_calls}")
    print(f"  Total duration:      {harness_result.total_duration_s:.1f}s")
    if harness_result.dimension_averages:
        print(f"  Dimension averages:")
        for dim, avg in harness_result.dimension_averages.items():
            print(f"    {dim}: {avg}/5.0")
    print(f"  {'='*60}")

    # Update latest_run.txt for normal runs (not just --merge)
    latest_path = output_dir / "latest_run.txt"
    existing = set()
    if latest_path.exists():
        existing = {line.strip() for line in latest_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    existing.add(run_name)
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(existing)))

    if search_engine:
        await search_engine.close()


def load_custom_candidates(filepath: str) -> list[dict]:
    """Load custom candidates from an external JSON file."""
    path = Path(filepath)
    if not path.exists():
        print(f"  WARNING: custom candidates file not found: {path}")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("candidates", [])
    return []


def load_project_data(config: dict) -> tuple:
    """Load all project data: candidates, evidence cards, gaps, hypotheses."""
    project_id = config.get("project_id", "p05_sc_multiomics_ai")

    # Load decompose data
    decompose_path = PROJECT_ROOT / "data" / "decompose_pilot_results.json"
    candidates = []
    if decompose_path.exists():
        with open(decompose_path, encoding="utf-8") as f:
            decompose = json.load(f)
        if isinstance(decompose, dict):
            projects = decompose.get("projects", {})
            project_data = projects.get(project_id, {})
            candidates = project_data.get("candidates", [])
        elif isinstance(decompose, list):
            # Find p05 project entry by project_id, extract candidates
            entries = [d for d in decompose if d.get("project_id") == project_id]
            if entries:
                candidates = entries[0].get("candidates", [])
            else:
                candidates = []

    # Sort by combined score descending
    candidates.sort(key=lambda c: c.get("scores", {}).get("combined", 0), reverse=True)

    # Load evidence cards and group by candidate tag
    cards_path = PROJECT_ROOT / "projects" / project_id / "output" / "evidence_cards.jsonl"
    evidence_maps: dict[str, list[dict]] = {}
    if cards_path.exists():
        with open(cards_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    card = json.loads(line)
                    tags = card.get("tags", [])
                    for tag in tags:
                        if tag.startswith("candidate:"):
                            cid = tag.split("candidate:")[-1].strip()
                            evidence_maps.setdefault(cid, []).append(card)
                except json.JSONDecodeError:
                    continue

    # Load gaps
    report_path = PROJECT_ROOT / "projects" / project_id / "output" / "final_report.json"
    gaps = []
    hypotheses = []
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        gaps = report.get("gaps", [])
        hypotheses = report.get("hypotheses", [])

    return candidates, evidence_maps, gaps, hypotheses


def filter_candidates(candidates: list[dict], args, config: dict, evidence_maps: dict[str, list[dict]] = None) -> list[dict]:
    if args.candidates:
        ids = {c.strip() for c in args.candidates.split(",")}
        matched = [c for c in candidates if c.get("topic_id", c.get("research_id", c.get("id", ""))) in ids]
        unmatched = ids - {c.get("topic_id", c.get("research_id", c.get("id", ""))) for c in matched}
        if unmatched:
            print(f"  WARNING: {len(unmatched)} specified candidate IDs not found: {', '.join(sorted(unmatched))}")
        return matched

    if args.deep_only:
        deep_count = config.get("candidates", {}).get("deep_analysis_count", 10)
        return candidates[:deep_count]

    if args.max_candidates > 0:
        return candidates[:args.max_candidates]

    if evidence_maps:
        candidates = sorted(
            candidates,
            key=lambda c: (
                len(evidence_maps.get(c.get("topic_id", c.get("research_id", c.get("id", ""))), [])),
                c.get("scores", {}).get("combined", 0),
            ),
            reverse=True,
        )

    return candidates


def add_summaries(remaining: list[dict], harness_result: "HarnessResult") -> None:  # type: ignore[name-defined]
    """Add brief summaries for candidates not in deep analysis."""
    from scripts.p05_harness.loop_runner import CandidateLoopResult, HarnessResult  # noqa: F811

    for candidate in remaining:
        cid = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
        rq = candidate.get("research_question", "")
        dims = candidate.get("dimensions", {})
        method = dims.get("method", "")
        disease = dims.get("disease", "") or dims.get("disease_phenotype", "")
        scores = candidate.get("scores", {})
        combined = scores.get("combined", 0.0)
        rationale = candidate.get("rationale", "")

        summary_plan = {
            "candidate_id": cid,
            "summary_zh": rationale[:500] if rationale else f"研究方向: {rq[:300]}",
            "technical_roadmap": [],
            "data_sources_detail": [],
            "feasibility": {
                "data_accessibility": {"score": 0, "reason": "简要摘要（非深度分析）"},
                "compute_requirements": {"gpu_hours": "", "platform": "", "pretrained_available": False, "reason": ""},
                "technical_difficulty": {"score": 0, "level": "", "reason": "简要摘要"},
                "timeline_months": 0,
                "key_risks": [],
                "mitigation": [],
            },
            "innovation_points": [],
            "expected_outputs": [],
            "target_venues": [],
            "is_summary": True,
        }

        result = CandidateLoopResult(
            candidate_id=cid,
            research_question=rq,
            method=str(method),
            disease=str(disease),
            combined_score=float(combined),
            plan=summary_plan,
            passed=False,
        )
        harness_result.candidates.append(result)


def list_saved_runs(runs_dir: Path) -> None:
    if not runs_dir.exists():
        print("No runs directory found.")
        return
    runs = sorted([d.name for d in runs_dir.iterdir() if d.is_dir() and (d / "checkpoint.json").exists()])
    if not runs:
        print("No saved runs found.")
        return

    print(f"\n{'='*60}")
    print(f"  Saved Runs ({len(runs)} total)")
    print(f"  {'='*60}")
    for run_name in runs:
        cp_path = runs_dir / run_name / "checkpoint.json"
        try:
            with open(cp_path, encoding="utf-8") as f:
                data = json.load(f)
            candidates = data.get("candidates", [])
            passed = sum(1 for c in candidates if c.get("passed"))
            failed = len(candidates) - passed
            print(f"  {run_name}")
            print(f"    Candidates: {len(candidates)} ({passed} passed, {failed} failed)")
        except (json.JSONDecodeError, IOError):
            print(f"  {run_name}  (unreadable)")
    print(f"  {'='*60}")
    print(f"\n  Merge runs:  python scripts/p05_harness/main.py --merge run1,run2")
    print(f"  Recover run: python scripts/p05_harness/main.py --recover <run_name>")


def merge_runs(runs_dir: Path, run_names: list[str], output_dir: Path) -> None:
    all_candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_passed = 0
    total_failed = 0

    for run_name in run_names:
        cp_path = runs_dir / run_name / "checkpoint.json"
        if not cp_path.exists():
            print(f"  WARNING: run '{run_name}' not found, skipping")
            continue
        try:
            with open(cp_path, encoding="utf-8") as f:
                data = json.load(f)
            for c in data.get("candidates", []):
                cid = c.get("candidate_id", "")
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    all_candidates.append(c)
                    if c.get("passed"):
                        total_passed += 1
                    else:
                        total_failed += 1
        except (json.JSONDecodeError, IOError):
            print(f"  WARNING: run '{run_name}' checkpoint is corrupted, skipping")

    aggregate = {
        "passed_count": total_passed,
        "failed_count": total_failed,
        "total_llm_calls": sum(c.get("total_llm_calls", 0) for c in all_candidates),
        "total_mcp_calls": sum(c.get("total_mcp_calls", 0) for c in all_candidates),
        "total_duration_s": sum(c.get("duration_s", 0) for c in all_candidates),
        "dimension_averages": {},
        "candidates": all_candidates,
    }

    # Compute dimension averages
    dim_sums: dict[str, float] = {}
    dim_counts: dict[str, int] = {}
    for c in all_candidates:
        for it in c.get("iterations", []):
            for dim, score in it.get("scores", {}).items():
                dim_sums[dim] = dim_sums.get(dim, 0.0) + score
                dim_counts[dim] = dim_counts.get(dim, 0) + 1
    aggregate["dimension_averages"] = {
        dim: round(dim_sums[dim] / dim_counts[dim], 2) for dim in dim_sums
    }

    aggregate_path = output_dir / "harness_result.json"
    with open(aggregate_path, "w", encoding="utf-8") as f:
        json.dump(aggregate, f, ensure_ascii=False, indent=2)

    # Write latest_run.txt
    latest_path = output_dir / "latest_run.txt"
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(run_names))

    print(f"\nMerged {len(run_names)} runs → {len(all_candidates)} candidates")
    print(f"  Passed: {total_passed}, Failed: {total_failed}")
    print(f"  Aggregate saved: {aggregate_path}")
    print(f"\n  Rebuild dashboard: python dashboard/build_data.py")


if __name__ == "__main__":
    main()
