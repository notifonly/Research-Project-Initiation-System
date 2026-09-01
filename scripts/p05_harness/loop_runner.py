from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shared.core.logging_setup import get_logger

from scripts.p05_harness.domain_prompts import get_prompts
from scripts.p05_harness.mcp.search_engine import SearchEngine
from scripts.p05_harness.phases.phase1_generate import enrich_context_with_mcp, generate_initial_plan
from scripts.p05_harness.phases.phase15_novelty_verify import (
    Phase15Output,
    format_novelty_warnings,
    verify_novelty,
)
from scripts.p05_harness.phases.phase2_critique import critique_plan, search_gap_literature
from scripts.p05_harness.phases.phase3_refine import refine_plan, reposition_plan
from scripts.p05_harness.validators.citation_verifier import verify_citations
from scripts.p05_harness.validators.completeness_check import check_completeness
from scripts.p05_harness.validators.literature_check import check_literature_coverage
from scripts.p05_harness.validators.methodology_redteam import (
    RedTeamOutput,
    format_redteam_warnings,
    run_redteam,
)
from scripts.p05_harness.validators.rubric import CritiqueResult, REVIEWER_PROFILE_ORDER, RobustCritique

logger = get_logger("p05_harness.runner")


@dataclass
class CandidateEvidenceLink:
    """Explicit evidence-card-to-candidate association with relation semantics."""
    candidate_id: str
    card_id: str
    relation: str = "supports"
    relevance_score: float = 0.5
    link_method: str = "pipeline_origin"
    verification_status: str = "unverified"
    created_by_stage: str = ""
    paper_id: str = ""


RELATION_TYPES = frozenset({"supports", "contradicts", "adjacent", "prior_work", "dataset", "method"})
LINK_METHODS = frozenset({"pipeline_origin", "semantic_retrieval", "citation_graph", "manual"})


def _classify_card_relation(card: dict[str, Any], candidate: dict[str, Any]) -> str:
    """Infer relation type from card fields and candidate context.

    Uses domain-specific card fields from get_prompts().card_classify_fields
    to handle archetype-specific field names (e.g. model_family for p05,
    method_family for p08).
    """
    key = (card.get("key_finding", "") or "").lower()
    method = (candidate.get("method", "") or "").lower()
    disease = (candidate.get("disease", "") or "").lower()
    limit = (card.get("limitation_explicit", "") or "").lower()

    if limit and (method in limit or disease in limit):
        return "contradicts"
    if card.get("raw_data_accession") and not card.get("key_finding"):
        return "dataset"
    if card.get("method_brief") and not card.get("key_finding"):
        return "method"

    classify_fields = get_prompts().card_classify_fields
    if classify_fields:
        primary_field = classify_fields[0]
        card_value = (card.get(primary_field, "") or "").lower()
        candidate_value = (candidate.get("method", "") or "").lower()
        if card_value and candidate_value and card_value != candidate_value:
            return "adjacent"
    return "supports"


@dataclass
class GapEvidenceLink:
    """Explicit gap-to-card link with matched rule, weight, and rationale."""
    gap_id: str
    card_id: str
    role: str = "supporting"
    matched_fields: list[str] = field(default_factory=list)
    matched_rule: str = ""
    evidence_weight: float = 0.0
    rationale: str = ""


