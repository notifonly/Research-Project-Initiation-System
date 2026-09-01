"""Archetype E (Cross-Ethnic) gap pattern library - 10 patterns for cross-ethnic multi-omics research."""

from __future__ import annotations

from shared.skills.skill_11_gap_analysis import GapPattern


ARCHETYPE_E_GAP_PATTERNS: list[GapPattern] = [
    GapPattern(
        pattern_id="E1",
        name="single_population",
        description="Study conducted in single population only; no cross-ethnic comparison or replication attempted",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E2",
        name="no_cross_ethnic_replication",
        description="Multi-omics finding (biomarker/PRS/causal) not replicated in independent population; generalizability unproven",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E3",
        name="biomarker_portability_untested",
        description="Protein/metabolite biomarker discovered in one population (e.g. EUR); portability to other ethnicities (e.g. EAS) not tested",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E4",
        name="prs_transportability_untested",
        description="PRS transportability across ancestries not tested; performance drop in non-EUR populations unexplored",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E5",
        name="mr_not_cross_validated",
        description="Mendelian randomization causal estimate not validated in another population; potential population-specific confounding",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E6",
        name="single_omics_layer",
        description="Only single omics layer used (e.g. proteomics only); no multi-omics integration for cross-ethnic comparison",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E7",
        name="biobank_underutilized",
        description="Major biobank with multi-omics data available (UKB/FinnGen/Chinese cohort) but not used in study",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.30,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E8",
        name="harmonization_missing",
        description="Multi-omics or phenotype data not harmonized across populations; cross-ethnic comparison feasibility unclear",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E9",
        name="population_specific_confounded",
        description="Population-specific finding not adjusted for environment/lifestyle/diet confounders; false population specificity risk",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.30,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="E10",
        name="cross_archetype_unexplored",
        description="Cross-ethnic multi-omics bridge to V2G (archetype A) or scFM (archetype C) unexplored; population-specific mechanisms unresolved",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.30,
    ),
]


__all__ = ["ARCHETYPE_E_GAP_PATTERNS"]
