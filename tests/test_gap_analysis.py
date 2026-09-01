"""Tests for GapAnalysis skill."""

import pytest
from shared.skills.skill_11_gap_analysis import (
    GapAnalysis,
    GapAnalysisInput,
    GapPattern,
    IdentifiedGap,
)
from shared.evidence.base_card import BaseEvidenceCard, V2GEvidenceCard
from shared.evidence.coverage_matrix import CoverageMatrix


class TestGapPattern:
    def test_defaults(self):
        p = GapPattern(pattern_id="P1", name="test", description="test pattern")
        assert p.weight_evidence_asymmetry == 0.35
        assert p.weight_feasibility == 0.25
        assert p.weight_competition == 0.20
        assert p.weight_cross_archetype == 0.20


class TestIdentifiedGap:
    def test_defaults(self):
        g = IdentifiedGap(gap_id="G1", pattern_id="P1", axis="test", description="test gap")
        assert g.score == 0.0
        assert g.feasibility == 0.5
        assert g.competition == 0.5
        assert g.cross_archetype == 0.0
        assert g.supporting_cards == []


class TestGapAnalysis:
    @pytest.fixture
    def skill(self):
        return GapAnalysis()

    def test_derive_expected_axes_empty(self, skill):
        assert skill._derive_expected_axes([]) == []

    def test_derive_expected_axes_non_v2g(self, skill):
        cards = [BaseEvidenceCard(card_id="c1", archetype="prs")]
        result = skill._derive_expected_axes(cards)
        assert result == []

    def test_derive_expected_axes_v2g(self, skill):
        cards = [
            V2GEvidenceCard(
                card_id="c1",
                trait_label="T1",
                lead_variant_rsid="rs1",
                functional_modality="eQTL",
                cell_type="blood",
                population_ancestry="EUR",
            ),
        ]
        result = skill._derive_expected_axes(cards)
        assert len(result) == 1
        assert result[0]["trait"] == "T1"

    def test_has_v2g_fields_false(self, skill):
        cards = [BaseEvidenceCard(card_id="c1")]
        assert not skill._has_v2g_fields(cards)

    def test_has_v2g_fields_true(self, skill):
        cards = [V2GEvidenceCard(card_id="c1", fine_mapping_method="SuSiE")]
        assert skill._has_v2g_fields(cards)

    async def test_execute_empty(self, skill):
        inp = GapAnalysisInput(cards=[])
        out = await skill.execute(inp, None)
        assert len(out.gaps) > 0  # P10 is always added
        assert out.gap_cells == []

    async def test_execute_with_v2g_cards(self, skill):
        cards = [
            V2GEvidenceCard(
                card_id="c1",
                trait_label="T1",
                lead_variant_rsid="rs1",
                functional_modality="eQTL",
                cell_type="blood",
                population_ancestry="EUR",
            ),
            V2GEvidenceCard(
                card_id="c2",
                trait_label="T1",
                lead_variant_rsid="rs1",
                functional_modality="pQTL",
                cell_type="blood",
                population_ancestry="EUR",
            ),
        ]
        matrix = CoverageMatrix()
        for c in cards:
            matrix.add_card(c)
        inp = GapAnalysisInput(cards=cards, coverage_matrix=matrix)
        out = await skill.execute(inp, None)
        assert len(out.gaps) > 0
        # Should have some V2G-specific gaps
        pattern_ids = {g.pattern_id for g in out.gaps}
        assert "P10" in pattern_ids

    async def test_execute_with_base_cards(self, skill):
        cards = [
            BaseEvidenceCard(card_id="c1", archetype="prs"),
            BaseEvidenceCard(card_id="c2", archetype="prs"),
        ]
        matrix = CoverageMatrix(axes=["archetype"])
        for c in cards:
            matrix.add_card(c)
        inp = GapAnalysisInput(cards=cards, coverage_matrix=matrix)
        out = await skill.execute(inp, None)
        assert len(out.gaps) > 0
        # Should NOT have V2G-specific patterns
        v2g_patterns = {"P1", "P2", "P5", "P6", "P7", "P8"}
        pattern_ids = {g.pattern_id for g in out.gaps}
        assert not (v2g_patterns & pattern_ids)

    async def test_execute_with_gap_patterns_override(self, skill):
        cards = [
            V2GEvidenceCard(card_id="c1", trait_label="T1"),
        ]
        custom_pattern = GapPattern(
            pattern_id="B1",
            name="custom_gap",
            description="Custom pattern",
            weight_evidence_asymmetry=0.5,
            weight_feasibility=0.3,
            weight_competition=0.1,
            weight_cross_archetype=0.1,
        )
        inp = GapAnalysisInput(cards=cards, gap_patterns=[custom_pattern])
        out = await skill.execute(inp, None)
        assert len(out.gaps) > 0

    async def test_top_gaps_limited(self, skill):
        cards = [
            V2GEvidenceCard(card_id=f"c{i}", trait_label="T1",
                          lead_variant_rsid="rs1", functional_modality="eQTL",
                          cell_type="blood", population_ancestry="EUR")
            for i in range(5)
        ]
        inp = GapAnalysisInput(cards=cards)
        out = await skill.execute(inp, None)
        assert len(out.top_gaps) <= 5
