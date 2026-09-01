"""Archetype F: Spatial GWAS Network — scGWAS × Spatial Transcriptomics Network Module Discovery."""

from archetypes.archetype_f_spatial_gwas.evidence_card import SpatialGWASCard
from archetypes.archetype_f_spatial_gwas.gap_patterns import ARCHETYPE_F_GAP_PATTERNS

ARCHETYPE_ID = "archetype_f_spatial_gwas"
ARCHETYPE_NAME = "Spatial GWAS Network (scGWAS × ST)"

ARCHETYPE_F_SKILLS: dict[str, type] = {}

__all__ = [
    "ARCHETYPE_ID",
    "ARCHETYPE_NAME",
    "SpatialGWASCard",
    "ARCHETYPE_F_GAP_PATTERNS",
    "ARCHETYPE_F_SKILLS",
]
