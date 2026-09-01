"""Archetype A (V2G) gap pattern library - 10 patterns specialized for variant-to-function research."""

from __future__ import annotations

from shared.skills.skill_11_gap_analysis import GapPattern


ARCHETYPE_A_GAP_PATTERNS: list[GapPattern] = [
    GapPattern(
        pattern_id="P1",
        name="functional_modality_missing",
        description="Locus has no functional modality evidence (eQTL/pQTL/sQTL/mQTL/etc.)",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P2",
        name="single_modality",
        description="Only one functional modality (e.g. eQTL only); no triangulation across modalities",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P3",
        name="cell_type_coverage_hole",
        description="Relevant cell type for trait has no functional evidence",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P4",
        name="cross_trait_borrowing",
        description="Functional evidence borrowed from another trait; not validated for target trait",
        weight_evidence_asymmetry=0.40,
        weight_feasibility=0.20,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P5",
        name="fine_mapping_missing",
        description="Locus lacks fine-mapping; credible set unknown",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P6",
        name="coloc_unverified",
        description="Colocalization between GWAS and QTL not tested",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.35,
        weight_competition=0.15,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P7",
        name="ancestry_single",
        description="All evidence from single ancestry (EUR only); no diversity",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.20,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P8",
        name="no_replication",
        description="No replication cohort; single-cohort findings",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P9",
        name="public_data_underexploited",
        description="Public datasets (GEO/ENCODE/CellxGene) available but unused",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.40,
        weight_competition=0.15,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="P10",
        name="cross_archetype_bridge",
        description="Bridge to PRS (archetype B) or foundation model (archetype C) unexplored",
        weight_evidence_asymmetry=0.20,
        weight_feasibility=0.20,
        weight_competition=0.20,
        weight_cross_archetype=0.40,
    ),
]


__all__ = ["ARCHETYPE_A_GAP_PATTERNS"]