@dataclass
class CandidateLoopResult:
    candidate_id: str
    research_question: str = ""
    method: str = ""
    disease: str = ""
    combined_score: float = 0.0
    plan: dict[str, Any] = field(default_factory=dict)
    iterations: list[dict[str, Any]] = field(default_factory=list)
    final_critique: CritiqueResult | None = None
    evidence_link: dict[str, Any] = field(default_factory=dict)
    evidence_links: list[CandidateEvidenceLink] = field(default_factory=list)
    final_score: float = 0.0
    passed: bool = False
    completeness: dict[str, Any] = field(default_factory=dict)
    citation_checks: list[dict[str, Any]] = field(default_factory=list)
    literature_coverage: dict[str, Any] = field(default_factory=dict)
    gap_papers_found: int = 0
    total_llm_calls: int = 0
    total_mcp_calls: int = 0
    duration_s: float = 0.0
    error: str = ""
    novelty_verdict: dict[str, Any] = field(default_factory=dict)
    redteam_result: dict[str, Any] = field(default_factory=dict)
    # refine 后复验时保留初始判定（最终判定存于 novelty_verdict/redteam_result）
    novelty_verdict_initial: dict[str, Any] = field(default_factory=dict)
    redteam_result_initial: dict[str, Any] = field(default_factory=dict)
    repositioning_attempts: int = 0


@dataclass
class HarnessResult:
    candidates: list[CandidateLoopResult] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    total_llm_calls: int = 0
    total_mcp_calls: int = 0
    total_duration_s: float = 0.0
    dimension_averages: dict[str, float] = field(default_factory=dict)


