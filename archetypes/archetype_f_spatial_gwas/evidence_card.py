"""Archetype F (Spatial GWAS Network) evidence card — scGWAS × spatial transcriptomics network evidence."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from shared.evidence.base_card import BaseEvidenceCard


class SpatialGWASCard(BaseEvidenceCard):
    """Archetype F: Spatial GWAS Network evidence card.

    Captures evidence linking GWAS traits to spatial gene network modules:
    scGWAS-style dual-weight module search applied to spatial transcriptomics
    microdomain GSS scores. Coverage axes: trait x tissue_region x cell_type x
    spatial_platform x method.
    """

    archetype: str = "spatial_gwas_network"

    trait: Optional[str] = None
    trait_efo: Optional[str] = None
    tissue_region: Optional[str] = None
    cell_type: Optional[str] = None
    spatial_platform: Optional[str] = None
    spatial_resolution: Optional[str] = None
    spatial_dataset: Optional[str] = None
    microdomain_id: Optional[str] = None
    gss_score: Optional[float] = None
    network_method: Optional[str] = None
    module_genes: list[str] = Field(default_factory=list)
    module_size: Optional[int] = None
    module_score: Optional[float] = None
    ppi_network_used: Optional[str] = None
    spatial_graph_type: Optional[str] = None
    null_model: Optional[str] = None
    permutation_test_p: Optional[float] = None
    gwas_source: Optional[str] = None
    gwas_sample_size: Optional[int] = None
    population_ancestry: Optional[str] = None
    method: Optional[str] = None
    method_family: Optional[str] = None
    code_available: Optional[bool] = None
    data_available: Optional[bool] = None
    raw_data_accession: Optional[str] = None

    evidence_status: Optional[str] = None
    evidence_strength: Optional[str] = None
    deep_read_source: Optional[str] = None

    def coverage_axes(self) -> dict:
        return {
            "trait": self.trait or self.trait_efo or "unknown",
            "tissue_region": self.tissue_region or "unknown",
            "cell_type": self.cell_type or "unknown",
            "spatial_platform": self.spatial_platform or "unknown",
            "method": self.method or self.method_family or "unknown",
        }


__all__ = ["SpatialGWASCard"]
