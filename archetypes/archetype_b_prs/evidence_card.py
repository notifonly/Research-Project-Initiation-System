"""Archetype B (PRS) evidence card - Polygenic Risk Score methods evidence."""

from __future__ import annotations

from typing import Optional


from shared.evidence.base_card import BaseEvidenceCard


class PRSEvidenceCard(BaseEvidenceCard):
    """Archetype B: Polygenic Risk Score evidence card.

    Captures PRS methodological and validation findings (one paper -> multiple cards).
    Coverage axes for archetype B: trait x ancestry x prs_method x validation_cohort x transportability.
    """

    archetype: str = "prs"

    trait_efo: Optional[str] = None
    trait_label: Optional[str] = None
    target_population: Optional[str] = None
    discovery_ancestry: Optional[str] = None
    validation_ancestry: Optional[str] = None
    sample_size_discovery: Optional[int] = None
    sample_size_validation: Optional[int] = None
    n_snps_in_prs: Optional[int] = None
    prs_method: Optional[str] = None
    prs_method_family: Optional[str] = None
    clumping_threshold: Optional[float] = None
    p_value_threshold: Optional[float] = None
    effect_size_metric: Optional[str] = None
    effect_size_value: Optional[float] = None
    auc: Optional[float] = None
    or_per_sd: Optional[float] = None
    c_index: Optional[float] = None
    baseline_risk: Optional[float] = None
    calibration_method: Optional[str] = None
    calibration_result: Optional[str] = None
    transportability_tested: Optional[bool] = None
    transportability_result: Optional[str] = None
    validation_cohort: Optional[str] = None
    external_validation: Optional[bool] = None
    interaction_terms: Optional[bool] = None
    rare_variants_included: Optional[bool] = None
    summary_stats_available: Optional[bool] = None
    code_available: Optional[bool] = None
    weights_available: Optional[bool] = None
    raw_data_accession: Optional[str] = None

    def coverage_axes(self) -> dict:
        return {
            "trait": self.trait_label or self.trait_efo or "unknown",
            "ancestry": self.validation_ancestry or self.discovery_ancestry or "unknown",
            "prs_method": self.prs_method or self.prs_method_family or "unknown",
            "validation_cohort": self.validation_cohort or ("external" if self.external_validation else "none"),
            "transportability": (
                "tested" if self.transportability_tested else
                "untested"
            ),
        }


__all__ = ["PRSEvidenceCard"]