class LoopRunner:
    """Core critique-refine loop controller for p05 research plan quality assurance."""

    def __init__(
        self,
        config: dict[str, Any],
        output_dir: Path,
        search_engine: SearchEngine | None = None,
        run_name: str = "",
        skip_mcp: bool = False,
    ):
        self.config = config
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.search_engine = search_engine
        self.run_name = run_name or f"run_{int(time.time())}"
        self.skip_mcp = skip_mcp

        self._runs_dir = self.output_dir / "runs" / self.run_name
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint_path = self._runs_dir / "checkpoint.json"

        loop_cfg = config.get("loop", {})
        self.max_iterations = loop_cfg.get("max_iterations", 3)
        self.pass_threshold = loop_cfg.get("pass_threshold", 4.0)
        self.max_concurrent_candidates = loop_cfg.get("max_concurrent_candidates", 1)

        self._checkpoint_lock = asyncio.Lock()
        self._result_lock = asyncio.Lock()

    def _build_candidate_links(
        self, cid: str, tagged_cards: list[dict[str, Any]], candidate: dict[str, Any]
    ) -> list[CandidateEvidenceLink]:
        links: list[CandidateEvidenceLink] = []
        seen_papers: set[str] = set()
        for card in tagged_cards:
            card_id = card.get("card_id", "")
            paper_id = card.get("paper_doi") or card.get("paper_title", "")
            if paper_id and paper_id in seen_papers:
                continue
            if paper_id:
                seen_papers.add(paper_id)
            relation = _classify_card_relation(card, candidate)
            links.append(CandidateEvidenceLink(
                candidate_id=cid,
                card_id=card_id,
                relation=relation,
                relevance_score=0.5,
                link_method="pipeline_origin",
                verification_status="unverified",
                created_by_stage="s7_extraction",
                paper_id=paper_id,
            ))
        return links

    @staticmethod
    def _count_relations(links: list[CandidateEvidenceLink]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for link in links:
            counts[link.relation] = counts.get(link.relation, 0) + 1
        return counts

    async def run(
        self,
        candidates: list[dict[str, Any]],
        evidence_cards_by_candidate: dict[str, list[dict[str, Any]]],
        gaps: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
    ) -> HarnessResult:
        t0 = time.monotonic()

        candidate_results: list[CandidateLoopResult] = []
        total_llm = 0
        total_mcp = 0

        all_cards_pool: list[dict[str, Any]] = [
            card for cards in evidence_cards_by_candidate.values() for card in cards
        ]

        completed_ids = self._load_completed_ids()

        semaphore = asyncio.Semaphore(self.max_concurrent_candidates)
        se_sources = self.config.get("mcp", {}).get("search_sources")
        se_max_per_source = self.config.get("mcp", {}).get("max_per_source", 10)
        se_year_range = self.config.get("mcp", {}).get("year_range")
        se_recent_boost = self.config.get("mcp", {}).get("recent_boost_year", 2024)

        semaphore = asyncio.Semaphore(self.max_concurrent_candidates)

        async def _run_single(idx: int, candidate: dict[str, Any]) -> None:
            nonlocal total_llm, total_mcp
            cid = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", f"T{idx:03d}")))
            if cid in completed_ids:
                logger.info(f"[LoopRunner] Skipping {idx+1}/{len(candidates)}: {cid} (already completed)")
                return

            async with semaphore:
                logger.info(f"[LoopRunner] Processing {idx+1}/{len(candidates)}: {cid}")

                tagged_cards = evidence_cards_by_candidate.get(cid, [])
                evidence_fallback = not tagged_cards and bool(all_cards_pool)
                if evidence_fallback:
                    logger.info(
                        f"[LoopRunner] {cid}: 无标签证据卡，回退到全库证据卡池 ({len(all_cards_pool)} 张)"
                    )

                evidence_links = self._build_candidate_links(cid, tagged_cards, candidate)
                # Paper-level dedup: count unique source papers per candidate
                unique_papers = set()
                for card in tagged_cards:
                    if card.get("paper_doi"):
                        unique_papers.add(card["paper_doi"])
                    elif card.get("source_paper") and isinstance(card["source_paper"], dict):
                        sp = card["source_paper"]
                        pid = sp.get("doi") or sp.get("title", "")
                        if pid:
                            unique_papers.add(pid)
                evidence_link = {
                    "linked_card_ids": [c.get("card_id", "") for c in tagged_cards[:20] if c.get("card_id")],
                    "linked_card_count": len(tagged_cards),
                    "unique_paper_count": len(unique_papers),
                    "evidence_pool_size": len(all_cards_pool),
                    "evidence_source": "fallback_pool" if evidence_fallback else "tagged",
                    "relation_counts": LoopRunner._count_relations(evidence_links),
                }

                # Per-candidate search engine (skip when MCP disabled)
                candidate_se = None
                if not self.skip_mcp:
                    candidate_se = SearchEngine(
                        sources=se_sources,
                        max_per_source=se_max_per_source,
                        year_range=se_year_range,
                        recent_boost_year=se_recent_boost,
                    )

                result = await self._process_candidate(
                    candidate,
                    tagged_cards or all_cards_pool,
                    gaps,
                    hypotheses,
                    evidence_fallback=evidence_fallback,
                    evidence_link=evidence_link,
                    search_engine=candidate_se,
                )
                result.evidence_links = evidence_links

                async with self._result_lock:
                    candidate_results.append(result)
                    total_llm += result.total_llm_calls
                    total_mcp += result.total_mcp_calls

                async with self._checkpoint_lock:
                    self._append_checkpoint(result)

        tasks = [_run_single(i, c) for i, c in enumerate(candidates)]
        await asyncio.gather(*tasks)

        # Restore original order
        order_map = {r.candidate_id: r for r in candidate_results}
        candidate_results = [order_map.get(
            c.get("topic_id", c.get("research_id", c.get("id", f"T{i:03d}"))),
            CandidateLoopResult(candidate_id=f"T{i:03d}", error="skipped or missing")
        ) for i, c in enumerate(candidates)]
        candidate_results = [r for r in candidate_results if r]

        # Compute dimension averages
        dim_sums: dict[str, float] = {}
        dim_counts: dict[str, int] = {}
        for cr in candidate_results:
            if cr.final_critique:
                for dim, score in cr.final_critique.scores.items():
                    dim_sums[dim] = dim_sums.get(dim, 0.0) + score
                    dim_counts[dim] = dim_counts.get(dim, 0) + 1

        dimension_averages = {
            dim: round(dim_sums[dim] / dim_counts[dim], 2) for dim in dim_sums
        }

        harness_result = HarnessResult(
            candidates=candidate_results,
            passed_count=sum(1 for r in candidate_results if r.passed),
            failed_count=sum(1 for r in candidate_results if not r.passed),
            total_llm_calls=total_llm,
            total_mcp_calls=total_mcp,
            total_duration_s=round(time.monotonic() - t0, 1),
            dimension_averages=dimension_averages,
        )

        self._save_results(harness_result)
        return harness_result

    async def _process_candidate(
        self,
        candidate: dict[str, Any],
        evidence_cards: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        evidence_fallback: bool = False,
        evidence_link: dict[str, Any] | None = None,
        search_engine: Any = None,
    ) -> CandidateLoopResult:
        se = search_engine if search_engine is not None else self.search_engine
        cid = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
        rq = candidate.get("research_question", "")
        dims = candidate.get("dimensions", {})
        method = dims.get("method", "")
        disease = dims.get("disease", "") or dims.get("disease_phenotype", "")
        scores = candidate.get("scores", {})
        combined = scores.get("combined", 0.0)

        result = CandidateLoopResult(
            candidate_id=cid,
            research_question=rq,
            method=str(method),
            disease=str(disease),
            combined_score=float(combined),
            evidence_link=evidence_link or {},
        )

        t_start = time.monotonic()
        llm_calls = 0
        mcp_calls = 0

        def mcp_ops() -> int:
            """当前 MCP 操作总数（检索 + 直查），用于差值计数避免重复累计。"""
            if not se:
                return 0
            return se.search_calls + se.lookup_calls

        try:
            # Phase 0: MCP context enrichment
            mcp_context = ""
            if se:
                _mcp_before = mcp_ops()
                mcp_context = await enrich_context_with_mcp(candidate, se)
                mcp_calls += mcp_ops() - _mcp_before

            # Phase 1: Generate initial plan
            plan = await generate_initial_plan(
                candidate, evidence_cards, gaps, hypotheses, mcp_context
            )
            llm_calls += 1

            # Completeness check on initial plan
            completeness = check_completeness(plan)
            result.completeness = {
                "missing_fields": completeness.missing_fields,
                "empty_fields": completeness.empty_fields,
                "issues_count": completeness.issues_count,
                "is_complete": completeness.is_complete,
            }

            # Phase 1.5: 对抗性新颖性验证（核心新环节）
            phase15_output = Phase15Output()
            redteam_output = RedTeamOutput()
            if se:
                _mcp_before = mcp_ops()
                phase15_output = await verify_novelty(
                    plan, candidate, se, self.config
                )
                mcp_calls += mcp_ops() - _mcp_before
                llm_calls += 3  # claims extraction + query generation + overlap judge

                result.novelty_verdict = self._novelty_dict(phase15_output)

                # 阻断逻辑: scooped → 强制重定位
                if phase15_output.overall_verdict == "scooped":
                    reposition_limit = self.config.get("novelty_check", {}).get("reposition_max_attempts", 1)
                    for attempt in range(reposition_limit):
                        result.repositioning_attempts = attempt + 1
                        logger.warning(
                            f"[LoopRunner] {cid}: SCOOPED, repositioning attempt {attempt+1}/{reposition_limit}"
                        )
                        plan = await reposition_plan(plan, phase15_output, candidate)
                        llm_calls += 1

                        # 重定位后重新验证
                        _mcp_before = mcp_ops()
                        phase15_output = await verify_novelty(
                            plan, candidate, se, self.config
                        )
                        mcp_calls += mcp_ops() - _mcp_before
                        llm_calls += 3
                        result.novelty_verdict = self._novelty_dict(
                            phase15_output, repositioning_attempts=attempt + 1
                        )

                        if phase15_output.overall_verdict != "scooped":
                            break

                    if phase15_output.overall_verdict == "scooped":
                        result.error = "scooped: 方案核心新颖性已被已有工作否定，重定位后未能通过验证"
                        result.passed = False
                        cw = phase15_output.verdicts[0].get("closest_works", []) if phase15_output.verdicts else []
                        cw_titles = [w.get("title", "?")[:60] for w in cw[:3]]
                        result.error += f" | closest works: {'; '.join(cw_titles)}"
                        return result

                # Phase 1.6: 方法论红队评审（复用 Phase 1.5 检索结果）
                _mcp_before = mcp_ops()
                redteam_output = await run_redteam(
                    plan, candidate, se,
                    evidence_cards, phase15_output.papers_found
                )
                mcp_calls += mcp_ops() - _mcp_before
                llm_calls += 2  # methodology review + data claim verify

                result.redteam_result = self._redteam_dict(redteam_output)

            # Pre-critique citation verification
            # 仅用方法名作检索关键词（疾病名会污染查询；方法名与引用论文强相关，命中率最高）
            # method 字段常带括号引用（如 "scGPT (Cui et al., 2024)"），先清理
            _kw_method = re.sub(r"\([^)]*\)", "", str(method)).strip()
            context_keywords = _kw_method
            verified_refs: list = []
            hallucinated_refs: list = []
            unverifiable_refs: list = []
            if se and plan:
                _mcp_before = mcp_ops()
                pre_citation_results = await verify_citations(
                    plan, se, context_keywords=context_keywords
                )
                mcp_calls += mcp_ops() - _mcp_before
                verified_refs = [cr for cr in pre_citation_results if cr.exists]
                hallucinated_refs = [cr for cr in pre_citation_results if cr.status == "not_found"]
                unverifiable_refs = [cr for cr in pre_citation_results if cr.status == "unverifiable"]
                if hallucinated_refs or unverifiable_refs:
                    logger.warning(
                        f"[LoopRunner] {cid}: {len(hallucinated_refs)} suspected-hallucinated + "
                        f"{len(unverifiable_refs)} unverifiable citations pre-critique, "
                        f"{len(verified_refs)} verified"
                    )
            else:
                verified_refs = []
                hallucinated_refs = []
                unverifiable_refs = []

            # Build combined warnings for critique phase
            novelty_warnings_text = format_novelty_warnings(phase15_output) if phase15_output.overall_verdict != "clear" else ""
            redteam_warnings_text = format_redteam_warnings(redteam_output)
            combined_warnings: list[str] = [
                f"Suspected hallucinated reference (verify or remove): {cr.display or cr.doi or cr.pmid or 'unknown'}"
                for cr in hallucinated_refs
            ] if hallucinated_refs else []
            if unverifiable_refs:
                combined_warnings.extend(
                    f"Unverifiable reference (double-check accession/identifier): {cr.display or 'unknown'}"
                    for cr in unverifiable_refs
                )
            if novelty_warnings_text:
                combined_warnings.append(novelty_warnings_text)
            if redteam_warnings_text:
                combined_warnings.append(redteam_warnings_text)

            # Loop: Critique -> Gap Search -> Refine
            current_plan = plan
            best_plan = plan
            best_score = 0.0
            best_critique: CritiqueResult | None = None
            stagnation_count = 0
            prev_weighted = -1.0
            stagnation_limit = self.config.get("loop", {}).get("stagnation_limit", 2)
            for iteration in range(self.max_iterations):
                # Phase 2: Critique (with pre-verified citation warnings + novelty + redteam)
                cite_warnings = combined_warnings if combined_warnings else None
                critique = await critique_plan(
                    candidate, current_plan, iteration, self.pass_threshold,
                    cite_warnings,
                    novelty_verdicts=phase15_output.verdicts if phase15_output.overall_verdict != "clear" else None,
                    redteam_findings=[{"check": f.check, "severity": f.severity, "detail": f.detail, "suggestion": f.suggestion} for f in redteam_output.findings] if redteam_output.findings else None,
                )
                llm_calls += 1

                # 将新颖性验证和红队评审结果附到 CritiqueResult
                if phase15_output.overall_verdict != "clear":
                    critique.novelty_verdicts = phase15_output.verdicts
                if redteam_output.findings:
                    critique.redteam_findings = [
                        {"check": f.check, "severity": f.severity, "detail": f.detail}
                        for f in redteam_output.findings
                    ]

                # Robust critique: for edge candidates, run 3 critiques with different reviewer profiles
                if iteration == 0 and RobustCritique.is_edge_candidate(critique.weighted_score):
                    extra_critiques = [critique]
                    profiles = REVIEWER_PROFILE_ORDER[:RobustCritique.N_REPEATS]
                    for i in range(1, RobustCritique.N_REPEATS):
                        profile = profiles[i] if i < len(profiles) else "generalist"
                        ec = await critique_plan(
                            candidate, current_plan, iteration, self.pass_threshold,
                            cite_warnings,
                            novelty_verdicts=phase15_output.verdicts if phase15_output.overall_verdict != "clear" else None,
                            redteam_findings=[{"check": f.check, "severity": f.severity, "detail": f.detail, "suggestion": f.suggestion} for f in redteam_output.findings] if redteam_output.findings else None,
                            reviewer_profile=profile,
                        )
                        llm_calls += 1
                        extra_critiques.append(ec)
                    critique, stability = RobustCritique.aggregate(extra_critiques, self.pass_threshold)
                    logger.info(
                        f"[LoopRunner] {cid}: edge candidate (first={extra_critiques[0].weighted_score}), "
                        f"robust median={critique.weighted_score} stability={stability} "
                        f"reviewers={[r.reviewer_profile for r in extra_critiques]}"
                    )

                # Track best plan (highest weighted score wins)
                if critique.weighted_score > best_score:
                    best_score = critique.weighted_score
                    best_plan = current_plan
                    best_critique = critique

                iter_record = {
                    "iteration": iteration,
                    "scores": critique.scores,
                    "weighted_score": critique.weighted_score,
                    "passed": critique.passed,
                    "literature_gaps": critique.literature_gaps,
                }
                result.iterations.append(iter_record)

                result.final_critique = critique
                result.final_score = critique.weighted_score

                if critique.passed:
                    result.passed = True
                    break

                # Stagnation check: if score hasn't improved, bail out
                if prev_weighted >= 0:
                    if abs(critique.weighted_score - prev_weighted) < 0.05:
                        stagnation_count += 1
                    else:
                        stagnation_count = 0
                prev_weighted = critique.weighted_score
                if stagnation_count >= stagnation_limit:
                    logger.info(
                        f"[LoopRunner] Stagnation at iter={iteration}: score={critique.weighted_score} "
                        f"unchanged for {stagnation_count} rounds, stopping early"
                    )
                    break

                # Literature gap search (MCP)
                if critique.literature_gaps and se:
                    _mcp_before = mcp_ops()
                    new_papers = await search_gap_literature(critique, candidate, se)
                    mcp_calls += mcp_ops() - _mcp_before
                    result.gap_papers_found += len(new_papers)
                else:
                    new_papers = []

                # Phase 3: Refine
                if iteration < self.max_iterations - 1:
                    current_plan = await refine_plan(current_plan, critique, new_papers, candidate)
                    llm_calls += 1

            # Deliver best plan, not last plan
            result.plan = best_plan
            result.final_score = best_score
            if best_critique is not None:
                result.final_critique = best_critique

            # Post-loop re-verification: Phase 1.5/1.6 针对的是初始方案，
            # refine 可能改变了数据源、基线与声明，需对最终交付方案复验，
            # 保证 novelty_verdict / redteam_result 反映的是交付方案而非过时结论。
            if se and best_plan is not plan:
                logger.info(
                    f"[LoopRunner] {cid}: plan changed during refine, "
                    f"re-running novelty + redteam verification on final plan"
                )
                _mcp_before = mcp_ops()
                final_phase15 = await verify_novelty(
                    best_plan, candidate, se, self.config
                )
                mcp_calls += mcp_ops() - _mcp_before
                llm_calls += 3

                _mcp_before = mcp_ops()
                final_redteam = await run_redteam(
                    best_plan, candidate, se,
                    evidence_cards, final_phase15.papers_found
                )
                mcp_calls += mcp_ops() - _mcp_before
                llm_calls += 2

                # 保留初始判定，最终判定作为对外展示结论
                result.novelty_verdict_initial = result.novelty_verdict
                result.redteam_result_initial = result.redteam_result
                result.novelty_verdict = self._novelty_dict(
                    final_phase15,
                    repositioning_attempts=result.repositioning_attempts,
                    reverified=True,
                )
                result.redteam_result = self._redteam_dict(final_redteam, reverified=True)

                if final_phase15.overall_verdict == "scooped":
                    logger.warning(
                        f"[LoopRunner] {cid}: final plan judged SCOOPED in re-verification"
                    )
                    result.error = (
                        "scooped_post_refine: refine 后方案被复验判定为 scooped，"
                        "建议人工审阅重定位"
                    )

            # Citation verification (on the delivered best plan)
            if se and result.plan:
                _mcp_before = mcp_ops()
                citation_results = await verify_citations(
                    result.plan, se, context_keywords=context_keywords
                )
                result.citation_checks = [
                    {
                        "ref_type": cr.ref_type,
                        "display": cr.display,
                        "doi": cr.doi,
                        "pmid": cr.pmid,
                        "accession": cr.accession,
                        "exists": cr.exists,
                        "status": cr.status,
                        "verified_title": cr.verified_title,
                        "error": cr.error,
                    }
                    for cr in citation_results
                ]
                mcp_calls += mcp_ops() - _mcp_before

            # Literature coverage check (on the delivered best plan)
            lit_coverage = check_literature_coverage(cid, result.plan, evidence_cards)
            result.literature_coverage = {
                "evidence_card_count": lit_coverage.evidence_card_count,
                "cited_paper_count": lit_coverage.cited_paper_count,
                "overlapping_count": lit_coverage.overlapping_count,
                "coverage_ratio": lit_coverage.coverage_ratio,
                "status": lit_coverage.status,
                "evidence_source": "fallback_pool" if evidence_fallback else "tagged",
            }

        except Exception as e:
            logger.error(f"[LoopRunner] Candidate {cid} failed: {e}")
            result.error = str(e)

        result.total_llm_calls = llm_calls
        result.total_mcp_calls = mcp_calls
        result.duration_s = round(time.monotonic() - t_start, 1)

        logger.info(
            f"[LoopRunner] {cid}: score={result.final_score} passed={result.passed} "
            f"llm={llm_calls} mcp={mcp_calls} @ {result.duration_s}s"
        )
        return result

    @staticmethod
    def _novelty_dict(
        output: Phase15Output,
        repositioning_attempts: int = 0,
        reverified: bool = False,
    ) -> dict[str, Any]:
        d: dict[str, Any] = {
            "overall_verdict": output.overall_verdict,
            "verdicts": output.verdicts,
            "papers_found": len(output.papers_found),
            "repositioning_required": output.repositioning_required,
        }
        if repositioning_attempts:
            d["repositioning_attempts"] = repositioning_attempts
        if reverified:
            d["reverified_post_refine"] = True
        return d

    @staticmethod
    def _redteam_dict(output: RedTeamOutput, reverified: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "findings": [
                {"check": f.check, "severity": f.severity, "detail": f.detail}
                for f in output.findings
            ],
            "high_count": output.high_count,
            "medium_count": output.medium_count,
            "low_count": output.low_count,
            "verified_claims": len(output.verified_claims),
            "unverified_claims": [
                {"claim_text": c["claim_text"], "status": c["status"]}
                for c in output.unverified_claims
            ],
        }
        if reverified:
            d["reverified_post_refine"] = True
        return d

    def _load_completed_ids(self) -> set[str]:
        if not self._checkpoint_path.exists():
            return set()
        try:
            with open(self._checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
            return {cr.get("candidate_id", "") for cr in data.get("candidates", [])}
        except (json.JSONDecodeError, IOError):
            return set()

    def _append_checkpoint(self, result: CandidateLoopResult) -> None:
        existing: list[dict[str, Any]] = []
        if self._checkpoint_path.exists():
            try:
                with open(self._checkpoint_path, encoding="utf-8") as f:
                    data = json.load(f)
                existing = data.get("candidates", [])
            except (json.JSONDecodeError, IOError):
                pass

        existing.append(self._candidate_to_dict(result))
        with open(self._checkpoint_path, "w", encoding="utf-8") as f:
            json.dump({"candidates": existing}, f, ensure_ascii=False, indent=2)

    def _candidate_to_dict(self, cr: CandidateLoopResult) -> dict[str, Any]:
        return {
            "candidate_id": cr.candidate_id,
            "research_question": cr.research_question,
            "method": cr.method,
            "disease": cr.disease,
            "combined_score": cr.combined_score,
            "final_score": cr.final_score,
            "passed": cr.passed,
            "iterations": cr.iterations,
            "final_critique": cr.final_critique.to_dict() if cr.final_critique else None,
            "completeness": cr.completeness,
            "citation_checks": cr.citation_checks,
            "literature_coverage": cr.literature_coverage,
            "gap_papers_found": cr.gap_papers_found,
            "total_llm_calls": cr.total_llm_calls,
            "total_mcp_calls": cr.total_mcp_calls,
            "duration_s": cr.duration_s,
            "error": cr.error,
            "plan": cr.plan,
            "novelty_verdict": cr.novelty_verdict,
            "redteam_result": cr.redteam_result,
                "novelty_verdict_initial": cr.novelty_verdict_initial,
                "redteam_result_initial": cr.redteam_result_initial,
                "repositioning_attempts": cr.repositioning_attempts,
                "evidence_link": cr.evidence_link,
            }

    def _save_results(self, result: HarnessResult) -> None:
        """Save results to run directory and update aggregate."""
        # Save to run-specific directory
        run_result_path = self._runs_dir / "harness_result.json"
        harness_data = self._harness_to_dict(result)
        with open(run_result_path, "w", encoding="utf-8") as f:
            json.dump(harness_data, f, ensure_ascii=False, indent=2)

        # Final enriched plans (dashboard-compatible) in run dir
        enriched = []
        for cr in result.candidates:
            plan = cr.plan.copy() if cr.plan else {}
            plan.update({
                "candidate_id": cr.candidate_id,
                "research_question": cr.research_question,
                "method": cr.method,
                "disease": cr.disease,
                "combined_score": cr.combined_score,
                "final_score": cr.final_score,
                "passed": cr.passed,
                "iterations": cr.iterations,
                "literature_coverage": cr.literature_coverage,
            })
            enriched.append(plan)

        enriched_path = self._runs_dir / "p05_final_enriched.json"
        with open(enriched_path, "w", encoding="utf-8") as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[LoopRunner] Saved results: {len(result.candidates)} candidates, "
            f"{result.passed_count} passed, {result.failed_count} failed → {self._runs_dir}"
        )

    def _harness_to_dict(self, result: HarnessResult) -> dict[str, Any]:
        return {
            "passed_count": result.passed_count,
            "failed_count": result.failed_count,
            "total_llm_calls": result.total_llm_calls,
            "total_mcp_calls": result.total_mcp_calls,
            "total_duration_s": result.total_duration_s,
            "dimension_averages": result.dimension_averages,
            "candidates": [self._candidate_to_dict(cr) for cr in result.candidates],
        }
