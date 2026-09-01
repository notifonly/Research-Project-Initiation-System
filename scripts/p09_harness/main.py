#!/usr/bin/env python3
"""P09 scGWAS × Spatial Transcriptomics Network Module Discovery Harness — Entry Point.

Thin wrapper around the shared harness core (scripts/p05_harness/).
Sets p09-specific domain prompts, config, and output paths.

Single focused candidate: scGWAS dual-weight module search applied to spatial
transcriptomics microdomain GSS scores.

Usage:
    python scripts/p09_harness/main.py                         # Run on single candidate
    python scripts/p09_harness/main.py --run-name run_v1       # Named run
    python scripts/p09_harness/main.py --skip-mcp              # LLM only, no literature search
    python scripts/p09_harness/main.py --merge run_v1,run_v2   # Merge saved runs
    python scripts/p09_harness/main.py --merge                 # Merge all saved runs into dashboard
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
    parser = argparse.ArgumentParser(description="P09 scGWAS × Spatial Transcriptomics Research Plan Quality Harness")
    parser.add_argument("--deep-only", action="store_true", help="Only deep analysis")
    parser.add_argument("--max-candidates", type=int, default=0, help="Max candidates to process")
    parser.add_argument("--candidates", type=str, default="", help="Comma-separated candidate IDs")
    parser.add_argument("--candidates-file", type=str, default="", help="JSON file with custom candidates to merge")
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

    from scripts.p09_harness.domain_prompts import P09_DOMAIN_PROMPTS
    from scripts.p05_harness.domain_prompts import set_prompts
    set_prompts(P09_DOMAIN_PROMPTS)

    asyncio.run(run_harness(args))


async def run_harness(args) -> None:
    from scripts.p05_harness.domain_prompts import get_prompts
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

    output_dir = PROJECT_ROOT / config.get("output", {}).get("dir", "data/p09_harness_output")
    if args.output_dir:
        output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    if args.list_runs:
        from scripts.p05_harness.main import list_saved_runs
        list_saved_runs(runs_dir)
        return

    if args.merge:
        from scripts.p05_harness.main import merge_runs
        run_names = [r.strip() for r in args.merge.split(",") if r.strip()]
        merge_runs(runs_dir, run_names, output_dir)
        return

    prompts = get_prompts()
    harness_name = prompts.harness_name
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

    custom_candidates = []
    if args.candidates_file:
        from scripts.p05_harness.main import load_custom_candidates
        custom_candidates = load_custom_candidates(args.candidates_file)
        if custom_candidates:
            print(f"  Custom candidates loaded: {len(custom_candidates)}")

    project_id = config.get("project_id", "")
    print(f"\n[1/5] Loading data for {project_id}...")
    candidates, evidence_maps, gaps, hypotheses = load_project_data(config)

    if custom_candidates:
        for c in custom_candidates:
            c.setdefault("scores", {})["combined"] = c.get("scores", {}).get("combined", 0.99)
        candidates = list(custom_candidates) + candidates

    candidates = filter_candidates(candidates, args, config, evidence_maps)
    deep_count = config.get("candidates", {}).get("deep_analysis_count", 1)
    top_n = candidates[:deep_count]
    remaining = candidates[deep_count:]

    if not top_n:
        print(f"\n  No candidates to process. Are there candidates for {project_id} in decompose_pilot_results.json?")
        print(f"  To inject the seeded candidate, add a decomposition entry or use --candidates-file.")
        return

    print(f"  Candidates: {len(candidates)} total ({len(top_n)} deep analysis, {len(remaining)} summaries)")

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

    print(f"\n[2/5] Running critique-refine loop ({len(top_n)} candidates)...")
    runner = LoopRunner(config=config, output_dir=output_dir, search_engine=search_engine, run_name=run_name, skip_mcp=args.skip_mcp)

    harness_result = await runner.run(
        candidates=top_n,
        evidence_cards_by_candidate=evidence_maps,
        gaps=gaps,
        hypotheses=hypotheses,
    )

    print(f"\n[3/5] Building summaries for {len(remaining)} remaining candidates...")
    from scripts.p05_harness.main import add_summaries
    add_summaries(remaining, harness_result)

    print("\n[4/5] Generating acceptance report...")
    run_report_path = runs_dir / run_name / "acceptance_report.md"
    run_report_path.parent.mkdir(parents=True, exist_ok=True)
    generate_report(harness_result, run_report_path)
    print(f"  Report saved: {run_report_path}")

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

    latest_path = output_dir / "latest_run.txt"
    existing = set()
    if latest_path.exists():
        existing = {line.strip() for line in latest_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    existing.add(run_name)
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(existing)))

    if search_engine:
        await search_engine.close()


def load_project_data(config: dict) -> tuple:
    """Load all project data: candidates, evidence cards, gaps, hypotheses."""
    project_id = config.get("project_id", "p09_spatial_gwas_network")

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
            entries = [d for d in decompose if d.get("project_id") == project_id]
            if entries:
                candidates = entries[0].get("candidates", [])
            else:
                candidates = []

    candidates.sort(key=lambda c: c.get("scores", {}).get("combined", 0), reverse=True)

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

    report_path = PROJECT_ROOT / "projects" / project_id / "output" / "final_report.json"
    gaps = []
    hypotheses = []
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        gaps = report.get("gaps", [])
        hypotheses = report.get("hypotheses", [])

    # If no candidates from decompose, inject the seeded candidate from project config
    if not candidates:
        project_cfg_path = PROJECT_ROOT / "projects" / project_id / "config.yaml"
        if project_cfg_path.exists():
            import yaml
            with open(project_cfg_path, encoding="utf-8") as f:
                pcfg = yaml.safe_load(f)
            seeded = pcfg.get("seeded_candidate")
            if seeded:
                candidates = [seeded]

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
        deep_count = config.get("candidates", {}).get("deep_analysis_count", 1)
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


if __name__ == "__main__":
    main()
