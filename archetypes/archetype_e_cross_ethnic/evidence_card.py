"""Archetype E (Cross-Ethnic) evidence card - cross-ethnic multi-omics integration evidence."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from shared.evidence.base_card import BaseEvidenceCard


class CrossEthnicOmicsCard(BaseEvidenceCard):
    """Archetype E: Cross-ethnic multi-omics evidence card.

    Captures cross-population multi-omics findings: biomarker portability,
    PRS transportability, and causal inference across ethnicities.
    Coverage axes: ancestry_comparison x omics_layers x trait x method x portability.
    """

    archetype: str = "cross_ethnic"

    ancestry_comparison: Optional[str] = None
    population_cohorts: list[str] = Field(default_factory=list)
    omics_layers: list[str] = Field(default_factory=list)
    primary_omics_layer: Optional[str] = None
    trait: Optional[str] = None
    trait_efo: Optional[str] = None
    harmonization_method: Optional[str] = None
    sample_size_pop1: Optional[int] = None
    sample_size_pop2: Optional[int] = None
    effect_size_pop1: Optional[float] = None
    effect_size_pop2: Optional[float] = None
    cross_ethnic_replication: Optional[bool] = None
    population_specific_finding: Optional[str] = None
    portability_score: Optional[float] = None
    method: Optional[str] = None
    method_family: Optional[str] = None
    eval_metric_name: Optional[str] = None
    eval_metric_value: Optional[float] = None
    biobank_source: Optional[str] = None
    code_available: Optional[bool] = None
    data_available: Optional[bool] = None
    raw_data_accession: Optional[str] = None

    # 深读增强字段 (与 archetype C 对齐, 供 S6C→S7 富集使用)
    evidence_status: Optional[str] = None
    evidence_strength: Optional[str] = None
    deep_read_source: Optional[str] = None

    def coverage_axes(self) -> dict:
        return {
            "ancestry_comparison": self.ancestry_comparison or "unknown",
            "omics_layers": "|".join(sorted(self.omics_layers)) if self.omics_layers else (self.primary_omics_layer or "unknown"),
            "trait": self.trait or self.trait_efo or "unknown",
            "method": self.method or self.method_family or "unknown",
            "portability": "replicated" if self.cross_ethnic_replication else (
                "tested" if self.cross_ethnic_replication is not None else "unknown"
            ),
        }


__all__ = ["CrossEthnicOmicsCard"]
