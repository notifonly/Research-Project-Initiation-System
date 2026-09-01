"""Regression tests for CrossEthnicCardExtract (Archetype E S7)."""

from unittest.mock import MagicMock

import pytest

from archetypes.archetype_e_cross_ethnic.evidence_card import CrossEthnicOmicsCard
from archetypes.archetype_e_cross_ethnic.skills.skill_07_cross_ethnic_card_extract import (
    CrossEthnicCardExtract,
    CrossEthnicExtractInput,
    CrossEthnicExtractOutput,
    ExtractTarget,
)
from shared.skills.base_skill import SkillContext


def _make_ctx() -> SkillContext:
    from shared.core.token_budget import TokenBudget
    return SkillContext(
        project_id="test",
        mcp_registry=MagicMock(),
        card_store=MagicMock(),
        context=MagicMock(),
        budget=TokenBudget(project_id="test"),
    )


class TestCrossEthnicCardDefaults:
    def test_defaults(self):
        card = CrossEthnicOmicsCard()
        assert card.archetype == "cross_ethnic"
        assert card.ancestry_comparison is None
        assert card.omics_layers == []

    def test_deep_read_fields_present(self):
        card = CrossEthnicOmicsCard(evidence_status="directly_stated",
                                    deep_read_source="paper_1")
        assert card.evidence_status == "directly_stated"
        assert card.deep_read_source == "paper_1"

    def test_coverage_axes_populated(self):
        card = CrossEthnicOmicsCard(
            ancestry_comparison="EUR_vs_EAS",
            omics_layers=["proteomics"],
            trait="type 2 diabetes",
            method="PRS-CSx",
            cross_ethnic_replication=True,
        )
        axes = card.coverage_axes()
        assert axes["ancestry_comparison"] == "EUR_vs_EAS"
        assert axes["omics_layers"] == "proteomics"
        assert axes["trait"] == "type 2 diabetes"
        assert axes["method"] == "PRS-CSx"
        assert axes["portability"] == "replicated"

    def test_coverage_axes_unknown_when_empty(self):
        axes = CrossEthnicOmicsCard().coverage_axes()
        assert set(axes.values()) == {"unknown"}


class TestCrossEthnicEnumMatching:
    def test_ancestry_pair(self):
        result = CrossEthnicCardExtract._extract_ancestry_comparison(
            "we compared european (uk biobank) and chinese (kadoorie) cohorts"
        )
        assert result == "EUR_vs_EAS"

    def test_ancestry_single(self):
        result = CrossEthnicCardExtract._extract_ancestry_comparison(
            "analysis restricted to african american individuals"
        )
        assert result == "AFR"

    def test_omics_multi(self):
        result = CrossEthnicCardExtract._match_all(
            "we integrated plasma proteomics (olink) and nmr metabolomics".lower(),
            CrossEthnicCardExtract._OMICS_VALUES,
            CrossEthnicCardExtract._OMICS_SYNONYMS,
        )
        assert "proteomics" in result
        assert "metabolomics" in result

    def test_method_prscsx(self):
        result = CrossEthnicCardExtract._match_enum(
            "we applied prs-csx for cross-ancestry polygenic scores".lower(),
            CrossEthnicCardExtract._METHOD_VALUES,
            CrossEthnicCardExtract._METHOD_SYNONYMS,
        )
        assert result == "PRS-CSx"

    def test_trait(self):
        result = CrossEthnicCardExtract._extract_trait(
            "genetic prediction of coronary artery disease".lower()
        )
        assert result == "coronary artery disease"

    def test_extract_fields_from_facts(self):
        fields = CrossEthnicCardExtract._extract_fields_from_facts(
            "PRS-CSx applied to proteomics biomarkers of type 2 diabetes across "
            "European (UK Biobank) and Chinese (China Kadoorie Biobank) cohorts, "
            "signal replicated across ancestries"
        )
        assert fields["ancestry_comparison"] == "EUR_vs_EAS"
        assert "proteomics" in fields["omics_layers"]
        assert fields["method"] == "PRS-CSx"
        assert fields["trait"] == "type 2 diabetes"
        assert fields["cross_ethnic_replication"] is True

    def test_extract_fields_unknown(self):
        fields = CrossEthnicCardExtract._extract_fields_from_facts(
            "this paper has no recognizable cross-ethnic multi-omics information"
        )
        assert fields["ancestry_comparison"] == ""
        assert fields["omics_layers"] == []
        assert fields["method"] == ""


