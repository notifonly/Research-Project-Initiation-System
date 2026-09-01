"""Tests for BaseEvidenceCard and archetype-specific cards."""

from shared.evidence.base_card import BaseEvidenceCard, V2GEvidenceCard


class TestBaseEvidenceCard:
    def test_defaults(self):
        card = BaseEvidenceCard()
        assert card.card_id.startswith("card_")
        assert card.source_type == "paper"
        assert card.archetype == "base"
        assert card.reliability_flag == "unverified"
        assert card.tags == []

    def test_minimal_construction(self):
        card = BaseEvidenceCard(
            key_finding="Test finding",
            method_brief="Test method",
        )
        assert card.key_finding == "Test finding"
        assert card.method_brief == "Test method"

    def test_coverage_axes_default(self):
        card = BaseEvidenceCard()
        assert card.coverage_axes() == {}

    def test_to_flat_dict(self):
        card = BaseEvidenceCard(
            card_id="test1",
            key_finding="finding",
        )
        flat = card.to_flat_dict()
        assert flat["card_id"] == "test1"
        assert "paper_" in str(list(flat.keys()))

    def test_extra_fields_ignored(self):
        card = BaseEvidenceCard.model_validate({"card_id": "test1", "unknown_field": "should_be_ignored"})
        assert not hasattr(card, "unknown_field")

    def test_tags(self):
        card = BaseEvidenceCard(tags=["tag1", "tag2"])
        assert "tag1|tag2" in card.to_flat_dict().get("tags_str", "")


class TestV2GEvidenceCard:
    def test_defaults(self):
        card = V2GEvidenceCard()
        assert card.archetype == "v2g"
        assert card.locus_genes == []

    def test_coverage_axes(self):
        card = V2GEvidenceCard(
            trait_label="T2D",
            lead_variant_rsid="rs123",
            functional_modality="eQTL",
            cell_type="islet",
            population_ancestry="EUR",
        )
        axes = card.coverage_axes()
        assert axes["trait"] == "T2D"
        assert axes["locus"] == "rs123"
        assert axes["functional_modality"] == "eQTL"
        assert axes["cell_type"] == "islet"
        assert axes["population_ancestry"] == "EUR"

    def test_coverage_axes_unknowns(self):
        card = V2GEvidenceCard()
        axes = card.coverage_axes()
        assert axes["trait"] == "unknown"
        assert axes["locus"] == "unknown"

    def test_all_fields(self):
        card = V2GEvidenceCard(
            trait_efo="EFO_0001360",
            trait_label="T2D",
            lead_variant_rsid="rs7903146",
            chrom="10",
            pos=114758349,
            locus_genes=["TCF7L2"],
            functional_modality="eQTL",
            cell_type="pancreatic_islet",
            tissue="pancreas",
            sample_size=10000,
            population_ancestry="EUR",
            p_value=5e-8,
            effect_size_beta=0.15,
            fine_mapping_method="SuSiE",
            coloc_result="PP4=0.95",
            has_replication=True,
            summary_stats_available=True,
            raw_data_accession="GSE12345",
        )
        assert card.trait_label == "T2D"
        assert card.lead_variant_rsid == "rs7903146"
        assert card.fine_mapping_method == "SuSiE"
        assert card.locus_genes == ["TCF7L2"]
