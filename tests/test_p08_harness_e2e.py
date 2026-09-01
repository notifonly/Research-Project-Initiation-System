"""End-to-end integration tests for p08 harness.
Verifies p08-specific domain prompts injection and basic loop wiring.
Core loop logic is tested by test_p05_harness_e2e.py.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── P08-specific test data ───────────────────────────────────────────────

P08_FAKE_PAPERS = [
    {
        "title": "Cross-ethnic proteomic biomarker validation",
        "authors": ["Chen, L.", "Wang, X."],
        "year": 2026,
        "venue": "Nature Genetics",
        "doi": "10.1038/ng.2026.cross.001",
        "abstract": "Validated 50 plasma protein biomarkers across EUR/EAS/AFR...",
        "citation_count": 42,
        "source": "semantic_scholar",
    },
]

P08_CANDIDATE = {
    "topic_id": "T001",
    "research_question": "Cross-ethnic proteomic biomarker portability between UKB and Chinese cohort",
    "dimensions": {
        "biomarker_portability": {
            "population_pair": "EUR-EAS",
            "omics_layer": "proteomics",
            "portability_method": "pQTL-coloc",
        },
    },
    "search_query": "proteomic biomarker cross-ethnic portability UKB Chinese",
    "scores": {"combined": 0.88, "competitiveness": 0.12},
}

P08_PLAN = {
    "candidate_id": "T001",
    "summary_zh": "系统性评估血浆蛋白生物标志物在UKB（EUR）与中国队列（EAS）间的可移植性。",
    "technical_roadmap": [],
    "data_sources_detail": [],
    "feasibility": {},
    "innovation_points": [],
    "expected_outputs": [],
    "target_venues": [],
}

P08_CONFIG = {
    "project_id": "p08_cross_ethnic_multiomics",
    "harness_name": "P08 跨种族多组学整合 研究方案质量验收",
    "loop": {"max_iterations": 1, "pass_threshold": 4.0, "stagnation_limit": 2},
    "mcp": {
        "search_sources": ["semantic_scholar", "medrxiv"],
        "max_per_source": 10,
        "year_range": "2022-",
        "recent_boost_year": 2024,
    },
    "novelty_check": {
        "enabled": True,
        "max_claims": 5,
        "queries_per_claim": 4,
        "top_k_papers": 15,
        "max_per_source": 10,
        "recent_boost_year": 2024,
        "reposition_max_attempts": 1,
    },
    "rubric": {
        "dimensions": [
            {"name": "literature_coverage", "label_zh": "文献覆盖度", "weight": 1.0},
            {"name": "technical_feasibility", "label_zh": "技术可行性", "weight": 1.0},
            {"name": "innovation_clarity", "label_zh": "创新清晰度", "weight": 1.0},
            {"name": "data_accessibility", "label_zh": "数据可及性", "weight": 1.0},
            {"name": "gap_alignment", "label_zh": "缺口对齐度", "weight": 1.0},
            {"name": "evaluation_rigor", "label_zh": "评估严谨性", "weight": 1.0},
        ],
        "pass_threshold": 4.0,
    },
    "output": {"dir": "data/p08_harness_output"},
}


# ── Helper ───────────────────────────────────────────────────────────────

def _set_p08_prompts():
    """Set P08 domain prompts. Call at test start, restore at teardown."""
    from scripts.p05_harness.domain_prompts import set_prompts
    from scripts.p08_harness.domain_prompts import P08_DOMAIN_PROMPTS
    set_prompts(P08_DOMAIN_PROMPTS)


def _restore_p05_prompts():
    """Restore P05 domain prompts as default."""
    from scripts.p05_harness.domain_prompts import set_prompts
    from scripts.p05_harness.domain_prompts import P05_DOMAIN_PROMPTS
    set_prompts(P05_DOMAIN_PROMPTS)


# ── Domain prompts tests ─────────────────────────────────────────────────

class TestP08DomainPrompts:
    """Verify P08 domain prompts are correctly loaded and injected."""

    def test_domain_name_is_cross_ethnic(self):
        from scripts.p08_harness.domain_prompts import P08_DOMAIN_PROMPTS
        assert P08_DOMAIN_PROMPTS.domain_name == "跨种族多组学整合"

    def test_generate_system_refers_to_cross_ethnic(self):
        from scripts.p08_harness.domain_prompts import P08_DOMAIN_PROMPTS
        assert "跨种族多组学" in P08_DOMAIN_PROMPTS.generate_system

    def test_card_classify_fields_are_cross_ethnic(self):
        from scripts.p08_harness.domain_prompts import P08_DOMAIN_PROMPTS
        fields = P08_DOMAIN_PROMPTS.card_classify_fields
        assert "ancestry_comparison" in fields
        assert "population_cohorts" in fields
        assert "cross_ethnic_replication" in fields
        assert "model_family" not in fields

    def test_report_template_contains_placeholder(self):
        from scripts.p08_harness.domain_prompts import P08_DOMAIN_PROMPTS
        template = P08_DOMAIN_PROMPTS.report_title_template
        assert "{harness_name}" in template
        assert "研究方案验收报告" in template

    def test_prompts_singleton_set_and_restore(self):
        from scripts.p05_harness.domain_prompts import get_prompts
        try:
            _set_p08_prompts()
            assert get_prompts().domain_name == "跨种族多组学整合"
            assert "ancestry_comparison" in get_prompts().card_classify_fields
        finally:
            _restore_p05_prompts()


# ── P08 main module tests ────────────────────────────────────────────────

class TestP08MainModule:
    """Verify p08 main.py correctly imports and configures the harness."""

    def test_load_project_data_returns_tuple(self):
        from scripts.p08_harness.main import load_project_data

        result = load_project_data(P08_CONFIG)
        assert isinstance(result, tuple)
        assert len(result) == 4
        candidates, evidence_maps, gaps, hypotheses = result
        assert isinstance(candidates, list)
        assert isinstance(evidence_maps, dict)
        assert isinstance(gaps, list)
        assert isinstance(hypotheses, list)

    def test_load_project_data_has_candidates(self):
        from scripts.p08_harness.main import load_project_data

        candidates, _, _, _ = load_project_data(P08_CONFIG)
        assert len(candidates) > 0

    def test_candidates_belong_to_p08(self):
        from scripts.p08_harness.main import load_project_data

        candidates, _, _, _ = load_project_data(P08_CONFIG)
        non_p08 = [c for c in candidates
                   if c.get("project_id", "")
                   and not c.get("project_id", "").startswith("p08")]
        assert len(non_p08) == 0, \
            f"Found candidates with non-p08 project_id: {non_p08}"

    def test_filter_candidates_by_ids(self):
        from scripts.p08_harness.main import filter_candidates

        fake_args = MagicMock()
        fake_args.candidates = "T000, T005"
        fake_args.deep_only = False
        fake_args.max_candidates = 0

        fake_candidates = [
            {"topic_id": "T000", "scores": {"combined": 0.9}},
            {"topic_id": "T001", "scores": {"combined": 0.8}},
            {"topic_id": "T005", "scores": {"combined": 0.7}},
        ]
        result = filter_candidates(fake_candidates, fake_args, P08_CONFIG)
        assert len(result) == 2
        assert {c["topic_id"] for c in result} == {"T000", "T005"}

    def test_filter_candidates_max_limit(self):
        from scripts.p08_harness.main import filter_candidates

        fake_args = MagicMock()
        fake_args.candidates = ""
        fake_args.deep_only = False
        fake_args.max_candidates = 2

        fake_candidates = [
            {"topic_id": "T000", "scores": {"combined": 0.9}},
            {"topic_id": "T001", "scores": {"combined": 0.8}},
            {"topic_id": "T002", "scores": {"combined": 0.7}},
        ]
        result = filter_candidates(fake_candidates, fake_args, P08_CONFIG)
        assert len(result) == 2

    def test_main_imports_without_error(self):
        import scripts.p08_harness.main  # noqa: F401


# ── E2E tests with p08 config and data ───────────────────────────────────

class TestP08E2EBasic:
    """Basic E2E: plan generation → critique → pass with p08 config."""

    @pytest.mark.asyncio
    async def test_p08_critique_loop_passes(self):
        try:
            _set_p08_prompts()
            from scripts.p05_harness.loop_runner import LoopRunner
            from scripts.p05_harness.validators.rubric import CritiqueResult

            passing = CritiqueResult(
                candidate_id="T001",
                iteration=0,
                scores={
                    "literature_coverage": 4,
                    "technical_feasibility": 4,
                    "innovation_clarity": 4,
                    "data_accessibility": 4,
                    "gap_alignment": 4,
                    "evaluation_rigor": 4,
                },
                weighted_score=4.0,
                passed=True,
            )

            with (
                patch("scripts.p05_harness.loop_runner.generate_initial_plan",
                      new_callable=AsyncMock, return_value=P08_PLAN),
                patch("scripts.p05_harness.loop_runner.check_completeness") as mock_comp,
                patch("scripts.p05_harness.loop_runner.critique_plan",
                      new_callable=AsyncMock, return_value=passing),
                patch("scripts.p05_harness.loop_runner.check_literature_coverage") as mock_lit,
            ):
                mock_comp.return_value = MagicMock(
                    missing_fields=[], empty_fields=[], issues_count=0, is_complete=True)
                mock_lit.return_value = MagicMock(
                    evidence_card_count=10, cited_paper_count=5,
                    overlapping_count=2, coverage_ratio=0.2, status="ok")

                with tempfile.TemporaryDirectory() as tmp:
                    runner = LoopRunner(
                        config=P08_CONFIG, output_dir=Path(tmp),
                        skip_mcp=True, run_name="test_p08_e2e")
                    result = await runner.run(
                        candidates=[P08_CANDIDATE],
                        evidence_cards_by_candidate={}, gaps=[], hypotheses=[])

                assert len(result.candidates) == 1
                cr = result.candidates[0]
                assert cr.error == "", f"Unexpected error: {cr.error}"
                assert cr.passed is True
                assert cr.candidate_id == "T001"
                assert result.passed_count == 1
                assert result.failed_count == 0
        finally:
            _restore_p05_prompts()

    @pytest.mark.asyncio
    async def test_p08_scooped_gets_rejected(self):
        try:
            _set_p08_prompts()
            from scripts.p05_harness.loop_runner import LoopRunner
            from scripts.p05_harness.phases.phase15_novelty_verify import Phase15Output

            scooped = Phase15Output(
                overall_verdict="scooped",
                repositioning_required=True,
                suggested_repositioning="收窄为特定族群",
                verdicts=[{
                    "claim": "首个跨种族蛋白标志物研究",
                    "verdict": "scooped",
                    "closeness": "已有UKB-EAS验证研究",
                    "closest_works": [{
                        "title": "Cross-ethnic proteomic validation",
                        "authors": "Chen, L.", "year": "2026",
                        "venue": "Nature Genetics",
                        "similarity": "相同人群对比",
                        "doi": "10.1038/test",
                    }],
                    "comparison_table": [], "evidence_links": [],
                }],
                papers_found=P08_FAKE_PAPERS,
            )
            scooped2 = Phase15Output(
                overall_verdict="scooped",
                repositioning_required=True,
                suggested_repositioning="无可行重定位",
                verdicts=[{
                    "claim": "特定族群标志物",
                    "verdict": "scooped",
                    "closeness": "已有类似研究",
                    "closest_works": [{
                        "title": "Ethnic-specific markers",
                        "authors": "Liu, M.", "year": "2025",
                        "venue": "AJHG", "similarity": "同族群", "doi": "",
                    }],
                    "comparison_table": [], "evidence_links": [],
                }],
                papers_found=P08_FAKE_PAPERS,
            )

            with (
                patch("scripts.p05_harness.loop_runner.enrich_context_with_mcp",
                      new_callable=AsyncMock, return_value="MCP context"),
                patch("scripts.p05_harness.loop_runner.generate_initial_plan",
                      new_callable=AsyncMock, return_value=P08_PLAN),
                patch("scripts.p05_harness.loop_runner.check_completeness") as mock_comp,
                patch("scripts.p05_harness.loop_runner.verify_novelty",
                      new_callable=AsyncMock, side_effect=[scooped, scooped2]),
                patch("scripts.p05_harness.loop_runner.reposition_plan",
                      new_callable=AsyncMock, return_value=P08_PLAN),
            ):
                mock_comp.return_value = MagicMock(
                    missing_fields=[], empty_fields=[], issues_count=0, is_complete=True)

                fake_se = MagicMock()
                fake_se.search_multi = AsyncMock(return_value=P08_FAKE_PAPERS)
                fake_se.search = AsyncMock(return_value=P08_FAKE_PAPERS)
                fake_se.close = AsyncMock()

                with tempfile.TemporaryDirectory() as tmp:
                    runner = LoopRunner(
                        config=P08_CONFIG, output_dir=Path(tmp),
                        search_engine=fake_se, run_name="test_p08_scooped")
                    result = await runner.run(
                        candidates=[P08_CANDIDATE],
                        evidence_cards_by_candidate={}, gaps=[], hypotheses=[])

                cr = result.candidates[0]
                assert cr.passed is False
                assert "scooped" in cr.error.lower()
                assert cr.repositioning_attempts == 1
                assert cr.novelty_verdict["overall_verdict"] == "scooped"
        finally:
            _restore_p05_prompts()

    @pytest.mark.asyncio
    async def test_p08_skip_mcp_runs_critique_only(self):
        """skip_mcp=True: no MCP phases, direct critique only."""
        try:
            _set_p08_prompts()
            from scripts.p05_harness.loop_runner import LoopRunner
            from scripts.p05_harness.validators.rubric import CritiqueResult

            passing = CritiqueResult(
                candidate_id="T001", iteration=0,
                scores={"literature_coverage": 4, "technical_feasibility": 4,
                        "innovation_clarity": 4, "data_accessibility": 4,
                        "gap_alignment": 4, "evaluation_rigor": 4},
                weighted_score=4.0, passed=True)

            with (
                patch("scripts.p05_harness.loop_runner.generate_initial_plan",
                      new_callable=AsyncMock, return_value=P08_PLAN),
                patch("scripts.p05_harness.loop_runner.check_completeness") as mock_comp,
                patch("scripts.p05_harness.loop_runner.critique_plan",
                      new_callable=AsyncMock, return_value=passing),
                patch("scripts.p05_harness.loop_runner.check_literature_coverage") as mock_lit,
            ):
                mock_comp.return_value = MagicMock(
                    missing_fields=[], empty_fields=[], issues_count=0, is_complete=True)
                mock_lit.return_value = MagicMock(
                    evidence_card_count=0, cited_paper_count=0,
                    overlapping_count=0, coverage_ratio=0.0, status="ok")

                with tempfile.TemporaryDirectory() as tmp:
                    runner = LoopRunner(
                        config=P08_CONFIG, output_dir=Path(tmp),
                        skip_mcp=True, run_name="test_p08_skip_mcp")
                    result = await runner.run(
                        candidates=[P08_CANDIDATE],
                        evidence_cards_by_candidate={}, gaps=[], hypotheses=[])

                cr = result.candidates[0]
                assert cr.error == ""
                assert cr.passed is True
                assert cr.repositioning_attempts == 0
                assert cr.novelty_verdict == {}
                assert cr.redteam_result == {}
        finally:
            _restore_p05_prompts()


# ── Card classification domain test ──────────────────────────────────────

class TestP08CardClassification:
    """Verify _classify_card_relation uses cross-ethnic card fields."""

    def test_classify_uses_cross_ethnic_fields(self):
        try:
            _set_p08_prompts()
            from scripts.p05_harness.loop_runner import _classify_card_relation

            card = {
                "card_id": "C001",
                "ancestry_comparison": "EUR_vs_EAS",
                "population_cohorts": ["UKB", "CKB"],
                "omics_layers": ["proteomics"],
                "trait": "type 2 diabetes",
                "cross_ethnic_replication": True,
                "method": "pQTL-coloc",
            }
            plan = {"summary_zh": "跨种族蛋白标志物验证"}

            result = _classify_card_relation(card, plan)
            assert isinstance(result, str)
            assert result in ("supports", "contradicts", "adjacent", "dataset", "method")
        finally:
            _restore_p05_prompts()


# ── P08 config schema tests ──────────────────────────────────────────────

class TestP08Config:
    """Verify p08 config.yaml is valid and loads correctly."""

    def test_config_loads_without_error(self):
        from scripts.p05_harness.config_schema import load_harness_config

        config_path = Path(__file__).parent.parent / "scripts" / "p08_harness" / "config.yaml"
        try:
            model = load_harness_config(str(config_path))
            assert model.project_id == "p08_cross_ethnic_multiomics"
            assert "P08" in model.harness_name
        finally:
            pass
