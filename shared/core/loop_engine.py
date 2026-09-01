from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Type

from shared.core.checkpoint import Checkpoint, CheckpointManager, CheckpointState
from shared.core.config import settings
from shared.core.harness import BreakpointType, Harness
from shared.core.logging_setup import get_logger
from shared.evidence.base_card import BaseEvidenceCard
from shared.evidence.coverage_matrix import CoverageCell, CoverageMatrix
from shared.skills.skill_06b_pdf_download import PDFDownloadOutput

from shared.skills.base_skill import SkillInput

if TYPE_CHECKING:
    from shared.skills.base_skill import BaseSkill, SkillOutput


class InnerConvergenceReason(str, Enum):
    QUERY_EXHAUSTED = "query_exhausted"
    CITATION_CLOSED = "citation_closed"
    REFLECTION_CONFIRMED = "reflection_confirmed"
    BUDGET_TOKEN_EXCEEDED = "budget_token_exceeded"
    MAX_ITERATIONS = "max_iterations"
    TOPIC_EXHAUSTED = "topic_exhausted"


class OuterConvergenceReason(str, Enum):
    COVERAGE_JACCARD = "coverage_jaccard_converged"
    GAP_YIELD = "gap_yield_below_threshold"
    CITATION_NETWORK_CLOSED = "citation_network_closed"
    ALL_MET = "all_criteria_met"
    MAX_ROUNDS = "max_rounds"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class InnerLoopResult:
    iteration: int
    converged: bool
    reason: Optional[InnerConvergenceReason] = None
    cards_added: int = 0
    queries_run: int = 0
    new_citations: int = 0
    skill_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    download_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class OuterLoopResult:
    round_idx: int
    converged: bool
    reasons: list[OuterConvergenceReason] = field(default_factory=list)
    inner_results: list[InnerLoopResult] = field(default_factory=list)
    coverage_jaccard: float = 0.0
    gap_yield: float = 0.0
    total_cards: int = 0
    citation_network_closed: bool = False
    final_coverage_summary: dict[str, Any] = field(default_factory=dict)
    final_gaps: list[dict[str, Any]] = field(default_factory=list)
    final_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    budget_snapshot: dict[str, Any] = field(default_factory=dict)


