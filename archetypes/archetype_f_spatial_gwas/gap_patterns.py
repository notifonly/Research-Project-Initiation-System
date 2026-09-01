"""Archetype F (Spatial GWAS Network) gap pattern library — 10 patterns for scGWAS × spatial transcriptomics."""

from __future__ import annotations

from shared.skills.skill_11_gap_analysis import GapPattern


ARCHETYPE_F_GAP_PATTERNS: list[GapPattern] = [
    GapPattern(
        pattern_id="F1",
        name="single_spatial_platform",
        description="Only single spatial platform used (e.g. 10x Visium); no cross-platform validation (MERFISH, Slide-seq, STARmap)",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F2",
        name="no_network_module",
        description="Spatial GWAS enrichment tested but no network module discovery performed; only spot-level enrichment, no gene co-expression network modules",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F3",
        name="ppi_module_no_spatial",
        description="Network module discovered on PPI but spatial context missing; module genes not mapped to spatial tissue microdomains",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F4",
        name="no_spatial_gradient",
        description="Module genes identified but spatial expression gradient/distance decay not quantified; no spatial autocorrelation analysis",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F5",
        name="single_trait",
        description="Only single GWAS trait analyzed; no cross-trait module comparison or pleiotropy analysis across traits",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F6",
        name="no_null_model",
        description="Module significance assessed without spatial permutation null model; spatial autocorrelation may inflate false positive rate",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F7",
        name="single_tissue",
        description="Only single tissue/region analyzed; cross-region module portability or tissue-specific module architecture not explored",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F8",
        name="no_cross_species",
        description="Module findings not validated in model organism spatial transcriptomics; cross-species module conservation untested",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.30,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F9",
        name="no_baseline_comparison",
        description="Method performance not compared against baseline approaches (MAGMA, LDSC-SEG, S-LDSC, scGWAS); relative improvement unquantified",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="F10",
        name="cross_archetype_unexplored",
        description="Spatial network module bridge to V2G (archetype A), scFM (archetype C), or cross-ethnic (archetype E) unexplored; mechanistic validation gap",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.30,
    ),
]


__all__ = ["ARCHETYPE_F_GAP_PATTERNS"]
