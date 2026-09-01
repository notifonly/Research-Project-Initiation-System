"""Archetype D (Multi-omics scoring) evidence card - phenotypic/aging/immune scoring evidence."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from shared.evidence.base_card import BaseEvidenceCard


class OmicsScoreEvidenceCard(BaseEvidenceCard):
    """Archetype D: Multi-omics phenotypic scoring evidence card.

    Captures aging clock / digital immunity / multi-omics score findings
    (one paper -> multiple cards).
    Coverage axes for archetype D:
      score_type x omics_layers x trait x validation_cohort x transportability.
    """

    archetype: str = "omics_score"

    score_name: Optional[str] = None
    score_type: Optional[str] = None
    score_family: Optional[str] = None
    omics_layers: list[str] = Field(default_factory=list)
    primary_omics_layer: Optional[str] = None
    trait_targeted: Optional[str] = None
    trait_efo: Optional[str] = None
    feature_count: Optional[int] = None
    feature_selection_method: Optional[str] = None
    model_type: Optional[str] = None
    model_algorithm: Optional[str] = None
    sample_size_discovery: Optional[int] = None
    sample_size_validation: Optional[int] = None
    age_range_min: Optional[float] = None
    age_range_max: Optional[float] = None
    population_ancestry: Optional[str] = None
    validation_cohort: Optional[str] = None
    external_validation: Optional[bool] = None
    eval_metric_name: Optional[str] = None
    eval_metric_value: Optional[float] = None
    auc: Optional[float] = None
    c_index: Optional[float] = None
    correlation_target: Optional[float] = None
    mae: Optional[float] = None
    calibration_method: Optional[str] = None
    calibration_result: Optional[str] = None
    transportability_tested: Optional[bool] = None
    transportability_result: Optional[str] = None
    clinical_cutoff: Optional[float] = None
    comparison_to_clinical_score: Optional[str] = None
    longitudinal_eval: Optional[bool] = None
    interpretability_method: Optional[str] = None
    sex_stratified: Optional[bool] = None
    cell_type_specific: Optional[bool] = None
    code_available: Optional[bool] = None
    weights_available: Optional[bool] = None
    data_available: Optional[bool] = None
    raw_data_accession: Optional[str] = None

    def coverage_axes(self) -> dict:
        return {
            "score_type": self.score_type or self.score_family or "unknown",
            "omics_layers": "|".join(sorted(self.omics_layers)) if self.omics_layers else (self.primary_omics_layer or "unknown"),
            "trait": self.trait_targeted or self.trait_efo or "unknown",
            "validation_cohort": self.validation_cohort or ("external" if self.external_validation else "none"),
            "transportability": "tested" if self.transportability_tested else "untested",
        }


__all__ = ["OmicsScoreEvidenceCard"]