class LoopEngine:
    """Drives the inner (discovery+extraction) and outer (coverage convergence) loops.

    Skill sequence is split into phases:
    - Scoping: run once at start (S1, S2, [S3 for archetype A])
    - Inner loop: discovery + extraction (S4-S9, [S10 for A]) — repeats until inner OR convergence
    - Synthesis: S11, S12 — run after inner loop converges

    Outer loop repeats [inner loop + synthesis] until outer AND convergence:
    coverage Jaccard > threshold for K rounds, gap yield < threshold, citation network closed.
    """

    SCOPING_SKILL_PREFIXES = {"s1_", "s2_", "s3_"}
    SYNTHESIS_SKILLS = {"s11_gap_analysis", "s12_hypothesis_generate"}

    def __init__(
        self,
        project_id: str,
        skill_sequence: list[str],
        skill_instances: dict[str, BaseSkill],
        harness: Harness,
        checkpoint_mgr: CheckpointManager,
        coverage_matrix: CoverageMatrix,
        convergence_config: dict[str, Any],
        max_inner_iterations: int = 7,
        max_outer_rounds: int = 5,
        evidence_card_class: Optional[Type[BaseEvidenceCard]] = None,
    ) -> None:
        self.project_id = project_id
        self.skill_sequence = skill_sequence
        self.skill_instances = skill_instances
        self.harness = harness
        self.checkpoint_mgr = checkpoint_mgr
        self.coverage_matrix = coverage_matrix
        self.convergence_config = convergence_config
        self.max_inner_iterations = max_inner_iterations
        self.max_outer_rounds = max_outer_rounds
        self.evidence_card_class = evidence_card_class
        self.logger = get_logger(project_id)

        self._previous_coverage: Optional[CoverageMatrix] = None
        self._previous_gap_count: int = 0
        self._citation_network: set[str] = set()
        self._all_queries: set[str] = set()
        self._inner_reflection_confirmed: bool = False
        self._jaccard_history: list[float] = []

        self._candidate_driven: bool = bool(convergence_config.get("candidate_driven", False))
        self._candidates: list[dict[str, Any]] = []
        self._candidate_idx: int = 0
        self._current_candidate: Optional[dict[str, Any]] = None
        self._candidate_progress: dict[str, dict[str, Any]] = {}

    def _split_phases(self) -> tuple[list[str], list[str], list[str]]:
        scoping: list[str] = []
        inner: list[str] = []
        synthesis: list[str] = []
        for sid in self.skill_sequence:
            prefix = sid[:3] if len(sid) >= 3 else sid
            if prefix in self.SCOPING_SKILL_PREFIXES:
                scoping.append(sid)
            elif sid in self.SYNTHESIS_SKILLS:
                synthesis.append(sid)
            else:
                inner.append(sid)
        return scoping, inner, synthesis

    async def run(self, initial_input: SkillInput) -> OuterLoopResult:
        scoping, inner, synthesis = self._split_phases()
        all_inner_results: list[InnerLoopResult] = []
        last_outer_reasons: list[OuterConvergenceReason] = []

        scoped_input = await self._run_scoping(scoping, initial_input)

        if self._candidate_driven:
            self._candidates = self._load_candidates()
            self._candidate_idx = 0
            if self._candidates:
                self.logger.info(
                    f"Candidate-driven mode: loaded {len(self._candidates)} topics "
                    f"(max_candidates={self.convergence_config.get('max_candidates', 20)})"
                )
            else:
                self.logger.warning("Candidate-driven mode enabled but no candidates found, falling back to standard loop")

        round_idx = 0
        for round_idx in range(self.max_outer_rounds):
            self.logger.info(f"=== Outer loop round {round_idx + 1}/{self.max_outer_rounds} ===")
            self._previous_coverage = self._clone_coverage()
            self._previous_gap_count = self._count_gaps()

            inner_result = await self._run_inner_loop(inner, round_idx, scoped_input)
            all_inner_results.append(inner_result)

            if self.harness.budget.exhausted:
                last_outer_reasons = [OuterConvergenceReason.BUDGET_EXHAUSTED]
                self.logger.warning("Budget exhausted, stopping outer loop")
                break

            synth_result = await self._run_synthesis(synthesis, round_idx)
            if synth_result is None:
                last_outer_reasons = [OuterConvergenceReason.BUDGET_EXHAUSTED]
                break

            converged, reasons = self._check_outer_convergence(round_idx)
            last_outer_reasons = reasons
            if converged:
                self.logger.info(f"Outer loop converged at round {round_idx + 1}: {[r.value for r in reasons]}")
                break

            if round_idx == self.max_outer_rounds - 1:
                last_outer_reasons = [OuterConvergenceReason.MAX_ROUNDS]
                self.logger.info(f"Outer loop reached max rounds ({self.max_outer_rounds})")

        result = OuterLoopResult(
            round_idx=round_idx,
            converged=any(r == OuterConvergenceReason.ALL_MET for r in last_outer_reasons),
            reasons=last_outer_reasons,
            inner_results=all_inner_results,
            coverage_jaccard=self._jaccard_history[-1] if self._jaccard_history else 0.0,
            total_cards=self.harness.card_store.count(),
            citation_network_closed=self._is_citation_network_closed(),
            budget_snapshot=self.harness.budget.snapshot(),
        )
        result.final_coverage_summary = self.coverage_matrix.summary()
        result.final_gaps = self._extract_gaps_from_l2()
        result.final_hypotheses = self._extract_hypotheses_from_l2()
        return result

    async def _run_scoping(self, scoping_skills: list[str], initial_input: SkillInput) -> SkillInput:
        current_input = initial_input
        for sid in scoping_skills:
            skill = self.skill_instances.get(sid)
            if skill is None:
                self.logger.warning(f"Scoping skill {sid} not found, skipping")
                continue
            if self.checkpoint_mgr.is_step_done(sid):
                self.logger.info(f"Scoping skill {sid} already checkpointed, skipping")
                self._restore_from_checkpoint(sid, current_input)
                continue

            self.logger.info(f"Running scoping skill: {sid}")
            self.harness.budget.set_phase(skill.budget_phase)
            prepared_input = self._prepare_skill_input(sid, current_input)
            result = await self.harness.run_skill(skill, prepared_input, timeout_s=180.0)
            if result.success and result.output:
                current_input = self._propagate_output(result.output, sid, current_input)
                self._checkpoint_step(sid, result.output, 0)
                if sid == "s1_direction_decompose":
                    self.harness.fire_breakpoint(
                        BreakpointType.BP1_DIRECTION_DECOMPOSE, sid,
                        data=result.output.metrics,
                    )
                elif sid in ("s2_terminology_normalize", "s3_v2g_locus_collect"):
                    self.harness.fire_breakpoint(
                        BreakpointType.BP2_LOCUS_TERMINOLOGY, sid,
                        data=result.output.metrics,
                    )
            else:
                self.logger.error(f"Scoping skill {sid} failed: {result.error}")
                self._checkpoint_step(sid, result.output, 0, state=CheckpointState.FAILED)

        return current_input

    async def _run_inner_loop(
        self,
        inner_skills: list[str],
        round_idx: int,
        initial_input: SkillInput,
    ) -> InnerLoopResult:
        if self._candidate_driven and self._candidates:
            return await self._run_candidate_driven_loop(inner_skills, round_idx, initial_input)
        return await self._run_standard_loop(inner_skills, round_idx, initial_input)

    async def _run_standard_loop(
        self,
        inner_skills: list[str],
        round_idx: int,
        initial_input: SkillInput,
    ) -> InnerLoopResult:
        result = InnerLoopResult(iteration=0, converged=False)
        current_input = initial_input

        for iteration in range(self.max_inner_iterations):
            result.iteration = iteration
            self.logger.info(f"--- Inner loop iteration {iteration + 1}/{self.max_inner_iterations} (round {round_idx + 1}) ---")
            self._inner_reflection_confirmed = False
            cards_before = self.harness.card_store.count()

            for sid in inner_skills:
                skill = self.skill_instances.get(sid)
                if skill is None:
                    self.logger.warning(f"Inner loop skill {sid} not found, skipping")
                    continue
                self.harness.budget.set_phase(skill.budget_phase)
                self.logger.info(f"  Running skill: {sid}")
                prepared_input = self._prepare_skill_input(sid, current_input)
                store_keys_before = (
                    self.harness.card_store.dedup_keys()
                    if sid == "s7_evidence_card_extract" and self.harness.card_store is not None
                    else None
                )
                sub_result = await self.harness.run_skill(skill, prepared_input, timeout_s=120.0)
                result.queries_run += 1
                if sub_result.success and sub_result.output:
                    current_input = self._propagate_output(sub_result.output, sid, current_input)
                    result.skill_outputs[sid] = sub_result.output.model_dump()
                    if sid == "s7_evidence_card_extract":
                        self._run_provenance_on_new_cards()
                        new_cards: list[BaseEvidenceCard] = sub_result.output.cards if hasattr(sub_result.output, 'cards') else []  # type: ignore[assignment]
                        for card in new_cards:
                            try:
                                if store_keys_before is None or \
                                        self.harness.card_store.key_for_card(card) not in store_keys_before:
                                    self.coverage_matrix.add_card(card)
                            except Exception:
                                pass
                        quality = self._compute_card_quality_metrics(new_cards)
                        if quality:
                            result.skill_outputs[f"{sid}_quality"] = quality
                    if sid == "s5_citation_snowball":
                        new_cites = sub_result.output.metrics.get("new_citations", 0)
                        result.new_citations += new_cites
                    if sid == "s6b_pdf_download":
                        dl_rate = sub_result.output.metrics.get("success_rate", 0)
                        dl_count = sub_result.output.metrics.get("downloaded", 0)
                        self.logger.info(f"  PDF download: {dl_count} succeeded ({dl_rate:.0%})")
                        result.download_stats = {
                            "success_rate": dl_rate,
                            "downloaded": dl_count,
                            "total_chars": sub_result.output.metrics.get("total_chars", 0),
                        }
                else:
                    # S6b failure is non-fatal — pass through kept papers for S7 abstract-only
                    if sid == "s6b_pdf_download":
                        self.logger.warning(f"  PDF download failed (non-fatal): {sub_result.error}")
                        result.errors.append(f"{sid}: {sub_result.error}")
                        result.download_stats = {"success_rate": 0.0, "downloaded": 0, "total_chars": 0}
                        kept_papers = current_input.model_dump().get("kept", []) if current_input else []
                        fallback = PDFDownloadOutput(
                            skill_name="s6b_pdf_download",
                            papers_with_fulltext=kept_papers or [],
                            success=False,
                            error=sub_result.error,
                        )
                        current_input = self._propagate_output(fallback, sid, current_input)
                    else:
                        result.errors.append(f"{sid}: {sub_result.error}")
                        self.logger.warning(f"  Skill {sid} failed: {sub_result.error}")

                if self.harness.budget.exhausted or self.harness.budget.current_phase_exhausted:
                    result.converged = True
                    result.reason = InnerConvergenceReason.BUDGET_TOKEN_EXCEEDED
                    self.logger.info("Inner loop converged: budget exceeded")
                    break

            result.cards_added = self.harness.card_store.count() - cards_before

            if self.harness.budget.exhausted:
                result.converged = True
                result.reason = InnerConvergenceReason.BUDGET_TOKEN_EXCEEDED
                break

            reason = self._check_inner_convergence(result, iteration)
            if reason is not None:
                result.converged = True
                result.reason = reason
                self.logger.info(f"Inner loop converged: {reason.value}")
                break

            if iteration == self.max_inner_iterations - 1:
                result.converged = True
                result.reason = InnerConvergenceReason.MAX_ITERATIONS
                self.logger.info(f"Inner loop reached max iterations ({self.max_inner_iterations})")

        self._checkpoint_inner_round(round_idx, result)
        self.harness.fire_breakpoint(
            BreakpointType.BP4_READING_LIST, "inner_loop",
            data={"round": round_idx, "cards": self.harness.card_store.count()},
        )
        return result

    async def _run_synthesis(self, synthesis_skills: list[str], round_idx: int) -> Optional[bool]:
        current_input = SkillInput()
        prev_outputs = self.harness.context.l2.snapshot()
        if prev_outputs:
            current_input = SkillInput.model_validate(
                {k: v for k, v in prev_outputs.items() if isinstance(v, (str, int, float, list, dict, bool))}
            ) if _is_dict_like(prev_outputs) else SkillInput()
        # Inject research_direction and archetype from S1 checkpoint or initial input
        current_input = self._inject_synthesis_context(current_input)

        for sid in synthesis_skills:
            skill = self.skill_instances.get(sid)
            if skill is None:
                self.logger.warning(f"Synthesis skill {sid} not found, skipping")
                continue
            if self.harness.budget.exhausted:
                return None
            self.harness.budget.set_phase(skill.budget_phase)
            self.logger.info(f"Running synthesis skill: {sid}")
            prepared_input = self._prepare_skill_input(sid, current_input)
            result = await self.harness.run_skill(skill, prepared_input, timeout_s=180.0)
            if result.success and result.output:
                current_input = self._propagate_output(result.output, sid, current_input)
                self._checkpoint_step(sid, result.output, round_idx)
                if sid == "s11_gap_analysis":
                    # Coverage quality check before gap analysis
                    coverage_quality = self._check_coverage_quality()
                    if coverage_quality:
                        result.output = result.output.model_copy(update={
                            "metrics": {**(result.output.metrics or {}), "coverage_quality": coverage_quality}
                        })
                    gaps_data = [g.model_dump() if hasattr(g, "model_dump") else g
                                 for g in getattr(result.output, "gaps", [])]
                    self.harness.context.warm_to_l2("identified_gaps", gaps_data)
                    self.harness.fire_breakpoint(
                        BreakpointType.BP6_GAP_HYPOTHESIS, sid,
                        data=result.output.metrics,
                    )
                if sid == "s12_hypothesis_generate":
                    hyp_data = [h.model_dump() if hasattr(h, "model_dump") else h
                                for h in getattr(result.output, "hypotheses", [])]
                    self.harness.context.warm_to_l2("hypotheses", hyp_data)
            else:
                self.logger.error(f"Synthesis skill {sid} failed: {result.error}")
                self._checkpoint_step(sid, result.output, round_idx, state=CheckpointState.FAILED)

        return True

    def _load_candidates(self) -> list[dict[str, Any]]:
        import json
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[2]
        decompose_path = project_root / "data" / "decompose_pilot_results.json"
        if not decompose_path.exists():
            self.logger.warning(f"Decompose data not found: {decompose_path}")
            return []
        try:
            raw = json.loads(decompose_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Failed to load decompose data: {e}")
            return []

        for entry in raw:
            if entry.get("project_id") == self.project_id:
                candidates = entry.get("candidates", [])
                min_score = self.convergence_config.get("min_candidate_score", 0)
                filtered = [
                    c for c in candidates
                    if isinstance(c, dict)
                    and max(
                        c.get("combined_score", 0),
                        (c.get("scores") or {}).get("combined", 0),
                    ) >= min_score
                ]
                order = self.convergence_config.get("candidate_order", "score_desc")
                if order == "shuffle":
                    random.shuffle(filtered)
                    return filtered
                return sorted(
                    filtered,
                    key=lambda c: (
                        max(
                            c.get("combined_score", 0),
                            (c.get("scores") or {}).get("combined", 0),
                        ),
                        c.get("novelty_score", 0),
                    ),
                    reverse=True,
                )
        self.logger.info(f"No decompose candidates found for project {self.project_id}")
        return []

    @staticmethod
    def _build_candidate_queries(candidate: dict[str, Any]) -> list[str]:
        dims = candidate.get("dimensions", {}) or {}
        # Collect all non-empty dimension values into parts for query stitching
        parts: list[str] = []
        for key in dims:
            val = dims.get(key, "")
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
            elif isinstance(val, list):
                parts.extend([str(v).strip() for v in val if str(v).strip()])
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_parts = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                unique_parts.append(p)
        parts = unique_parts
        structured = " ".join(parts) if parts else ""
        queries: list[str] = []
        if structured:
            queries.append(structured)
        for dim in parts:
            if dim and dim != structured and dim not in queries:
                queries.append(dim)
        rq = candidate.get("research_question", "")
        if rq and rq not in queries:
            queries.append(rq)
        sq = candidate.get("search_query", "")
        if sq and sq != structured and sq not in queries:
            queries.append(sq)
        return queries[:8]

    async def _rewrite_candidate_queries(self, candidate: dict[str, Any]) -> list[str]:
        import json as _json

        from shared.core.llm_client import llm_complete
        from shared.core.token_budget import BudgetPhase

        dims = candidate.get("dimensions", {}) or {}
        rq = candidate.get("research_question", "")

        # Build dimension summary dynamically from all available dimension fields
        dim_lines = []
        for key, val in dims.items():
            label = key.replace("_", " ")
            if isinstance(val, str):
                dim_lines.append(f"{label}: {val}")
            elif isinstance(val, list):
                dim_lines.append(f"{label}: {', '.join(str(v) for v in val)}")
        dims_text = "; ".join(dim_lines) if dim_lines else str(dims)

        prompt = (
            f"Research topic: {rq}\n"
            f"Dimensions: {dims_text}\n\n"
            "Generate 3-5 PubMed/Semantic Scholar search queries with varying scope:\n"
            "- 1-2 broad queries: use only the key method/technique names\n"
            "- 1-2 medium queries: combine 2-3 dimension values\n"
            "- 1 narrow query: combine multiple dimension values for specificity\n"
            "Avoid queries that are so specific they return zero results. "
            'Return JSON: {"queries": [...]}'
        )

        try:
            raw = await llm_complete(
                prompt,
                system="You are a literature search query generator for bioinformatics research.",
                budget=self.harness.budget,
                phase=BudgetPhase.EXTRACTION,
                temperature=0.3,
                max_tokens=200,
                response_format=dict,
            )
            parsed = _json.loads(raw)
            queries = parsed.get("queries", [])
            if isinstance(queries, list) and queries:
                return queries[:5]
        except Exception as e:
            self.logger.warning(f"LLM query rewrite failed: {e}, falling back to dimension stitching")

        return self._build_candidate_queries(candidate)

    async def _run_candidate_driven_loop(
        self,
        inner_skills: list[str],
        round_idx: int,
        initial_input: SkillInput,
    ) -> InnerLoopResult:
        result = InnerLoopResult(iteration=0, converged=False)
        max_candidates = self.convergence_config.get("max_candidates", 20)
        end_idx = min(len(self._candidates), max_candidates)

        self.logger.info(
            f"Candidate-driven inner loop: {end_idx} candidates "
            f"(round {round_idx + 1})"
        )

        cards_before_total = self.harness.card_store.count()
        idx: int = 0

        for idx in range(end_idx):
            candidate = self._candidates[idx]
            self._current_candidate = candidate
            topic_id = candidate.get("topic_id", f"candidate_{idx}")

            prev_progress = self._candidate_progress.get(topic_id)
            if prev_progress is not None and prev_progress.get("cards_added", 0) == 0:
                exhaust_count = prev_progress.get("exhaust_count", 0) + 1
                self._candidate_progress[topic_id]["exhaust_count"] = exhaust_count
                if exhaust_count >= 3:
                    self.logger.info(
                        f"--- Candidate {idx + 1}/{end_idx}: {topic_id} "
                        f"(exhausted {exhaust_count} rounds, skipping) ---"
                    )
                    continue
                self.logger.info(
                    f"--- Candidate {idx + 1}/{end_idx}: {topic_id} "
                    f"(exhaust count={exhaust_count}, retrying with fresh search) ---"
                )

            cached_progress = self._candidate_progress.get(topic_id, {})
            s4_round_key = f"s4_papers_r{round_idx}"
            if cached_progress.get(s4_round_key):
                self.logger.info(
                    f"--- Candidate {idx + 1}/{end_idx}: {topic_id} "
                    f"(already processed this round, reusing S4 cache) ---"
                )

            current_input = initial_input

            cards_before = self.harness.card_store.count()
            cand_score = max(candidate.get("combined_score", 0), (candidate.get("scores") or {}).get("combined", 0))
            self.logger.info(
                f"--- Candidate {idx + 1}/{end_idx}: {topic_id} "
                f"(score={cand_score:.1f}) ---"
            )

            if not self._candidate_progress.get(topic_id, {}).get("llm_queries"):
                llm_queries = await self._rewrite_candidate_queries(candidate)
                self._candidate_progress.setdefault(topic_id, {})["llm_queries"] = llm_queries
                self.logger.info(f"  LLM rewrote {len(llm_queries)} queries: {llm_queries[0][:60]}...")

            for sid in inner_skills:
                skill = self.skill_instances.get(sid)
                if skill is None:
                    self.logger.warning(f"Inner loop skill {sid} not found, skipping")
                    continue

                if sid.startswith("s4_"):
                    round_key = f"s4_papers_r{round_idx}"
                    cached = self._candidate_progress.get(topic_id, {})
                    if cached.get(round_key):
                        self.logger.info(f"  S4: reusing {len(cached[round_key])} cached papers from round {round_idx}")
                        from shared.skills.skill_04_multi_source_search import MultiSourceSearchOutput
                        fake_output = MultiSourceSearchOutput(
                            papers=cached[round_key],
                            deduplicated_count=cached.get(f"{round_key}_dedup", 0),
                        )
                        current_input = self._propagate_output(fake_output, sid, current_input)
                        continue

                self.harness.budget.set_phase(skill.budget_phase)
                prepared_input = self._prepare_skill_input(sid, current_input)

                scratch: dict[str, Any] = {}
                if sid.startswith("s7_"):
                    scratch["_candidate_topic_id"] = topic_id

                store_keys_before = (
                    self.harness.card_store.dedup_keys()
                    if sid == "s7_evidence_card_extract" and self.harness.card_store is not None
                    else None
                )
                sub_result = await self.harness.run_skill(
                    skill, prepared_input,
                    scratch=scratch,
                    timeout_s=120.0,
                )
                result.queries_run += 1
                if sub_result.success and sub_result.output:
                    current_input = self._propagate_output(sub_result.output, sid, current_input)
                    result.skill_outputs[sid] = sub_result.output.model_dump()
                    if sid == "s4_multi_source_search":
                        dumped = sub_result.output.model_dump()
                        cached = self._candidate_progress.setdefault(topic_id, {})
                        round_key = f"s4_papers_r{round_idx}"
                        cached[round_key] = dumped.get("papers", [])
                        cached[f"{round_key}_dedup"] = dumped.get("deduplicated_count", 0)
                        # Also keep backward-compatible keys for intra-round reuse
                        cached["s4_papers"] = dumped.get("papers", [])
                        cached["s4_deduplicated_count"] = dumped.get("deduplicated_count", 0)
                    if sid == "s7_evidence_card_extract":
                        self._run_provenance_on_new_cards()
                        for card in (sub_result.output.cards if hasattr(sub_result.output, 'cards') else []):
                            try:
                                # 仅当卡片真正新增入库（未被去重跳过）才计入覆盖矩阵
                                if store_keys_before is None or \
                                        self.harness.card_store.key_for_card(card) not in store_keys_before:
                                    self.coverage_matrix.add_card(card)
                            except Exception:
                                pass
                    if sid == "s5_citation_snowball":
                        new_cites = sub_result.output.metrics.get("new_citations", 0)
                        result.new_citations += new_cites
                    if sid == "s6b_pdf_download":
                        dl_rate = sub_result.output.metrics.get("success_rate", 0)
                        dl_count = sub_result.output.metrics.get("downloaded", 0)
                        self.logger.info(f"  PDF download: {dl_count} succeeded ({dl_rate:.0%})")
                        result.download_stats = {
                            "success_rate": dl_rate,
                            "downloaded": dl_count,
                            "total_chars": sub_result.output.metrics.get("total_chars", 0),
                        }
                else:
                    if sid == "s6b_pdf_download":
                        self.logger.warning(f"  PDF download failed (non-fatal): {sub_result.error}")
                        result.errors.append(f"{sid}: {sub_result.error}")
                        result.download_stats = {"success_rate": 0.0, "downloaded": 0, "total_chars": 0}
                        kept_papers = current_input.model_dump().get("kept", []) if current_input else []
                        fallback = PDFDownloadOutput(
                            skill_name="s6b_pdf_download",
                            papers_with_fulltext=kept_papers or [],
                            success=False,
                            error=sub_result.error,
                        )
                        current_input = self._propagate_output(fallback, sid, current_input)
                    else:
                        result.errors.append(f"{sid}: {sub_result.error}")
                        self.logger.warning(f"  Skill {sid} failed: {sub_result.error}")
                        if sid.startswith("s4_"):
                            self.logger.warning(f"  Abandoning candidate {topic_id} (S4 failed, no papers)")
                            break

                if self.harness.budget.exhausted or self.harness.budget.current_phase_exhausted:
                    result.converged = True
                    result.reason = InnerConvergenceReason.BUDGET_TOKEN_EXCEEDED
                    self.logger.info("Inner loop converged: budget exceeded")
                    break

            cards_added = self.harness.card_store.count() - cards_before
            result.cards_added += cards_added
            prev = self._candidate_progress.get(topic_id, {})
            self._candidate_progress[topic_id] = {
                "idx": idx,
                "cards_added": cards_added,
                "combined_score": candidate.get("combined_score", 0),
                "lit_count": candidate.get("literature_count", 0),
                "llm_queries": prev.get("llm_queries", []),
                "s4_papers": prev.get("s4_papers", []),
                "s4_deduplicated_count": prev.get("s4_deduplicated_count", 0),
            }
            self._checkpoint_candidate(round_idx, idx, topic_id, cards_added)
            self.logger.info(
                f"  Candidate {topic_id}: {cards_added} cards "
                f"(score={candidate.get('combined_score', 0):.1f}, lit={candidate.get('literature_count', 0)})"
            )

            if self.harness.budget.exhausted:
                result.converged = True
                result.reason = InnerConvergenceReason.BUDGET_TOKEN_EXCEEDED
                break

        if idx + 1 >= end_idx and not result.converged:
            result.converged = True
            result.reason = InnerConvergenceReason.TOPIC_EXHAUSTED
            self.logger.info(f"Inner loop converged: all {end_idx} topics exhausted")

        self._checkpoint_inner_round(round_idx, result)
        self.harness.fire_breakpoint(
            BreakpointType.BP4_READING_LIST, "inner_loop",
            data={"round": round_idx, "cards": self.harness.card_store.count(), "candidates": end_idx},
        )
        return result

    def _checkpoint_candidate(self, round_idx: int, idx: int, topic_id: str, cards_added: int) -> None:
        if not settings.enable_checkpoint:
            return
        try:
            cp = Checkpoint(
                project_id=self.project_id,
                step_name=f"r{round_idx}_candidate_{idx}_{topic_id}",
                step_index=idx,
                state=CheckpointState.COMPLETED,
                context_snapshot=self.harness.context.l2.snapshot(),
                token_usage=self.harness.budget.snapshot(),
                metadata={"topic_id": topic_id, "cards_added": cards_added},
            )
            self.checkpoint_mgr.save(cp)
        except Exception as e:
            self.logger.warning(f"Candidate checkpoint save failed for {topic_id}: {e}")

    def _check_inner_convergence(self, result: InnerLoopResult, iteration: int) -> Optional[InnerConvergenceReason]:
        if result.cards_added == 0 and result.new_citations == 0:
            if iteration > 0:
                return InnerConvergenceReason.QUERY_EXHAUSTED
        if result.new_citations == 0 and iteration > 0:
            self._citation_network.update(
                self._extract_cited_dois_from_l2()
            )
            return InnerConvergenceReason.CITATION_CLOSED
        if self._inner_reflection_confirmed:
            return InnerConvergenceReason.REFLECTION_CONFIRMED
        return None

    def _check_outer_convergence(self, round_idx: int) -> tuple[bool, list[OuterConvergenceReason]]:
        reasons: list[OuterConvergenceReason] = []
        current_keys = self.coverage_matrix.occupied_keys()

        jaccard = 0.0
        if self._previous_coverage is not None:
            jaccard = self.coverage_matrix.jaccard(self._previous_coverage)
        self._jaccard_history.append(jaccard)

        threshold = self.convergence_config.get("coverage_jaccard_threshold", settings.coverage_jaccard_threshold)
        k = self.convergence_config.get("outer_loop_k", settings.outer_loop_k)
        jaccard_converged = (
            len(self._jaccard_history) >= k
            and all(j >= threshold for j in self._jaccard_history[-k:])
        )
        if jaccard_converged:
            reasons.append(OuterConvergenceReason.COVERAGE_JACCARD)

        current_gap_count = self._count_gaps()
        gap_threshold = self.convergence_config.get("gap_yield_threshold", settings.gap_yield_threshold)
        gap_yield_ratio = 1.0
        if self._previous_gap_count > 0:
            gap_yield_ratio = max(0, self._previous_gap_count - current_gap_count) / self._previous_gap_count
        new_gap_ratio = current_gap_count / max(1, len(current_keys))
        if new_gap_ratio < gap_threshold or gap_yield_ratio < gap_threshold:
            reasons.append(OuterConvergenceReason.GAP_YIELD)

        citation_closed = self._is_citation_network_closed()
        if citation_closed:
            reasons.append(OuterConvergenceReason.CITATION_NETWORK_CLOSED)

        self.logger.info(
            f"Outer convergence check: jaccard={jaccard:.3f} (need {threshold} for {k} rounds), "
            f"gap_ratio={new_gap_ratio:.3f} gap_yield={gap_yield_ratio:.3f} (need < {gap_threshold}), "
            f"citation_closed={citation_closed}"
        )

        outer_and = self.convergence_config.get("outer_loop_and", [])
        required_count = len(outer_and) if outer_and else 3
        if len(reasons) >= required_count:
            return True, [OuterConvergenceReason.ALL_MET]
        return False, reasons

    def _count_gaps(self) -> int:
        gaps = self._extract_gaps_from_l2()
        return len(gaps)

    def _extract_gaps_from_l2(self) -> list[dict[str, Any]]:
        gaps_data = self.harness.context.l2.get("identified_gaps", [])
        if isinstance(gaps_data, list):
            return gaps_data
        return []

    def _extract_hypotheses_from_l2(self) -> list[dict[str, Any]]:
        hyp_data = self.harness.context.l2.get("hypotheses", [])
        if isinstance(hyp_data, list):
            return hyp_data
        return []

    def _extract_cited_dois_from_l2(self) -> set[str]:
        reading_list = self.harness.context.l2.get("reading_list", [])
        dois: set[str] = set()
        if isinstance(reading_list, list):
            for item in reading_list:
                if isinstance(item, dict):
                    doi = item.get("doi")
                    if doi:
                        dois.add(doi)
        return dois

    def _is_citation_network_closed(self) -> bool:
        cited = self._extract_cited_dois_from_l2()
        if not cited:
            return False
        self._citation_network.update(cited)
        return len(self._citation_network) > 0 and self.harness.card_store.count() > 0

    def _inject_synthesis_context(self, current_input: SkillInput) -> SkillInput:
        data = current_input.model_dump()
        l2 = self.harness.context.l2.snapshot()
        if not data.get("research_direction"):
            from_s1 = l2.get("last_output_s1_direction_decompose", l2.get("output_s1_direction_decompose", {}))
            if isinstance(from_s1, dict):
                data["research_direction"] = from_s1.get("research_direction", "")
        if not data.get("archetype"):
            from_s1 = l2.get("last_output_s1_direction_decompose", l2.get("output_s1_direction_decompose", {}))
            if isinstance(from_s1, dict):
                data["archetype"] = from_s1.get("archetype", "")
            if not data.get("archetype") and self.evidence_card_class:
                arch_field = self.evidence_card_class.model_fields.get("archetype")
                if arch_field is not None and hasattr(arch_field, "default"):
                    data["archetype"] = arch_field.default or ""
        return SkillInput.model_validate(data)

    def _clone_coverage(self) -> CoverageMatrix:
        clone = CoverageMatrix(axes=list(self.coverage_matrix.AXES))
        for key, cell in self.coverage_matrix.all_cells().items():
            clone._cells[key] = CoverageCell(
                card_count=cell.card_count,
                has_fine_mapping=cell.has_fine_mapping,
                has_colocalization=cell.has_colocalization,
                has_replication=cell.has_replication,
                data_available=cell.data_available,
                card_ids=list(cell.card_ids),
                archetype_specific=dict(cell.archetype_specific),
            )
        return clone

    @staticmethod
    def _compute_card_quality_metrics(cards: list) -> dict[str, Any]:
        """Compute fill rate metrics for each coverage axis across cards."""
        if not cards:
            return {"total_cards": 0, "fill_rate": 0.0}
        total = len(cards)
        axis_fill: dict[str, float] = {}
        for axis in ("task", "modality_omics", "tissue", "model_architecture", "model_family", "cell_type"):
            filled = 0
            for c in cards:
                val = getattr(c, axis, None)
                if val and str(val) not in ("", "unknown", "None"):
                    filled += 1
            axis_fill[axis] = round(filled / total, 3) if total else 0.0
        avg_fill = sum(axis_fill.values()) / max(len(axis_fill), 1)
        return {
            "total_cards": total,
            "fill_rate": round(avg_fill, 3),
            "coverage_axis_fill": axis_fill,
        }

    def _check_coverage_quality(self) -> dict[str, Any]:
        """Check coverage matrix sparsity before gap analysis."""
        cells = self.coverage_matrix.all_cells()
        total_cells = len(cells)
        cells_with_data = sum(1 for c in cells.values() if c.data_available)
        total_cards = sum(c.card_count for c in cells.values())
        ratio = cells_with_data / max(total_cells, 1)
        result = {
            "total_cells": total_cells,
            "cells_with_data": cells_with_data,
            "coverage_ratio": round(ratio, 3),
            "total_cards": total_cards,
        }
        if total_cells > 0 and ratio < 0.2:
            self.logger.warning(
                f"Coverage too sparse: {cells_with_data}/{total_cells} cells have data "
                f"(ratio={ratio:.1%}). Gap/hypothesis quality may be degraded."
            )
        return result

    def _propagate_output(self, output: SkillOutput, skill_id: str, current_input: Optional[SkillInput] = None) -> SkillInput:
        """Accumulate skill output into the running input. Merges new output data
        on top of the current input so downstream skills see all prior outputs."""
        new_data = output.model_dump()
        new_data["from_skill"] = skill_id
        self.harness.context.warm_to_l2(f"output_{skill_id}", new_data)

        # Start from accumulated state, overlay new output data
        base: dict[str, Any] = {}
        if current_input is not None:
            base = current_input.model_dump()
        # Remove SkillOutput-only fields that shouldn't carry forward
        for k in ("skill_name", "success", "error"):
            new_data.pop(k, None)
        base.update(new_data)
        return SkillInput.model_validate(base)

    def _prepare_skill_input(self, sid: str, current_input: SkillInput) -> SkillInput:
        """Inject skill-specific runtime data before execution. Bridges the DAG
        data-flow: some skills need data from non-adjacent skills, the card store,
        the coverage matrix, or archetype gap patterns."""
        data = current_input.model_dump()

        # Helper: safely get a list field
        def _get_list(key: str) -> list[Any]:
            v = data.get(key)
            return v if isinstance(v, list) else []

        # S2: derive trait_labels/gene_symbols from S1 key_terms
        if sid.startswith("s2_"):
            key_terms = _get_list("key_terms")
            if not data.get("trait_labels"):
                data["trait_labels"] = key_terms
            if not data.get("gene_symbols"):
                data["gene_symbols"] = []
            if "expand_synonyms" not in data:
                data["expand_synonyms"] = True

        # S3: derive traits/efo_ids/genes from S2 normalized output
        if sid.startswith("s3_"):
            norm_traits = _get_list("normalized_traits")
            norm_genes = _get_list("normalized_genes")
            if not data.get("traits"):
                data["traits"] = [t.get("efo_label", t.get("raw", "")) for t in norm_traits if isinstance(t, dict)]
            if not data.get("efo_ids"):
                data["efo_ids"] = [t.get("efo", "") for t in norm_traits if isinstance(t, dict) and t.get("efo")]
            if not data.get("genes"):
                data["genes"] = [g.get("symbol", "") for g in norm_genes if isinstance(g, dict)]
            params = self.harness.archetype_config.get("parameters", {})
            data.setdefault("p_value_max", params.get("significance_p_threshold", 5e-8))
            data.setdefault("max_per_trait", params.get("max_loci_per_trait", 50))

        # S4: build queries from key_terms + normalized terms (or candidate dimensions)
        if sid.startswith("s4_"):
            if not data.get("queries"):
                if self._candidate_driven and self._current_candidate:
                    topic_id = self._current_candidate.get("topic_id", "")
                    cached = self._candidate_progress.get(topic_id, {})
                    queries = cached.get("llm_queries", [])
                    if not queries:
                        queries = self._build_candidate_queries(self._current_candidate)
                    if not queries:
                        queries = list(_get_list("key_terms"))
                    kt = _get_list("key_terms")
                    for term in kt:
                        if term not in queries:
                            queries.append(term)
                else:
                    queries = list(_get_list("key_terms"))
                    for t in _get_list("normalized_traits"):
                        if isinstance(t, dict):
                            label = t.get("efo_label", t.get("raw", ""))
                            if label and label not in queries:
                                queries.append(label)
                    for sq in _get_list("sub_questions"):
                        if isinstance(sq, str) and len(sq) <= 80 and sq not in queries:
                            queries.append(sq)
                data["queries"] = queries
            data.setdefault("sources", ["semantic_scholar", "pubmed", "biorxiv"])
            data.setdefault("max_per_source", 20)

        # S5: seed_paper_ids and seed_dois from S4 papers
        if sid.startswith("s5_"):
            if not data.get("seed_paper_ids"):
                paper_ids: list[str] = []
                dois: list[str] = []
                for p in _get_list("papers"):
                    if isinstance(p, dict):
                        pid = p.get("paper_id") or p.get("paperId") or p.get("pmid")
                        if pid:
                            paper_ids.append(str(pid))
                        doi = p.get("doi") or (p.get("externalIds") or {}).get("DOI") if isinstance(p.get("externalIds"), dict) else p.get("doi")
                        if doi:
                            dois.append(str(doi))
                data["seed_paper_ids"] = paper_ids
                data["seed_dois"] = dois

        # S6b (PDF download): screened_papers from S6 kept list; params from archetype
        if sid.startswith("s6b_"):
            if not data.get("screened_papers"):
                screened = _get_list("kept")
                if not screened:
                    screened = _get_list("papers")
                data["screened_papers"] = screened
            params = self.harness.archetype_config.get("parameters", {})
            data.setdefault("max_downloads", params.get("pdf_download_max", settings.pdf_download_max))
            priority = list(_get_list("key_terms"))
            for t in _get_list("normalized_traits"):
                if isinstance(t, dict):
                    label = t.get("efo_label", "")
                    if label and label not in priority:
                        priority.append(label)
            data.setdefault("priority_keywords", priority)

        # S6: candidates from S4 papers + S5 hits; scope from S1 (exclude s6b_)
        if (sid.startswith("s6_literature") or sid.startswith("s6_")) and not sid.startswith("s6b_"):
            if not data.get("candidates"):
                candidates: list[dict[str, Any]] = []
                for p in _get_list("papers"):
                    if isinstance(p, dict):
                        candidates.append(p)
                for p in _get_list("forward_hits") + _get_list("backward_hits"):
                    if isinstance(p, dict):
                        candidates.append(p)
                data["candidates"] = candidates
            scope = data.get("scope_boundaries", {})
            if isinstance(scope, dict):
                inc = scope.get("include", [])
                exc = scope.get("exclude", [])
                data.setdefault("scope_include", [inc] if isinstance(inc, str) else inc)
                data.setdefault("scope_exclude", [exc] if isinstance(exc, str) else exc)
            if not data.get("key_terms"):
                data["key_terms"] = _get_list("key_terms")
            data.setdefault("max_tier", 2)

        # S6a (divergent): locus_genes from S3, cell_types from config/cards
        if sid.startswith("s6a_"):
            if not data.get("locus_genes"):
                data["locus_genes"] = _get_list("locus_genes")
            if not data.get("cell_types"):
                # derive from cards or archetype params
                params = self.harness.archetype_config.get("parameters", {})
                data["cell_types"] = params.get("cell_types", [])
            if not data.get("tissues"):
                params = self.harness.archetype_config.get("parameters", {})
                data["tissues"] = params.get("spatial_tissue_priority", [])
            if not data.get("traits"):
                data["traits"] = _get_list("traits")

        # S6c (deep read): papers from S6 kept list, with full_text if available from S6b
        if sid.startswith("s6c_"):
            if not data.get("papers"):
                deep_papers: list[dict[str, Any]] = []
                fulltext = _get_list("papers_with_fulltext")
                kept = _get_list("kept")
                if fulltext:
                    deep_papers = list(fulltext)
                elif kept:
                    deep_papers = [k for k in kept if isinstance(k, dict)]
                if not deep_papers:
                    deep_papers = _get_list("papers")
                data["papers"] = deep_papers
            params = self.harness.archetype_config.get("parameters", {})
            deep_read_cfg = params.get("deep_read", {})
            data.setdefault("max_papers", deep_read_cfg.get("max_papers_per_candidate", 5))
            data.setdefault("max_tier2_papers", deep_read_cfg.get("max_tier2_papers", 2))

        # S7: targets from S6b papers_with_fulltext (preferred) else S6 kept papers
        if sid.startswith("s7_"):
            if not data.get("targets"):
                targets: list[dict[str, Any]] = []
                fulltext_papers = _get_list("papers_with_fulltext")
                if fulltext_papers:
                    targets = fulltext_papers
                else:
                    for k in _get_list("kept"):
                        if isinstance(k, dict):
                            targets.append(k)
                    if not targets:
                        targets = _get_list("papers")
                data["targets"] = targets
            # Inject deep_read_notes from s6c if available
            notes = _get_list("notes")
            if notes and not data.get("deep_read_notes"):
                data["deep_read_notes"] = notes
            data.setdefault("normalized_traits", _get_list("normalized_traits"))
            data.setdefault("normalized_genes", _get_list("normalized_genes"))
            data.setdefault("max_findings_per_paper", 5)
            if self.evidence_card_class:
                archetype_default = self.evidence_card_class.model_fields["archetype"].default
                data["archetype"] = archetype_default

        # S8: locus_genes from S3, cell_types from cards/config
        if sid.startswith("s8_"):
            if not data.get("locus_genes"):
                data["locus_genes"] = _get_list("locus_genes")
            if not data.get("cell_types"):
                params = self.harness.archetype_config.get("parameters", {})
                data["cell_types"] = params.get("cell_types", [])

        # S9: required_methods/datasets from S8 gaps + config
        if sid.startswith("s9_"):
            if not data.get("required_methods"):
                # derive from S8 gaps (method-related) + archetype params
                params = self.harness.archetype_config.get("parameters", {})
                data["required_methods"] = params.get("required_methods", [])
            if not data.get("required_datasets"):
                data["required_datasets"] = _get_list("gaps")  # S8 output gaps list

        # S10: study_ids/variant_ids from S3
        if sid.startswith("s10_"):
            data.setdefault("study_ids", _get_list("study_ids"))
            data.setdefault("variant_ids", _get_list("variant_ids"))
            data.setdefault("genes", _get_list("genes"))

        # S11: cards from card_store, coverage_matrix, gap_patterns from archetype
        if sid.startswith("s11_"):
            if not data.get("cards"):
                data["cards"] = self._load_cards_from_store()
            if not data.get("gap_patterns"):
                data["gap_patterns"] = self.harness.archetype_config.get("_gap_patterns", [])
            data["coverage_matrix"] = self.coverage_matrix

        # S12: gaps from S11, cards from card_store
        if sid.startswith("s12_"):
            if not data.get("gaps"):
                data["gaps"] = _get_list("gaps")
            if not data.get("cards"):
                data["cards"] = self._load_cards_from_store()
            data.setdefault("max_hypotheses", 5)

        skill = self.skill_instances.get(sid)
        schema = skill.input_schema if skill else SkillInput
        return schema.model_validate(data)

    def _load_cards_from_store(self) -> list[Any]:
        """Load all evidence cards from the card store as card objects."""
        try:
            rows = self.harness.card_store.all_rows()
            if not rows:
                return []
            from shared.evidence.base_card import BaseEvidenceCard

            card_class = self.evidence_card_class or BaseEvidenceCard
            cards: list[Any] = []
            for row in rows:
                if isinstance(row, dict):
                    try:
                        cards.append(card_class.model_validate(row))
                    except Exception:
                        try:
                            from shared.evidence.base_card import V2GEvidenceCard
                            cards.append(V2GEvidenceCard.model_validate(row))
                        except Exception:
                            cards.append(row)
                else:
                    cards.append(row)
            return cards
        except Exception:
            return []

    def _checkpoint_step(
        self,
        step_name: str,
        output: Optional[SkillOutput],
        round_idx: int,
        state: CheckpointState = CheckpointState.COMPLETED,
    ) -> None:
        if not settings.enable_checkpoint:
            return
        try:
            cp = Checkpoint(
                project_id=self.project_id,
                step_name=f"r{round_idx}_{step_name}",
                step_index=round_idx,
                state=state,
                context_snapshot=self.harness.context.l2.snapshot(),
                token_usage=self.harness.budget.snapshot(),
                metadata=output.metrics if output else {},
            )
            self.checkpoint_mgr.save(cp)
        except Exception as e:
            self.logger.warning(f"Checkpoint save failed for {step_name}: {e}")

    def _checkpoint_inner_round(self, round_idx: int, result: InnerLoopResult) -> None:
        if not settings.enable_checkpoint:
            return
        try:
            cp = Checkpoint(
                project_id=self.project_id,
                step_name=f"r{round_idx}_inner_loop",
                step_index=round_idx,
                state=CheckpointState.COMPLETED if result.converged else CheckpointState.RUNNING,
                context_snapshot=self.harness.context.l2.snapshot(),
                token_usage=self.harness.budget.snapshot(),
                metadata={
                    "iteration": result.iteration,
                    "reason": result.reason.value if result.reason else None,
                    "cards_added": result.cards_added,
                    "errors": result.errors,
                },
            )
            self.checkpoint_mgr.save(cp)
        except Exception as e:
            self.logger.warning(f"Inner loop checkpoint failed: {e}")

    def _restore_from_checkpoint(self, step_name: str, fallback_input: SkillInput) -> SkillInput:
        cp = self.checkpoint_mgr.load(step_name)
        if cp and cp.context_snapshot:
            try:
                return SkillInput.model_validate(cp.context_snapshot)
            except Exception:
                pass
        return fallback_input

    def _run_provenance_on_new_cards(self) -> None:
        try:
            rows = self.harness.card_store.all_rows()
            from shared.evidence.base_card import BaseEvidenceCard

            card_class = self.evidence_card_class or BaseEvidenceCard
            cards: list = []
            for row in rows:
                try:
                    cards.append(card_class.model_validate(row))
                except Exception:
                    pass
            if cards:
                self.harness.run_provenance(cards)
        except Exception as e:
            self.logger.warning(f"Provenance check failed: {e}")


def _is_dict_like(d: Any) -> bool:
    return isinstance(d, dict) and len(d) > 0
