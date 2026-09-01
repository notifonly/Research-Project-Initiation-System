"""End-to-end integration tests for p05 harness loop_runner.

Mocks phase functions at the loop_runner module level to test pipeline wiring.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from scripts.p05_harness.loop_runner import CandidateLoopResult, LoopRunner
from scripts.p05_harness.mcp.search_engine import SearchEngine

# ── Shared test fixtures ───────────────────────────────────────────────

FAKE_PAPERS = [
    {
        "title": "PantheonOS: A Unified Framework for scFM Selection",
        "authors": ["Jones, A.", "Smith, B."],
        "year": 2026,
        "venue": "bioRxiv",
        "doi": "10.1101/2026.02.15.123456",
        "abstract": "PantheonOS introduces a model router agent...",
        "citation_count": 15,
        "source": "semantic_scholar",
    },
]

CANDIDATE = {
    "topic_id": "T001",
    "research_question": "multi-scFM router agent for single-cell omics",
    "dimensions": {"method": "multi-scFM router", "disease": "pan-cancer"},
    "search_query": "scFM router agent single-cell",
    "scores": {"combined": 0.85, "competitiveness": 0.15},
}

PASSING_PLAN = {
    "candidate_id": "T001",
    "summary_zh": "提出多scFM路由智能体。",
    "technical_roadmap": [],
    "data_sources_detail": [],
    "feasibility": {},
    "innovation_points": [],
    "expected_outputs": [],
    "target_venues": [],
}

CONFIG = {
    "loop": {"max_iterations": 1, "pass_threshold": 4.0, "stagnation_limit": 2},
    "mcp": {"search_sources": ["semantic_scholar"], "max_per_source": 10, "year_range": "2022-", "recent_boost_year": 2024},
    "novelty_check": {
        "enabled": True, "max_claims": 5, "queries_per_claim": 4,
        "top_k_papers": 15, "max_per_source": 10,
        "recent_boost_year": 2024, "reposition_max_attempts": 1,
    },
}


def _make_fake_se() -> MagicMock:
    se = MagicMock(spec=SearchEngine)
    se.search_multi = AsyncMock(return_value=FAKE_PAPERS)
    se.search = AsyncMock(return_value=FAKE_PAPERS)
    se.verify_doi = AsyncMock(return_value={"title": "X", "year": 2024, "verified": True})
    se.verify_pmid = AsyncMock(return_value={"title": "X", "year": 2024, "verified": True})
    se.search_calls = 0
    se.lookup_calls = 0
    se.close = AsyncMock()
    return se


# ── E2E Tests ──────────────────────────────────────────────────────────

class TestE2EScoopedReject:
    """Scooped → reposition (fail) → rejected."""

    @pytest.mark.asyncio
    async def test_scooped_reposition_fail_rejects_candidate(self):
        fake_se = _make_fake_se()

        from scripts.p05_harness.phases.phase15_novelty_verify import Phase15Output
        from scripts.p05_harness.validators.methodology_redteam import RedTeamOutput

        scooped_output = Phase15Output(
            overall_verdict="scooped",
            repositioning_required=True,
            suggested_repositioning="收窄为学习型路由",
            verdicts=[{"claim": "首个多scFM路由", "verdict": "scooped", "closeness": "PantheonOS已实现", "closest_works": [{"title": "PantheonOS", "authors": "Jones", "year": "2026", "venue": "bioRxiv", "similarity": "路由", "doi": "10.1101/test"}], "comparison_table": [], "evidence_links": []}],
            papers_found=FAKE_PAPERS,
        )
        # Second call returns still-scooped after reposition
        scooped_output2 = Phase15Output(
            overall_verdict="scooped",
            repositioning_required=True,
            suggested_repositioning="无可行重定位",
            verdicts=[{"claim": "学习型路由", "verdict": "scooped", "closeness": "已有学习型路由", "closest_works": [{"title": "Learning Router", "authors": "Smith", "year": "2025", "venue": "ICML", "similarity": "学习", "doi": ""}], "comparison_table": [], "evidence_links": []}],
            papers_found=FAKE_PAPERS,
        )

        with (
            patch("scripts.p05_harness.loop_runner.enrich_context_with_mcp", new_callable=AsyncMock, return_value="MCP context") as mock_enrich,
            patch("scripts.p05_harness.loop_runner.generate_initial_plan", new_callable=AsyncMock, return_value=PASSING_PLAN) as mock_gen,
            patch("scripts.p05_harness.loop_runner.check_completeness") as mock_comp,
            patch("scripts.p05_harness.loop_runner.verify_novelty", new_callable=AsyncMock, side_effect=[scooped_output, scooped_output2]) as mock_novelty,
            patch("scripts.p05_harness.loop_runner.reposition_plan", new_callable=AsyncMock, return_value=PASSING_PLAN) as mock_reposition,
        ):
            # Minimal completeness: no issues
            mock_comp.return_value = MagicMock(missing_fields=[], empty_fields=[], issues_count=0, is_complete=True)

            with tempfile.TemporaryDirectory() as tmp:
                runner = LoopRunner(
                    config=CONFIG, output_dir=Path(tmp),
                    search_engine=fake_se, run_name="test1",
                )
                result = await runner.run(
                    candidates=[CANDIDATE],
                    evidence_cards_by_candidate={}, gaps=[], hypotheses=[],
                )

            assert len(result.candidates) == 1
            cr = result.candidates[0]
            assert cr.error != "", f"Expected error, got empty"
            assert "scooped" in cr.error.lower()
            assert cr.passed is False
            assert cr.repositioning_attempts == 1
            assert cr.novelty_verdict["overall_verdict"] == "scooped"
            assert result.passed_count == 0
            assert result.failed_count == 1

    @pytest.mark.asyncio
    async def test_scooped_reposition_field_serialization(self):
        """Verify CandidateLoopResult serializes all new fields."""
        fake_se = _make_fake_se()
        from scripts.p05_harness.phases.phase15_novelty_verify import Phase15Output

        scooped = Phase15Output(
            overall_verdict="scooped",
            repositioning_required=True,
            verdicts=[{"claim": "test", "verdict": "scooped", "closeness": "dup", "closest_works": [], "comparison_table": [], "evidence_links": []}],
            papers_found=[],
        )

        with (
            patch("scripts.p05_harness.loop_runner.enrich_context_with_mcp", new_callable=AsyncMock, return_value="MCP"),
            patch("scripts.p05_harness.loop_runner.generate_initial_plan", new_callable=AsyncMock, return_value=PASSING_PLAN),
            patch("scripts.p05_harness.loop_runner.check_completeness") as mock_comp,
            patch("scripts.p05_harness.loop_runner.verify_novelty", new_callable=AsyncMock, side_effect=[scooped, scooped]),
            patch("scripts.p05_harness.loop_runner.reposition_plan", new_callable=AsyncMock, return_value=PASSING_PLAN),
        ):
            mock_comp.return_value = MagicMock(missing_fields=[], empty_fields=[], issues_count=0, is_complete=True)

            with tempfile.TemporaryDirectory() as tmp:
                runner = LoopRunner(config=CONFIG, output_dir=Path(tmp), search_engine=fake_se, run_name="test2")
                result = await runner.run(
                    candidates=[CANDIDATE], evidence_cards_by_candidate={}, gaps=[], hypotheses=[],
                )

            cr = result.candidates[0]
            d = runner._candidate_to_dict(cr)
            assert "novelty_verdict" in d
            assert "redteam_result" in d
            assert "repositioning_attempts" in d
            assert d["repositioning_attempts"] == 1


class TestE2EScoopedRepositionPass:
    """Scooped → reposition (success, now adjacent) → redteam → critique."""

    @pytest.mark.asyncio
    async def test_scooped_then_adjacent_passes_critique(self):
        fake_se = _make_fake_se()
        from scripts.p05_harness.phases.phase15_novelty_verify import Phase15Output
        from scripts.p05_harness.validators.methodology_redteam import RedTeamOutput

        scooped = Phase15Output(
            overall_verdict="scooped", repositioning_required=True,
            suggested_repositioning="收窄",
            verdicts=[{"claim": "首个路由", "verdict": "scooped", "closeness": "有先例", "closest_works": [{"title": "PantheonOS", "authors": "J", "year": "2026", "venue": "bioRxiv", "similarity": "路由", "doi": ""}], "comparison_table": [], "evidence_links": []}],
            papers_found=FAKE_PAPERS,
        )
        adjacent = Phase15Output(
            overall_verdict="adjacent", repositioning_required=True,
            suggested_repositioning="差异化定位可行",
            verdicts=[{"claim": "学习型路由", "verdict": "adjacent", "closeness": "有差异化", "closest_works": [{"title": "PantheonOS", "authors": "J", "year": "2026", "venue": "bioRxiv", "similarity": "差异", "doi": ""}], "comparison_table": [], "evidence_links": []}],
            papers_found=FAKE_PAPERS,
        )
        redteam_ok = RedTeamOutput(
            findings=[],
            verified_claims=[],
            unverified_claims=[],
            high_count=0, medium_count=0, low_count=1,
        )

        from scripts.p05_harness.validators.rubric import CritiqueResult
        passing_critique = CritiqueResult(
            candidate_id="T001", iteration=0,
            scores={
                "literature_coverage": 4, "technical_feasibility": 4,
                "innovation_clarity": 4, "data_accessibility": 4,
                "gap_alignment": 4, "evaluation_rigor": 4,
            },
            weighted_score=4.0, passed=True,
        )

        with (
            patch("scripts.p05_harness.loop_runner.enrich_context_with_mcp", new_callable=AsyncMock, return_value="MCP") as mock_enrich,
            patch("scripts.p05_harness.loop_runner.generate_initial_plan", new_callable=AsyncMock, return_value=PASSING_PLAN) as mock_gen,
            patch("scripts.p05_harness.loop_runner.check_completeness") as mock_comp,
            patch("scripts.p05_harness.loop_runner.verify_novelty", new_callable=AsyncMock, side_effect=[scooped, adjacent]) as mock_novelty,
            patch("scripts.p05_harness.loop_runner.reposition_plan", new_callable=AsyncMock, return_value=PASSING_PLAN) as mock_reposition,
            patch("scripts.p05_harness.loop_runner.run_redteam", new_callable=AsyncMock, return_value=redteam_ok) as mock_redteam,
            patch("scripts.p05_harness.loop_runner.verify_citations", new_callable=AsyncMock, return_value=[]) as mock_cite,
            patch("scripts.p05_harness.loop_runner.critique_plan", new_callable=AsyncMock, return_value=passing_critique) as mock_critique,
            patch("scripts.p05_harness.loop_runner.check_literature_coverage") as mock_lit,
        ):
            mock_comp.return_value = MagicMock(missing_fields=[], empty_fields=[], issues_count=0, is_complete=True)
            mock_lit.return_value = MagicMock(evidence_card_count=0, cited_paper_count=0, overlapping_count=0, coverage_ratio=0.0, status="ok")

            with tempfile.TemporaryDirectory() as tmp:
                runner = LoopRunner(config=CONFIG, output_dir=Path(tmp), search_engine=fake_se, run_name="test3")
                result = await runner.run(
                    candidates=[CANDIDATE], evidence_cards_by_candidate={}, gaps=[], hypotheses=[],
                )

            cr = result.candidates[0]
            assert cr.error == "", f"Unexpected error: {cr.error}"
            assert cr.passed is True
            assert cr.repositioning_attempts == 1
            assert cr.novelty_verdict["overall_verdict"] == "adjacent"
            assert cr.redteam_result != {}


class TestE2ENoSearchEngine:
    """skip_mcp=True path — no Phase 0/1.5/1.6, direct to critique."""

    @pytest.mark.asyncio
    async def test_skip_mcp_runs_critique_only(self):
        from scripts.p05_harness.validators.rubric import CritiqueResult
        passing = CritiqueResult(
            candidate_id="T001", iteration=0,
            scores={"literature_coverage": 4, "technical_feasibility": 4, "innovation_clarity": 4, "data_accessibility": 4, "gap_alignment": 4, "evaluation_rigor": 4},
            weighted_score=4.0, passed=True,
        )

        with (
            patch("scripts.p05_harness.loop_runner.generate_initial_plan", new_callable=AsyncMock, return_value=PASSING_PLAN),
            patch("scripts.p05_harness.loop_runner.check_completeness") as mock_comp,
            patch("scripts.p05_harness.loop_runner.critique_plan", new_callable=AsyncMock, return_value=passing),
            patch("scripts.p05_harness.loop_runner.check_literature_coverage") as mock_lit,
        ):
            mock_comp.return_value = MagicMock(missing_fields=[], empty_fields=[], issues_count=0, is_complete=True)
            mock_lit.return_value = MagicMock(evidence_card_count=0, cited_paper_count=0, overlapping_count=0, coverage_ratio=0.0, status="ok")

            with tempfile.TemporaryDirectory() as tmp:
                runner = LoopRunner(config=CONFIG, output_dir=Path(tmp), skip_mcp=True, run_name="test_skip")
                result = await runner.run(
                    candidates=[CANDIDATE], evidence_cards_by_candidate={}, gaps=[], hypotheses=[],
                )

            cr = result.candidates[0]
            assert cr.error == ""
            assert cr.passed is True
            assert cr.repositioning_attempts == 0
            assert cr.novelty_verdict == {}
            assert cr.redteam_result == {}


class TestCandidateLoopResultFields:
    def test_default_fields_present(self):
        cr = CandidateLoopResult(candidate_id="test")
        assert cr.novelty_verdict == {}
        assert cr.redteam_result == {}
        assert cr.repositioning_attempts == 0

    def test_candidate_to_dict_serializes_new_fields(self):
        cr = CandidateLoopResult(
            candidate_id="T001",
            research_question="test",
            method="router",
            disease="cancer",
            combined_score=0.8,
            final_score=4.5,
            passed=True,
            repositioning_attempts=2,
            novelty_verdict={"overall_verdict": "adjacent", "verdicts": []},
            redteam_result={"findings": [], "high_count": 0},
        )
        with tempfile.TemporaryDirectory() as tmp:
            runner = LoopRunner(config=CONFIG, output_dir=Path(tmp), skip_mcp=True)
            d = runner._candidate_to_dict(cr)

        assert d["novelty_verdict"]["overall_verdict"] == "adjacent"
        assert d["redteam_result"]["high_count"] == 0
        assert d["repositioning_attempts"] == 2
        assert d["passed"] is True


class TestSearchEngineRecencyConfig:
    @pytest.mark.asyncio
    async def test_recency_boost_passed_to_search_engine(self):
        from scripts.p05_harness.validators.rubric import CritiqueResult
        passing = CritiqueResult(
            candidate_id="T001", iteration=0,
            scores={"literature_coverage": 4, "technical_feasibility": 4, "innovation_clarity": 4, "data_accessibility": 4, "gap_alignment": 4, "evaluation_rigor": 4},
            weighted_score=4.0, passed=True,
        )

        with (
            patch("scripts.p05_harness.loop_runner.SearchEngine") as MockSE,
            patch("scripts.p05_harness.loop_runner.generate_initial_plan", new_callable=AsyncMock, return_value=PASSING_PLAN),
            patch("scripts.p05_harness.loop_runner.check_completeness") as mock_comp,
            patch("scripts.p05_harness.loop_runner.critique_plan", new_callable=AsyncMock, return_value=passing),
            patch("scripts.p05_harness.loop_runner.check_literature_coverage") as mock_lit,
        ):
            mock_comp.return_value = MagicMock(missing_fields=[], empty_fields=[], issues_count=0, is_complete=True)
            mock_lit.return_value = MagicMock(evidence_card_count=0, cited_paper_count=0, overlapping_count=0, coverage_ratio=0.0, status="ok")

            mock_se = _make_fake_se()
            MockSE.return_value = mock_se

            with tempfile.TemporaryDirectory() as tmp:
                runner = LoopRunner(config=CONFIG, output_dir=Path(tmp), search_engine=None, run_name="test_recency")
                await runner.run(
                    candidates=[CANDIDATE], evidence_cards_by_candidate={}, gaps=[], hypotheses=[],
                )

            MockSE.assert_called_once()
            call_kwargs = MockSE.call_args.kwargs
            assert call_kwargs.get("recent_boost_year") == CONFIG["mcp"]["recent_boost_year"]


# ── Phase 0 adversarial queries unit tests ─────────────────────────────

class TestMergeDedupPapers:
    def test_empty_both(self):
        from scripts.p05_harness.phases.phase1_generate import _merge_dedup_papers
        assert _merge_dedup_papers([], []) == []

    def test_dedup_by_title(self):
        from scripts.p05_harness.phases.phase1_generate import _merge_dedup_papers
        supportive = [{"title": "Paper A", "citation_count": 5, "year": 2023}]
        adversarial = [{"title": "Paper A", "citation_count": 10, "year": 2023}]
        result = _merge_dedup_papers(supportive, adversarial)
        assert len(result) == 1
        assert result[0]["citation_count"] == 10

    def test_keep_unique_from_both(self):
        from scripts.p05_harness.phases.phase1_generate import _merge_dedup_papers
        supportive = [{"title": "Paper A", "citation_count": 5, "year": 2023}]
        adversarial = [{"title": "Paper B", "citation_count": 3, "year": 2024}]
        result = _merge_dedup_papers(supportive, adversarial)
        assert len(result) == 2

    def test_sort_by_citation_desc(self):
        from scripts.p05_harness.phases.phase1_generate import _merge_dedup_papers
        supportive = [{"title": "Low", "citation_count": 1, "year": 2023}]
        adversarial = [{"title": "High", "citation_count": 100, "year": 2023}]
        result = _merge_dedup_papers(supportive, adversarial)
        assert result[0]["title"] == "High"
        assert result[1]["title"] == "Low"

    def test_empty_title_skipped(self):
        from scripts.p05_harness.phases.phase1_generate import _merge_dedup_papers
        supportive = [{"title": "", "citation_count": 5}]
        adversarial = [{"title": "Good", "citation_count": 3}]
        result = _merge_dedup_papers(supportive, adversarial)
        assert len(result) == 1
        assert result[0]["title"] == "Good"


class TestGenerateAdversarialPhase0Queries:
    @pytest.mark.asyncio
    async def test_generates_queries(self):
        from scripts.p05_harness.phases.phase1_generate import _generate_adversarial_phase0_queries

        with patch("scripts.p05_harness.phases.phase1_generate.llm_complete", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps(
                ["model routing agent bioinformatics", "scFM cost-aware selection", "foundation model router"]
            )

            candidate = {
                "research_question": "multi-scFM router",
                "dimensions": {"method": "router", "disease": "pan-cancer"},
            }
            queries = await _generate_adversarial_phase0_queries(candidate, max_queries=3)
            assert len(queries) == 3
            assert all(isinstance(q, str) and len(q) > 0 for q in queries)

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self):
        from scripts.p05_harness.phases.phase1_generate import _generate_adversarial_phase0_queries

        with patch("scripts.p05_harness.phases.phase1_generate.llm_complete", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM unavailable")

            candidate = {"research_question": "test", "dimensions": {"method": "x", "disease": "y"}}
            queries = await _generate_adversarial_phase0_queries(candidate)
            assert queries == []

    @pytest.mark.asyncio
    async def test_truncates_to_max_queries(self):
        from scripts.p05_harness.phases.phase1_generate import _generate_adversarial_phase0_queries

        with patch("scripts.p05_harness.phases.phase1_generate.llm_complete", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps(["query one", "query two", "query three", "query four", "query five", "query six"])

            candidate = {"research_question": "test", "dimensions": {"method": "x", "disease": "y"}}
            queries = await _generate_adversarial_phase0_queries(candidate, max_queries=3)
            assert len(queries) == 3
