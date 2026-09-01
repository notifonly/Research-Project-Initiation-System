from __future__ import annotations

import json
from typing import Any

from shared.core.llm_client import llm_complete
from shared.core.logging_setup import get_logger

from scripts.p05_harness.mcp.query_generator import generate_search_queries
from scripts.p05_harness.mcp.search_engine import SearchEngine
from scripts.p05_harness.validators.rubric import (
    CRITIQUE_SYSTEM_PROMPT,
    REVIEWER_PROFILES,
    CritiqueResult,
    build_critique_prompt,
    get_rubric,
)

logger = get_logger("p05_harness.phase2")


async def critique_plan(
    candidate: dict[str, Any],
    plan: dict[str, Any],
    iteration: int = 0,
    pass_threshold: float = 4.0,
    citation_warnings: list[str] | None = None,
    novelty_verdicts: list[dict[str, Any]] | None = None,
    redteam_findings: list[dict[str, Any]] | None = None,
    reviewer_profile: str = "generalist",
) -> CritiqueResult:
    """Phase 2: LLM critique of a research plan against the rubric."""
    candidate_id = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
    plan_json = _format_plan_for_critique(plan)
    candidate_info = _format_candidate_for_critique(candidate, citation_warnings)

    prompt = build_critique_prompt(
        plan_json, candidate_info, candidate,
        novelty_verdicts=novelty_verdicts,
        redteam_findings=redteam_findings,
        reviewer_profile=reviewer_profile,
        plan=plan,
    )

    system_prompt = REVIEWER_PROFILES.get(reviewer_profile, CRITIQUE_SYSTEM_PROMPT)

    try:
        raw = await llm_complete(
            prompt,
            system=system_prompt,
            temperature=0.2,
            max_tokens=4000,
        )
        rubric = get_rubric(candidate)
        result = CritiqueResult.from_llm_response(candidate_id, iteration, raw, pass_threshold, candidate, rubric, reviewer_profile=reviewer_profile)
        logger.info(
            f"[Phase2] Critique {candidate_id} iter={iteration}: "
            f"weighted={result.weighted_score} passed={result.passed} "
            f"gaps={len(result.literature_gaps)} profile={reviewer_profile}"
        )
        return result
    except Exception as e:
        logger.error(f"[Phase2] Critique failed for {candidate_id}: {e}")
        return CritiqueResult(candidate_id=candidate_id, iteration=iteration, weighted_score=-1.0, passed=False, critique_text=f"LLM FAILED: {e}", reviewer_profile=reviewer_profile)


async def search_gap_literature(
    critique_result: CritiqueResult,
    candidate: dict[str, Any],
    search_engine: SearchEngine,
) -> list[dict[str, Any]]:
    """If critique identifies literature gaps, run MCP searches to fill them."""
    if not critique_result.literature_gaps:
        return []

    method = candidate.get("dimensions", {}).get("method", "")
    disease = candidate.get("dimensions", {}).get("disease", "") or candidate.get(
        "dimensions", {}
    ).get("disease_phenotype", "")
    if isinstance(disease, dict):
        disease = disease.get("name", str(disease))
    rq = candidate.get("research_question", "")

    # Generate search queries from critique gaps
    gap_queries = await generate_search_queries(
        critique_text=critique_result.critique_text,
        research_question=rq,
        method=str(method),
        disease=str(disease),
    )

    all_papers: list[dict[str, Any]] = []
    for gq in (gap_queries or []):
        queries = gq.get("queries", [])
        for q in queries:
            papers = await search_engine.search(q, max_per_source=5)
            all_papers.extend(papers)

    # Deduplicate and take top 10
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in all_papers:
        title = (p.get("title") or "").strip().lower()
        if title and title not in seen:
            seen.add(title)
            unique.append(p)
    unique.sort(key=lambda p: p.get("citation_count") or 0, reverse=True)

    logger.info(
        f"[Phase2] Gap search: {len(gap_queries)} gap topics, {len(unique)} unique papers found"
    )
    return unique[:10]


def _format_plan_for_critique(plan: dict[str, Any]) -> str:
    critique_fields = {
        "summary_zh": plan.get("summary_zh", ""),
        "technical_roadmap": _format_roadmap(plan.get("technical_roadmap", [])),
        "data_sources_detail": plan.get("data_sources_detail", []),
        "feasibility": plan.get("feasibility", {}),
        "innovation_points": plan.get("innovation_points", []),
        "expected_outputs": plan.get("expected_outputs", []),
        "target_venues": plan.get("target_venues", []),
    }
    return json.dumps(critique_fields, ensure_ascii=False, indent=2)


def _format_roadmap(roadmap: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "step": s.get("step", i + 1),
            "title": s.get("title", ""),
            "desc": s.get("desc", ""),
            "methods": s.get("methods", ""),
            "weeks": s.get("weeks", ""),
            "tools": s.get("tools", []),
        }
        for i, s in enumerate(roadmap or [])
    ]


def _format_candidate_for_critique(candidate: dict[str, Any], citation_warnings: list[str] | None = None) -> str:
    dims = candidate.get("dimensions", {})
    scores = candidate.get("scores", {})
    rq = candidate.get("research_question", "")
    info: dict[str, Any] = {
        "research_question": rq,
        "dimensions": dims,
        "original_scores": scores,
    }
    if citation_warnings:
        info["citation_warnings"] = citation_warnings
    return json.dumps(info, ensure_ascii=False, indent=2)
