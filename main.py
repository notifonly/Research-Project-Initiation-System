"""AIscience main entry point.

Runs all 7 research-direction sub-projects in parallel via asyncio.gather.
Each project runs an independent Orchestrator with its own loop_flow. A global
semaphore caps concurrent MCP API calls across all projects. After all projects
converge, a cross-archetype gap scan post-phase runs to surface bridge gaps.

Usage:
    python main.py                  # run all 7 projects in parallel
    python main.py --only p01_gwas_perturb_seq,p04_prs_advance   # run a subset (use full project keys)
    python main.py --breakpoints    # enable human breakpoints
    python main.py --no-cross-scan  # skip cross-archetype gap scan
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.table import Table

from shared.core.config import settings
from shared.core.logging_setup import get_logger, setup_logging
from shared.core.orchestrator import ProjectResult
from projects import ARCHETYPE_MAP, PROJECTS

console = Console()
logger = get_logger("main")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AIscience: parallel bioinformatics research-direction agent")
    p.add_argument("--only", type=str, default="", help="comma-separated project ids to run (default: all)")
    p.add_argument("--breakpoints", action="store_true", help="enable human breakpoints")
    p.add_argument("--no-cross-scan", action="store_true", help="skip cross-archetype gap scan post-phase")
    p.add_argument("--mcp-concurrency", type=int, default=settings.mcp_concurrency, help="global MCP API concurrency")
    return p.parse_args()


async def _run_one(
    project_id: str,
    run_fn,
    global_semaphore: asyncio.Semaphore,
    breakpoint_handler: Any,
) -> ProjectResult:
    setup_logging(project_id)
    t0 = time.monotonic()
    logger.info(f"[{project_id}] starting")
    try:
        result = await run_fn(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)
        logger.info(
            f"[{project_id}] done success={result.success} converged={result.converged} "
            f"cards={result.total_cards} gaps={len(result.gaps)} hyp={len(result.hypotheses)} "
            f"dur={time.monotonic()-t0:.1f}s"
        )
        return result
    except Exception as e:
        logger.error(f"[{project_id}] crashed: {e}")
        return ProjectResult(
            project_id=project_id,
            archetype_id=ARCHETYPE_MAP.get(project_id, "unknown"),
            success=False,
            error=str(e),
            duration_s=time.monotonic() - t0,
        )


async def _cross_archetype_gap_scan(results: list[ProjectResult]) -> dict[str, Any]:
    """Post-phase: surface gaps that bridge archetypes (P10 cross_archetype_bridge)."""
    logger.info("=== Cross-archetype gap scan (post-phase) ===")
    all_gaps: list[dict[str, Any]] = []
    for r in results:
        for g in r.gaps:
            if isinstance(g, dict):
                g2 = dict(g)
                g2["_source_project"] = r.project_id
                g2["_source_archetype"] = r.archetype_id
                all_gaps.append(g2)

    archetype_gap_counts: dict[str, int] = {}
    for g in all_gaps:
        arch = g.get("_source_archetype", "unknown")
        archetype_gap_counts[arch] = archetype_gap_counts.get(arch, 0) + 1

    bridge_gaps: list[dict[str, Any]] = []
    seen_patterns: dict[str, list[str]] = {}
    for g in all_gaps:
        pat = g.get("pattern_id") or g.get("pattern") or g.get("gap_type") or "unknown"
        seen_patterns.setdefault(pat, []).append(g.get("_source_project", ""))
    for pat, projs in seen_patterns.items():
        if len(set(projs)) > 1:
            bridge_gaps.append({
                "pattern_id": pat,
                "appears_in_projects": sorted(set(projs)),
                "count": len(projs),
            })

    scan = {
        "total_gaps": len(all_gaps),
        "archetype_gap_counts": archetype_gap_counts,
        "cross_archetype_bridge_gaps": bridge_gaps,
        "shared_patterns": {k: v for k, v in seen_patterns.items() if len(set(v)) > 1},
    }
    scan_path = settings.data_dir / "cross_archetype_gap_scan.json"
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    scan_path.write_text(json.dumps(scan, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info(f"Cross-archetype scan: {len(all_gaps)} total gaps, {len(bridge_gaps)} bridge patterns -> {scan_path}")
    return scan


def _print_summary_table(results: list[ProjectResult], total_duration: float) -> None:
    table = Table(title=f"AIscience results ({total_duration:.1f}s)")
    table.add_column("Project", style="cyan")
    table.add_column("Archetype", style="magenta")
    table.add_column("OK", justify="center")
    table.add_column("Conv", justify="center")
    table.add_column("Cards", justify="right")
    table.add_column("Gaps", justify="right")
    table.add_column("Hyp", justify="right")
    table.add_column("Dur(s)", justify="right")
    for r in results:
        table.add_row(
            r.project_id,
            r.archetype_id,
            "Y" if r.success else "N",
            "Y" if r.converged else "N",
            str(r.total_cards),
            str(len(r.gaps)),
            str(len(r.hypotheses)),
            f"{r.duration_s:.1f}",
        )
    console.print(table)


def _save_combined_report(results: list[ProjectResult], total_duration: float, cross_scan: Optional[dict]) -> None:
    report = {
        "total_duration_s": round(total_duration, 2),
        "projects_run": len(results),
        "projects_succeeded": sum(1 for r in results if r.success),
        "projects_converged": sum(1 for r in results if r.converged),
        "total_cards": sum(r.total_cards for r in results),
        "total_gaps": sum(len(r.gaps) for r in results),
        "total_hypotheses": sum(len(r.hypotheses) for r in results),
        "results": [_result_to_dict(r) for r in results],
    }
    if cross_scan:
        report["cross_archetype_gap_scan"] = cross_scan
    out_path = settings.data_dir / "run_all_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    console.print(f"\n[bold green]Combined report saved to {out_path}[/bold green]")


def _result_to_dict(r: ProjectResult) -> dict[str, Any]:
    d = asdict(r)
    d.pop("coverage_summary", None)
    d["gap_count"] = len(r.gaps)
    d["hypothesis_count"] = len(r.hypotheses)
    d["coverage_cells"] = r.coverage_summary.get("total_cells", 0) if isinstance(r.coverage_summary, dict) else 0
    return d


async def run_all(
    project_ids: Optional[list[str]] = None,
    enable_breakpoints: bool = False,
    cross_scan: bool = True,
    mcp_concurrency: Optional[int] = None,
) -> list[ProjectResult]:
    settings.ensure_dirs()
    if project_ids is None:
        project_ids = list(PROJECTS.keys())
    else:
        project_ids = [p for p in project_ids if p in PROJECTS]

    concurrency = mcp_concurrency or settings.mcp_concurrency
    global_semaphore = asyncio.Semaphore(concurrency)
    breakpoint_handler: Any = None
    if enable_breakpoints or settings.enable_breakpoints:
        breakpoint_handler = _console_breakpoint_handler

    console.print(f"[bold]AIscience[/bold] running {len(project_ids)} projects in parallel "
                  f"(MCP concurrency={concurrency})")
    console.print(f"  projects: {', '.join(project_ids)}")

    t0 = time.monotonic()
    tasks = [
        _run_one(pid, PROJECTS[pid], global_semaphore, breakpoint_handler)
        for pid in project_ids
    ]
    results = await asyncio.gather(*tasks)
    total_duration = time.monotonic() - t0

    _print_summary_table(results, total_duration)

    cs = None
    if cross_scan:
        cs = await _cross_archetype_gap_scan(results)

    _save_combined_report(results, total_duration, cs)
    return results


def _console_breakpoint_handler(event: Any) -> Any:
    console.print(f"\n[yellow]BREAKPOINT[/yellow] {event.bp_type} @ {event.step_name} (project={event.project_id})")
    console.print(f"  data: {json.dumps(event.data, ensure_ascii=False, default=str)[:300]}")
    event.decision = "continue"
    return event


def main() -> None:
    args = _parse_args()
    only = [s.strip() for s in args.only.split(",") if s.strip()] or None
    asyncio.run(run_all(
        project_ids=only,
        enable_breakpoints=args.breakpoints,
        cross_scan=not args.no_cross_scan,
        mcp_concurrency=args.mcp_concurrency,
    ))


if __name__ == "__main__":
    main()
