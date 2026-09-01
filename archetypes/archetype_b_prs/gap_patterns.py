"""Archetype B (PRS) gap pattern library - 10 patterns for statistical genetics methods research."""

from __future__ import annotations

from shared.skills.skill_11_gap_analysis import GapPattern


ARCHETYPE_B_GAP_PATTERNS: list[GapPattern] = [
    GapPattern(
        pattern_id="B1",
        name="ancestry_limited_discovery",
        description="PRS discovery performed in single ancestry (typically EUR); no cross-ancestry discovery",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B2",
        name="no_external_validation",
        description="PRS validated only in discovery cohort; no external validation cohort",
        weight_evidence_asymmetry=0.40,
        weight_feasibility=0.25,
        weight_competition=0.15,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B3",
        name="transportability_untested",
        description="PRS transportability across ancestries/populations not tested",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B4",
        name="method_comparison_missing",
        description="Only one PRS method used (e.g. P+T only); no benchmark vs LDpred2/PRScs/lassosum",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B5",
        name="polygenicity_threshold_unexplored",
        description="Single p-value threshold used; no threshold sensitivity sweep",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.35,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B6",
        name="rare_variant_exclusion",
        description="Rare variants (MAF<0.01) excluded without justification; no rare-variant PRS comparison",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B7",
        name="interaction_effects_missing",
        description="No gene-environment or sex-interaction terms in PRS model",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B8",
        name="calibration_untested",
        description="PRS calibration (slope/intercept) not assessed; predictive discrimination only",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B9",
        name="clinical_cutoff_absent",
        description="No clinical risk threshold/cutoff defined; no decision curve analysis",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="B10",
        name="cross_trait_prs_unused",
        description="Cross-trait PRS (e.g. using related traits to boost target PRS) unexplored",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.30,
    ),
]


__all__ = ["ARCHETYPE_B_GAP_PATTERNS"]