class TestCrossEthnicQualityGate:
    @pytest.fixture
    def skill(self):
        return CrossEthnicCardExtract()

    @pytest.fixture
    def ctx(self):
        return _make_ctx()

    async def test_rejects_zero_findings(self, skill, ctx):
        output = CrossEthnicExtractOutput(
            skill_name="s7", cards=[], paper_count=5, findings_count=0, irrelevant_count=0)
        assert await skill.quality_gate(output, ctx) is False

    async def test_rejects_empty_key_finding(self, skill, ctx):
        cards = [
            CrossEthnicOmicsCard(card_id="c1", ancestry_comparison="EUR_vs_EAS", key_finding=""),
            CrossEthnicOmicsCard(card_id="c2", ancestry_comparison="EUR_vs_AFR", key_finding="f2"),
        ]
        output = CrossEthnicExtractOutput(
            skill_name="s7", cards=cards, paper_count=2, findings_count=2, irrelevant_count=0)
        assert await skill.quality_gate(output, ctx) is False

    async def test_rejects_low_fill_rate(self, skill, ctx):
        cards = [CrossEthnicOmicsCard(card_id=f"c{i}", key_finding=f"f{i}") for i in range(5)]
        output = CrossEthnicExtractOutput(
            skill_name="s7", cards=cards, paper_count=5, findings_count=5, irrelevant_count=0)
        assert await skill.quality_gate(output, ctx) is False

    async def test_passes_good_output(self, skill, ctx):
        cards = [
            CrossEthnicOmicsCard(card_id="c1", ancestry_comparison="EUR_vs_EAS", key_finding="f1"),
            CrossEthnicOmicsCard(card_id="c2", omics_layers=["proteomics"], key_finding="f2"),
            CrossEthnicOmicsCard(card_id="c3", trait="type 2 diabetes", key_finding="f3"),
        ]
        output = CrossEthnicExtractOutput(
            skill_name="s7", cards=cards, paper_count=3, findings_count=3, irrelevant_count=0)
        assert await skill.quality_gate(output, ctx) is True

    async def test_passes_single_paper_even_empty(self, skill, ctx):
        cards = [CrossEthnicOmicsCard(card_id="c1", key_finding="f1")]
        output = CrossEthnicExtractOutput(
            skill_name="s7", cards=cards, paper_count=1, findings_count=1, irrelevant_count=0)
        assert await skill.quality_gate(output, ctx) is True

    async def test_rejects_low_evidence_rate(self, skill, ctx):
        cards = [
            CrossEthnicOmicsCard(card_id="c1", ancestry_comparison="EUR_vs_EAS", key_finding="f1",
                                 deep_read_source="p1", evidence_status=None),
            CrossEthnicOmicsCard(card_id="c2", ancestry_comparison="EUR_vs_AFR", key_finding="f2",
                                 deep_read_source="p1", evidence_status=None),
            CrossEthnicOmicsCard(card_id="c3", omics_layers=["proteomics"], key_finding="f3",
                                 deep_read_source="p1", evidence_status="author_claim"),
        ]
        output = CrossEthnicExtractOutput(
            skill_name="s7", cards=cards, paper_count=3, findings_count=3, irrelevant_count=0)
        assert await skill.quality_gate(output, ctx) is False


class TestCrossEthnicIrrelevantFilter:
    def test_rejects_nursing(self):
        assert CrossEthnicCardExtract._is_irrelevant(
            "CVI scale validation study",
            "content validity index and face validity for nursing education",
        ) is True

    def test_accepts_cross_ethnic_paper(self):
        assert CrossEthnicCardExtract._is_irrelevant(
            "Cross-ancestry proteomic biomarker portability",
            "We validated plasma proteins across European and East Asian cohorts",
        ) is False


class TestCrossEthnicDeepRead:
    def test_constructs_cards_from_facts(self):
        import asyncio
        target = ExtractTarget(
            paper_id="test001",
            title="Cross-ethnic proteomic portability of type 2 diabetes biomarkers",
            doi="10.1234/example",
            year=2025,
        )
        note = {
            "paper_id": "test001",
            "facts": [
                {
                    "statement": "PRS-CSx applied to proteomics markers of type 2 diabetes, "
                                 "replicated across European (UK Biobank) and Chinese cohorts",
                    "evidence_status": "directly_stated",
                    "source_locator": {"section": "results"},
                }
            ],
            "judgments": [],
        }
        skill = CrossEthnicCardExtract()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                skill._extract_from_deep_read(target, note, CrossEthnicOmicsCard, "topic_x")
            )
        finally:
            loop.close()
        assert len(result) == 1
        card = result[0]
        assert card.archetype == "cross_ethnic"
        assert card.ancestry_comparison == "EUR_vs_EAS"
        assert "proteomics" in card.omics_layers
        assert card.method == "PRS-CSx"
        assert card.trait == "type 2 diabetes"
        assert card.evidence_status == "directly_stated"
        # 覆盖轴不再全为 unknown
        axes = card.coverage_axes()
        assert axes["ancestry_comparison"] != "unknown"
        assert axes["omics_layers"] != "unknown"


class TestCrossEthnicPaper:
    @pytest.mark.asyncio
    async def test_skips_short_text(self):
        target = ExtractTarget(paper_id="p1", title="Short", abstract="Too short")
        skill = CrossEthnicCardExtract()
        inp = CrossEthnicExtractInput(targets=[target], max_targets=5)
        ctx = _make_ctx()
        result = await skill._extract_from_paper(target, inp, ctx, CrossEthnicOmicsCard, "t1")
        assert result == []


class TestP08SkillRegistration:
    def test_extra_skills_registers_cross_ethnic_s7(self):
        from projects.p08_cross_ethnic_multiomics import tool_flow
        assert tool_flow.EXTRA_SKILLS["s7_evidence_card_extract"] is CrossEthnicCardExtract

    def test_archetype_e_skills_registered(self):
        from archetypes.archetype_e_cross_ethnic import ARCHETYPE_E_SKILLS
        assert ARCHETYPE_E_SKILLS["s7_evidence_card_extract"] is CrossEthnicCardExtract
