"""Archetype D (Multi-omics scoring) gap pattern library - 10 patterns for phenotypic scoring research."""

from __future__ import annotations

from shared.skills.skill_11_gap_analysis import GapPattern


ARCHETYPE_D_GAP_PATTERNS: list[GapPattern] = [
    GapPattern(
        pattern_id="D1",
        name="single_omics_layer",
        description="Score built on single omics layer (e.g. methylation only); no multi-omics integration",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D2",
        name="no_external_validation",
        description="Score validated only in discovery cohort; no external validation",
        weight_evidence_asymmetry=0.40,
        weight_feasibility=0.25,
        weight_competition=0.15,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D3",
        name="no_calibration",
        description="Score calibration not assessed; discrimination only",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D4",
        name="no_transportability",
        description="Score transportability across cohorts/ancestries not tested",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D5",
        name="narrow_age_range",
        description="Score trained/validated on narrow age range; generalization across age untested",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D6",
        name="single_ancestry",
        description="Score built on single ancestry; no cross-ancestry generalization",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.20,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D7",
        name="no_clinical_cutoff",
        description="No clinical risk cutoff/decision curve; score not clinically actionable",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D8",
        name="no_interpretability",
        description="No feature-level interpretability; biological meaning of score opaque",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.35,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D9",
        name="no_clinical_score_comparison",
        description="No comparison to existing clinical scores (e.g. Framingham, Charleston)",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="D10",
        name="no_longitudinal_eval",
        description="No longitudinal evaluation; cross-sectional only, no temporal predictive value",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
]


__all__ = ["ARCHETYPE_D_GAP_PATTERNS"]
