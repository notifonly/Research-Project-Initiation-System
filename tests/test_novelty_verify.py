"""Regression tests for Phase 1.5 novelty verification and Phase 1.6 red-team.

Covers the 3 problematic p05 research directions identified in human surveys.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.p05_harness.validators.methodology_redteam import (
    RedTeamFinding,
    RedTeamOutput,
    _build_known_facts,
    _extract_data_claims,
    _extract_identifiers,
    _match_known_fact,
    _parse_json_response,
    format_redteam_warnings,
)
from scripts.p05_harness.validators.rubric import (
    BaseRubric,
    DefaultRubric,
    _apply_smooth_novelty_weights,
)
from scripts.p05_harness.mcp.search_engine import boost_recent
from scripts.p05_harness.phases.phase15_novelty_verify import (
    NoveltyClaim,
    NoveltyVerdict,
    Phase15Output,
    _aggregate_overall_verdict,
    _normalize_verdict,
    format_novelty_warnings,
)


# ── Non-LLM unit tests ────────────────────────────────────────────────

class TestNormalizeVerdict:
    def test_scooped(self):
        assert _normalize_verdict("scooped") == "scooped"
        assert _normalize_verdict("SCOOPED") == "scooped"

    def test_crowded(self):
        assert _normalize_verdict("crowded") == "crowded"
        assert _normalize_verdict("CROWDED") == "crowded"

    def test_adjacent(self):
        assert _normalize_verdict("adjacent") == "adjacent"
        assert _normalize_verdict("  adjac ent  ") == "adjacent"

    def test_clear(self):
        assert _normalize_verdict("clear") == "clear"
        assert _normalize_verdict("unknown") == "clear"


class TestAggregateOverallVerdict:
    def test_empty(self):
        assert _aggregate_overall_verdict([]) == "clear"

    def test_any_scooped_dominates(self):
        v = [
            NoveltyVerdict(claim="c1", verdict="scooped", closeness=""),
            NoveltyVerdict(claim="c2", verdict="clear", closeness=""),
        ]
        assert _aggregate_overall_verdict(v) == "scooped"

    def test_crowded_over_adjacent(self):
        v = [
            NoveltyVerdict(claim="c1", verdict="adjacent", closeness=""),
            NoveltyVerdict(claim="c2", verdict="crowded", closeness=""),
        ]
        assert _aggregate_overall_verdict(v) == "crowded"

    def test_adjacent_over_clear(self):
        v = [
            NoveltyVerdict(claim="c1", verdict="clear", closeness=""),
            NoveltyVerdict(claim="c2", verdict="clear", closeness=""),
            NoveltyVerdict(claim="c3", verdict="adjacent", closeness=""),
        ]
        assert _aggregate_overall_verdict(v) == "adjacent"

    def test_all_clear(self):
        v = [NoveltyVerdict(claim="c1", verdict="clear", closeness="")] * 3
        assert _aggregate_overall_verdict(v) == "clear"


class TestBoostRecent:
    def _make_paper(self, title: str, year: int, citations: int = 0, doi: str = "") -> dict[str, Any]:
        return {
            "title": title,
            "year": year,
            "citation_count": citations,
            "doi": doi,
            "abstract": "x" * 300,
        }

    def test_recent_papers_ranked_higher(self):
        papers = [
            self._make_paper("old", 2022),
            self._make_paper("recent", 2025),
        ]
        ranked = boost_recent(papers, boost_year=2024)
        assert ranked[0]["title"] == "recent"

    def test_high_citations_compensate_age(self):
        papers = [
            self._make_paper("old_cited", 2023, citations=500),
            self._make_paper("recent_uncited", 2025, citations=0),
        ]
        ranked = boost_recent(papers, boost_year=2024)
        assert ranked[0]["title"] == "old_cited"

    def test_truncated_to_top_k(self):
        papers = [self._make_paper(f"p{i}", 2022 + i) for i in range(20)]
        ranked = boost_recent(papers, boost_year=2024)
        assert len(ranked) == 20  # truncation happens externally

    def test_invalid_year_handled(self):
        papers = [
            self._make_paper("bad_year", 0),
            {"title": "no_year", "citation_count": 0, "abstract": ""},
        ]
        ranked = boost_recent(papers, boost_year=2024)
        assert len(ranked) == 2


class TestFormatNoveltyWarnings:
    def test_clear_returns_empty(self):
        out = Phase15Output(overall_verdict="clear")
        assert format_novelty_warnings(out) == ""

    def test_scooped_has_warnings(self):
        vd = {
            "claim": "首个多scFM路由智能体",
            "verdict": "scooped",
            "closeness": "PantheonOS 已实现模型路由",
            "closest_works": [
                {
                    "title": "PantheonOS: A Unified Framework",
                    "authors": "Smith et al.",
                    "year": "2026",
                    "venue": "NeurIPS",
                    "similarity": "实现了22个scFM的自动选择",
                }
            ],
            "comparison_table": [],
        }
        out = Phase15Output(
            overall_verdict="scooped",
            verdicts=[vd],
            suggested_repositioning="收窄为学习型细粒度路由",
        )
        text = format_novelty_warnings(out)
        assert "首个多scFM路由智能体" in text
        assert "scooped" in text
        assert "PantheonOS" in text

    def test_crowded_with_comparison_table(self):
        vd = {
            "claim": "首个自进化的单细胞基准",
            "verdict": "crowded",
            "closeness": "已有3个自进化基准方法",
            "closest_works": [],
            "comparison_table": [
                {"dimension": "method", "our_approach": "scFM eval", "existing_work": "LLM eval"}
            ],
        }
        out = Phase15Output(overall_verdict="crowded", verdicts=[vd])
        text = format_novelty_warnings(out)
        assert "crowded" in text
        assert "对比维度" in text


class TestFormatRedteamWarnings:
    def test_empty(self):
        out = RedTeamOutput()
        assert format_redteam_warnings(out) == ""

    def test_high_severity(self):
        out = RedTeamOutput(
            findings=[
                RedTeamFinding(
                    check="data_leakage",
                    severity="high",
                    detail="CELLxGENE used without snapshot",
                    suggestion="specify release date",
                )
            ],
            high_count=1,
        )
        text = format_redteam_warnings(out)
        assert "高风险问题" in text
        assert "CELLxGENE" in text

    def test_unverified_claims(self):
        out = RedTeamOutput(
            findings=[RedTeamFinding(check="reproducibility", severity="low", detail="no seed", suggestion="add seed")],
            low_count=1,
            unverified_claims=[{"claim_text": "36M cells", "status": "unverified", "identifiers": []}],
        )
        text = format_redteam_warnings(out)
        assert "未核实" in text
        assert "36M" in text


class TestParseJsonResponse:
    def test_plain_json(self):
        assert _parse_json_response('[{"a": 1}]') == [{"a": 1}]

    def test_markdown_wrapped(self):
        raw = '```json\n{"key": "val"}\n```'
        assert _parse_json_response(raw) == {"key": "val"}


class TestExtractDataClaims:
    def test_scale_claims_cn(self):
        plan = {"summary_zh": "覆盖100万个细胞和36万样本"}
        claims = _extract_data_claims(plan)
        assert len(claims) >= 1
        assert any("100万" in c["claim_text"] or "36万" in c["claim_text"] for c in claims)

    def test_scale_claims_en(self):
        plan = {"summary_zh": "dataset with 10 million cells from HCA"}
        claims = _extract_data_claims(plan)
        assert any("10 million" in c["claim_text"] for c in claims)

    def test_data_source_claims(self):
        plan = {
            "summary_zh": "",
            "data_sources_detail": [
                {"name": "CELLxGENE", "url": "https://cellxgene.cziscience.com/collections/abc", "desc": "test"},
            ],
        }
        claims = _extract_data_claims(plan)
        assert any("CELLxGENE" in c["claim_text"] for c in claims)


class TestExtractIdentifiers:
    def test_doi(self):
        ids = _extract_identifiers("https://doi.org/10.1038/s41588-023-01456-z")
        assert any("10.1038" in i for i in ids)

    def test_gse(self):
        ids = _extract_identifiers("GSE207422 data used")
        assert "GSE207422" in ids

    def test_pmid(self):
        ids = _extract_identifiers("PMID: 37968348 referenced")
        assert "37968348" in ids

    def test_github(self):
        ids = _extract_identifiers("code at github.com/lab/rna-tool")
        assert "github.com/lab/rna-tool" in ids


class TestKnownFacts:
    def test_match_by_doi(self):
        facts = _build_known_facts([{"paper_doi": "10.1038/test", "paper_title": "test"}])
        claim = {"claim_text": "test", "identifiers": ["10.1038/test"]}
        assert _match_known_fact(claim, facts)

    def test_match_by_numeric_value(self):
        facts = _build_known_facts([{"paper_title": "test", "paper_abstract": "包含36M个细胞"}])
        claim = {"claim_text": "36M cells", "identifiers": []}
        assert _match_known_fact(claim, facts)

    def test_no_match(self):
        facts = _build_known_facts([{"paper_title": "other", "paper_abstract": "other"}])
        claim = {"claim_text": "36M cells", "identifiers": ["GSE12345"]}
        assert not _match_known_fact(claim, facts)


# ── Perverse incentive fix ────────────────────────────────────────────

class TestPerverseIncentiveFix:
    """Verify _apply_smooth_novelty_weights no longer reduces literature weight for low competition."""

    def test_low_competition_preserves_weight(self):
        rubric = DefaultRubric()
        original_weight = rubric.dimension_weights["literature_coverage"]
        candidate = {"scores": {"competitiveness": 0.03}}
        _apply_smooth_novelty_weights(rubric, candidate)
        assert rubric.dimension_weights["literature_coverage"] == original_weight

    def test_low_competition_sets_guidance(self):
        rubric = DefaultRubric()
        candidate = {"scores": {"competitiveness": 0.03}}
        _apply_smooth_novelty_weights(rubric, candidate)
        assert rubric.novelty_guidance != ""
        assert "低竞争方向" in rubric.novelty_guidance

    def test_normal_competition_no_change(self):
        rubric = DefaultRubric()
        candidate = {"scores": {"competitiveness": 0.35}}
        _apply_smooth_novelty_weights(rubric, candidate)
        assert rubric.novelty_guidance == ""

    def test_no_scores_no_change(self):
        rubric = DefaultRubric()
        candidate: dict[str, Any] = {}
        _apply_smooth_novelty_weights(rubric, candidate)
        assert rubric.novelty_guidance == ""

    def test_cross_domain_guidance(self):
        from scripts.p05_harness.validators.rubric import CrossDomainRubric
        rubric = CrossDomainRubric()
        candidate = {"scores": {"competitiveness": 0.02}}
        _apply_smooth_novelty_weights(rubric, candidate)
        assert "跨学科" in rubric.novelty_guidance


# ── Regression tests: 3 known problematic p05 directions ──────────────

class TestNoveltyVerdict:
    """Verify verdict dataclass default values."""
    def test_defaults(self):
        v = NoveltyVerdict(claim="c1", verdict="clear", closeness="ok")
        assert v.closest_works == []
        assert v.comparison_table == []
        assert v.evidence_links == []

class TestPhase15Output:
    """Verify output dataclass default values."""
    def test_defaults(self):
        o = Phase15Output()
        assert o.claims == []
        assert o.verdicts == []
        assert o.overall_verdict == "clear"
        assert o.repositioning_required is False

class TestRedTeamFinding:
    def test_defaults(self):
        f = RedTeamFinding(check="data_leakage", severity="high", detail="test", suggestion="fix")
        assert f.evidence == []

class TestRedTeamOutput:
    def test_defaults(self):
        o = RedTeamOutput()
        assert o.findings == []
        assert o.high_count == 0


# ── Integration tests with mocked LLM ─────────────────────────────────

SCOOPED_LLM_CLAIMS_EXTRACT = json.dumps([
    {"claim": "首个多scFM路由智能体", "source": "innovation_points[0]"},
    {"claim": "首次实现22个scFM模型的自动选择与执行", "source": "summary_zh"},
], ensure_ascii=False)

SCOOPED_LLM_QUERIES = json.dumps([
    {
        "claim_index": 0,
        "claim": "首个多scFM路由智能体",
        "queries": [
            "scFM router agent single-cell",
            "single-cell foundation model selection agent",
            "multi-model routing bioinformatics",
            "PantheonOS scFM selector",
        ],
    },
    {
        "claim_index": 1,
        "claim": "首次实现22个scFM模型的自动选择与执行",
        "queries": [
            "automatic scFM model selection execution",
            "22 foundation model single cell benchmark",
        ],
    },
], ensure_ascii=False)

SCOOPED_LLM_JUDGE = json.dumps([
    {
        "claim": "首个多scFM路由智能体",
        "verdict": "scooped",
        "closeness": "PantheonOS (2026-02) 已实现 scFM Router，支持22个模型自动选择与执行，概念与本方案核心声明完全重合。",
        "closest_works": [
            {
                "title": "PantheonOS: A Unified Framework for scFM Selection",
                "authors": "Jones et al.",
                "year": "2026",
                "venue": "bioRxiv",
                "similarity": "实现了22个scFM模型的自动选择与执行路由",
                "doi": "10.1101/2026.02.15.123456",
            }
        ],
        "comparison_table": [
            {"dimension": "核心方法", "our_approach": "多scFM路由智能体", "existing_work": "PantheonOS Router"},
            {"dimension": "支持模型数", "our_approach": "未明确", "existing_work": "22个scFM"},
        ],
        "evidence_links": ["10.1101/2026.02.15.123456"],
    },
    {
        "claim": "首次实现22个scFM模型的自动选择与执行",
        "verdict": "crowded",
        "closeness": "PantheonOS 已实现类似功能，但22这个量级本身可能仍有空间。",
        "closest_works": [],
        "comparison_table": [],
        "evidence_links": [],
    },
], ensure_ascii=False)

PAPERS_FOR_CASE1 = [
    {
        "title": "PantheonOS: A Unified Framework for scFM Selection",
        "authors": ["Jones, A.", "Smith, B."],
        "year": 2026,
        "venue": "bioRxiv",
        "doi": "10.1101/2026.02.15.123456",
        "abstract": "PantheonOS introduces a model router agent that enables automatic selection among 22 single-cell foundation models.",
        "citation_count": 15,
    },
    {
        "title": "scGPT: Toward Building a Foundation Model for Single-Cell Multi-Omics",
        "authors": ["Cui, H."],
        "year": 2024,
        "venue": "Nature Methods",
        "doi": "10.1038/s41592-024-02201-0",
        "abstract": "scGPT is a generative pre-trained transformer...",
        "citation_count": 200,
    },
]

CROWDED_LLM_JUDGE = json.dumps([
    {
        "claim": "首个自进化的单细胞基准智能体",
        "verdict": "crowded",
        "closeness": "NLP领域已有Benchmark Self-Evolving (COLING 2025)、TRACE (ICLR 2026)、MAC-Bench (2026)，方法学先例存在。",
        "closest_works": [
            {
                "title": "Benchmark Self-Evolving: Automated Benchmark Evolution",
                "authors": "Li et al.",
                "year": "2025",
                "venue": "COLING",
                "similarity": "提出自进化基准框架，与本方案核心思想一致",
                "doi": "",
            },
        ],
        "comparison_table": [
            {"dimension": "领域", "our_approach": "单细胞组学", "existing_work": "自然语言处理"},
        ],
        "evidence_links": [],
    },
], ensure_ascii=False)


class TestRegressionCase1RouterAgent:
    """Case 1: Multi-scFM Router Agent claimed 'first' but PantheonOS (2026) already exists."""

    @pytest.mark.asyncio
    async def test_scooped_verdict_blocks_candidate(self):
        from scripts.p05_harness.phases.phase15_novelty_verify import verify_novelty

        candidate = {
            "id": "T001",
            "research_question": "multi-scFM router agent for single-cell omics",
            "dimensions": {"method": "multi-scFM router", "disease": "pan-cancer"},
        }
        plan = {
            "candidate_id": "T001",
            "summary_zh": "首次提出多scFM路由智能体，实现22个scFM模型的自动选择与执行，填补C11缺口。",
            "innovation_points": [
                {"claim": "首个多scFM路由智能体", "closest_existing_work": "", "difference": "", "evidence_refs": []},
            ],
        }

        search_engine = MagicMock()
        search_engine.search_multi = AsyncMock(return_value=PAPERS_FOR_CASE1)

        with patch("scripts.p05_harness.phases.phase15_novelty_verify.llm_complete") as mock_llm:
            # Sequence: claims extract → query gen → overlap judge
            mock_llm.side_effect = [
                SCOOPED_LLM_CLAIMS_EXTRACT,
                SCOOPED_LLM_QUERIES,
                SCOOPED_LLM_JUDGE,
            ]

            config = {
                "novelty_check": {
                    "enabled": True,
                    "max_claims": 5,
                    "queries_per_claim": 4,
                    "top_k_papers": 15,
                    "max_per_source": 10,
                    "recent_boost_year": 2024,
                    "reposition_max_attempts": 1,
                },
            }
            result = await verify_novelty(plan, candidate, search_engine, config)

            assert result.overall_verdict == "scooped"
            assert result.repositioning_required is True
            assert len(result.verdicts) >= 1
            assert any(v.get("verdict") == "scooped" for v in result.verdicts)

    @pytest.mark.asyncio
    async def test_disabled_novelty_check_skips(self):
        from scripts.p05_harness.phases.phase15_novelty_verify import verify_novelty

        candidate = {"id": "T001"}
        plan = {"summary_zh": "test plan"}
        search_engine = MagicMock()

        config = {"novelty_check": {"enabled": False}}
        result = await verify_novelty(plan, candidate, search_engine, config)

        assert result.overall_verdict == "clear"
        assert result.verdicts == []

    @pytest.mark.asyncio
    async def test_all_three_llm_stages_called(self):
        """Verify the full claim→query→judge pipeline with 3 LLM calls."""
        from scripts.p05_harness.phases.phase15_novelty_verify import verify_novelty

        candidate = {"id": "T001"}
        plan = {"summary_zh": "novelty claim here"}
        search_engine = MagicMock()
        search_engine.search_multi = AsyncMock(return_value=[
            {"title": "related work", "year": 2024, "abstract": "...", "citation_count": 5}
        ])

        with patch("scripts.p05_harness.phases.phase15_novelty_verify.llm_complete") as mock_llm:
            mock_llm.side_effect = [
                json.dumps([{"claim": "test claim", "source": "summary"}]),
                json.dumps([{"claim_index": 0, "claim": "test claim", "queries": ["query1"]}]),
                json.dumps([{"claim": "test claim", "verdict": "clear", "closeness": "no match"}]),
            ]

            config = {"novelty_check": {"enabled": True, "max_claims": 5, "queries_per_claim": 4, "top_k_papers": 15, "max_per_source": 10, "recent_boost_year": 2024}}
            result = await verify_novelty(plan, candidate, search_engine, config)

            assert result.overall_verdict == "clear"
            assert mock_llm.call_count == 3


class TestRegressionCase2SelfEvolvingBenchmark:
    """Case 2: Self-Evolving Benchmark Agent — NLP prior art exists, should be crowded not clear."""

    @pytest.mark.asyncio
    async def test_crowded_when_prior_art_found(self):
        from scripts.p05_harness.phases.phase15_novelty_verify import verify_novelty

        candidate = {
            "id": "T002",
            "research_question": "self-evolving single-cell benchmark agent",
            "dimensions": {"method": "self-evolving benchmark", "disease": "pan-cancer"},
        }
        plan = {
            "candidate_id": "T002",
            "summary_zh": "首个自进化的单细胞基准智能体，动态更新评估样本和指标。",
        }

        search_engine = MagicMock()
        search_engine.search_multi = AsyncMock(return_value=[
            {"title": "MAC-Bench: Multi-Agent ...", "year": 2026, "abstract": "dynamic benchmark...", "citation_count": 10},
        ])

        with patch("scripts.p05_harness.phases.phase15_novelty_verify.llm_complete") as mock_llm:
            mock_llm.side_effect = [
                json.dumps([{"claim": "首个自进化的单细胞基准智能体", "source": "summary_zh"}]),
                json.dumps([{"claim_index": 0, "claim": "首个自进化...", "queries": ["self-evolving benchmark", "dynamic evaluation benchmark"]}]),
                CROWDED_LLM_JUDGE,
            ]

            config = {
                "novelty_check": {
                    "enabled": True, "max_claims": 5, "queries_per_claim": 4, "top_k_papers": 15,
                    "max_per_source": 10, "recent_boost_year": 2024, "reposition_max_attempts": 1,
                },
            }
            result = await verify_novelty(plan, candidate, search_engine, config)

            assert result.overall_verdict == "crowded"
            assert result.repositioning_required is True


class TestRegressionCase3ContextualBandit:
    """Case 3: Contextual Bandit model selection — ROGI 2025 prior art, conflicted feedback signal."""

    @pytest.mark.asyncio
    async def test_scooped_when_rogi_prior_exists(self):
        from scripts.p05_harness.phases.phase15_novelty_verify import verify_novelty

        candidate = {
            "id": "T003",
            "research_question": "adaptive model selection using contextual bandit",
            "dimensions": {"method": "contextual bandit", "disease": "pan-cancer"},
        }
        plan = {
            "candidate_id": "T003",
            "summary_zh": "首个面向scFM部署的Contextual Bandit自适应模型选择框架。",
        }

        rogi_paper = {
            "title": "ROGI: Realistic Optimal Model Selection with Genetic Interaction",
            "authors": ["Wang, L."],
            "year": 2025,
            "venue": "NeurIPS",
            "doi": "10.48550/arXiv.2501.12345",
            "abstract": "ROGI selects optimal models via dataset features and genetic interaction patterns...",
            "citation_count": 25,
        }

        search_engine = MagicMock()
        search_engine.search_multi = AsyncMock(return_value=[rogi_paper])

        rogi_judge = json.dumps([
            {
                "claim": "首个面向scFM部署的Contextual Bandit自适应模型选择框架",
                "verdict": "crowded",
                "closeness": "ROGI (2025) 已实现基于数据集特征→模型推荐的bandit方法，但未针对scFM部署优化。",
                "closest_works": [
                    {
                        "title": "ROGI: Realistic Optimal Model Selection with Genetic Interaction",
                        "authors": "Wang et al.",
                        "year": "2025",
                        "venue": "NeurIPS",
                        "similarity": "已用bandit做数据集特征→模型推荐",
                        "doi": "10.48550/arXiv.2501.12345",
                    }
                ],
                "comparison_table": [
                    {"dimension": "方法", "our_approach": "Contextual Bandit", "existing_work": "Contextual Bandit（ROGI）"},
                    {"dimension": "应用领域", "our_approach": "单细胞组学", "existing_work": "遗传互作分析"},
                ],
                "evidence_links": ["10.48550/arXiv.2501.12345"],
            },
        ], ensure_ascii=False)

        with patch("scripts.p05_harness.phases.phase15_novelty_verify.llm_complete") as mock_llm:
            mock_llm.side_effect = [
                json.dumps([{"claim": "首个面向scFM部署的Contextual Bandit自适应模型选择框架", "source": "summary_zh"}]),
                json.dumps([{"claim_index": 0, "claim": "首个...", "queries": ["model selection bandit", "adaptive routing single-cell", "ROGI model selection"]}]),
                rogi_judge,
            ]

            config = {
                "novelty_check": {
                    "enabled": True, "max_claims": 5, "queries_per_claim": 4, "top_k_papers": 15,
                    "max_per_source": 10, "recent_boost_year": 2024, "reposition_max_attempts": 1,
                },
            }
            result = await verify_novelty(plan, candidate, search_engine, config)

            assert result.overall_verdict == "crowded"
            assert result.repositioning_required is True

    @pytest.mark.asyncio
    async def test_redteam_detects_feedback_contradiction(self):
        """Verify methodology red-team flags the bandit feedback loop contradiction."""
        from scripts.p05_harness.validators.methodology_redteam import run_redteam

        candidate = {"id": "T003", "dimensions": {"method": "contextual bandit"}}
        plan = {
            "candidate_id": "T003",
            "summary_zh": "用模型预测准确率作为Contextual Bandit的奖励信号，指导后续模型选择...使用了CELLxGENE的36M细胞数据。",
            "technical_roadmap": [
                {"step_name": "bandit训练", "desc": "用上一轮预测准确率作为奖励更新bandit策略"},
            ],
        }

        redteam_feedback = json.dumps([
            {
                "check": "feedback_validity",
                "severity": "high",
                "detail": "方案存在循环矛盾：用模型预测准确率指导选择，但选择正是为了最大化预测准确率——这构成在测试集上训练的逻辑等价。",
                "suggestion": "改用部署无关的元特征（如数据集规模、稀疏度、噪声估计）作为bandit上下文，或使用holdout-based的离线评估。",
                "evidence": ["technical_roadmap[0]"],
            },
            {
                "check": "data_leakage",
                "severity": "high",
                "detail": "CELLxGENE 是持续更新的资源，方案未指定快照版本，评测结果不可复现。",
                "suggestion": "指定 CELLxGENE 的具体 release 版本号或发布日期快照。",
                "evidence": ["data_sources_detail"],
            },
            {
                "check": "baseline_adequacy",
                "severity": "medium",
                "detail": "缺少 oracle 基线和随机基线，只比较固定模型。",
                "suggestion": "添加 best-single-model oracle 和 random-selection baseline。",
                "evidence": [],
            },
        ], ensure_ascii=False)

        with patch("scripts.p05_harness.validators.methodology_redteam.llm_complete") as mock_llm:
            mock_llm.side_effect = [redteam_feedback]

            output = await run_redteam(plan, candidate, search_engine=None, evidence_cards=[], novelty_papers=[])

            assert output.high_count >= 2
            high_checks = [f.check for f in output.findings if f.severity == "high"]
            assert "feedback_validity" in high_checks
            assert "data_leakage" in high_checks or any("CELLxGENE" in f.detail for f in output.findings)
