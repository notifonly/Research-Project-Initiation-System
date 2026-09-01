"""Tests for CoverageMatrix and CoverageCell."""

import pytest
from shared.evidence.coverage_matrix import CoverageCell, CoverageMatrix
from shared.evidence.base_card import BaseEvidenceCard, V2GEvidenceCard


class TestCoverageCell:
    def test_defaults(self):
        cell = CoverageCell()
        assert cell.card_count == 0
        assert not cell.has_fine_mapping
        assert not cell.has_colocalization
        assert not cell.has_replication
        assert not cell.data_available
        assert cell.card_ids == []
        assert cell.archetype_specific == {}

    def test_from_card_v2g(self):
        card = V2GEvidenceCard(
            card_id="test1",
            trait_label="trait1",
            lead_variant_rsid="rs123",
            functional_modality="eQTL",
            cell_type="blood",
            population_ancestry="EUR",
        )
        cell = CoverageCell.from_card(card)
        assert cell.card_count == 1
        assert cell.card_ids == ["test1"]
        assert not cell.has_fine_mapping

    def test_from_card_v2g_with_fields(self):
        card = V2GEvidenceCard(
            card_id="test2",
            fine_mapping_method="SuSiE",
            coloc_result="PP4=0.9",
            has_replication=True,
            raw_data_accession="GSE12345",
        )
        cell = CoverageCell.from_card(card)
        assert cell.has_fine_mapping
        assert cell.has_colocalization
        assert cell.has_replication
        assert cell.data_available

    def test_from_card_base(self):
        card = BaseEvidenceCard(card_id="test3")
        cell = CoverageCell.from_card(card)
        assert cell.card_count == 1
        assert not cell.has_fine_mapping

    def test_archetype_specific_from_card(self):
        card = BaseEvidenceCard(card_id="test4", archetype="test_arch")
        cell = CoverageCell.from_card(card)
        assert cell.archetype_specific.get("archetype") == "test_arch"


class TestCoverageMatrix:
    def test_init_default_axes(self):
        m = CoverageMatrix()
        assert m.AXES == ("trait", "locus", "functional_modality", "cell_type", "population_ancestry")

    def test_init_custom_axes(self):
        m = CoverageMatrix(axes=["trait", "ancestry", "prs_method"])
        assert m.AXES == ("trait", "ancestry", "prs_method")

    def test_add_card(self):
        m = CoverageMatrix()
        card = V2GEvidenceCard(
            card_id="c1",
            trait_label="T2D",
            lead_variant_rsid="rs789",
            functional_modality="eQTL",
            cell_type="islet",
            population_ancestry="EUR",
        )
        m.add_card(card)
        assert len(m.all_cells()) == 1

    def test_jaccard_identical(self):
        m1 = CoverageMatrix()
        m2 = CoverageMatrix()
        card = V2GEvidenceCard(card_id="c1", trait_label="T1")
        m1.add_card(card)
        m2.add_card(card)
        assert m1.jaccard(m2) == pytest.approx(1.0)

    def test_jaccard_disjoint(self):
        m1 = CoverageMatrix()
        m2 = CoverageMatrix()
        c1 = V2GEvidenceCard(card_id="c1", trait_label="T1")
        c2 = V2GEvidenceCard(card_id="c2", trait_label="T2")
        m1.add_card(c1)
        m2.add_card(c2)
        assert m1.jaccard(m2) == pytest.approx(0.0)

    def test_jaccard_partial(self):
        m1 = CoverageMatrix()
        m2 = CoverageMatrix()
        c1 = V2GEvidenceCard(card_id="c1", trait_label="T1", lead_variant_rsid="rs1")
        c2 = V2GEvidenceCard(card_id="c2", trait_label="T1", lead_variant_rsid="rs1", functional_modality="eQTL")
        m1.add_card(c1)
        m1.add_card(c2)
        m2.add_card(c1)
        assert m1.jaccard(m2) > 0 and m1.jaccard(m2) < 1

    def test_jaccard_empty(self):
        m1 = CoverageMatrix()
        m2 = CoverageMatrix()
        assert m1.jaccard(m2) == pytest.approx(0.0)

    def test_gap_cells(self):
        m = CoverageMatrix()
        card = V2GEvidenceCard(card_id="c1", trait_label="T1", lead_variant_rsid="rs1")
        m.add_card(card)
        gaps = m.gap_cells([
            {"trait": "T1", "locus": "rs1", "functional_modality": "unknown",
             "cell_type": "unknown", "population_ancestry": "unknown"},
            {"trait": "T2", "locus": "rs2", "functional_modality": "unknown",
             "cell_type": "unknown", "population_ancestry": "unknown"},
        ])
        assert len(gaps) == 1

    def test_summary(self):
        m = CoverageMatrix()
        card = V2GEvidenceCard(card_id="c1", trait_label="T1")
        m.add_card(card)
        s = m.summary()
        assert s["total_cells"] == 1
        assert s["total_cards"] == 1

    def test_summary_with_v2g_fields(self):
        m = CoverageMatrix()
        card = V2GEvidenceCard(
            card_id="c1", fine_mapping_method="SuSiE",
            coloc_result="PP4=0.9", has_replication=True,
        )
        m.add_card(card)
        s = m.summary()
        assert s.get("cells_with_fine_mapping") == 1
        assert s.get("cells_with_colocalization") == 1
        assert s.get("cells_with_replication") == 1

    def test_add_card_base_evidence(self):
        m = CoverageMatrix()
        card = BaseEvidenceCard(card_id="c1", archetype="prs")
        m.add_card(card)
        assert len(m.all_cells()) == 1

    def test_get_cell_nonexistent(self):
        m = CoverageMatrix()
        cell = m.get_cell({"trait": "X", "locus": "Y", "functional_modality": "Z",
                          "cell_type": "W", "population_ancestry": "V"})
        assert cell is None

    def test_occupied_keys(self):
        m = CoverageMatrix()
        assert m.occupied_keys() == set()
        card = V2GEvidenceCard(card_id="c1", trait_label="T1")
        m.add_card(card)
        assert len(m.occupied_keys()) == 1
