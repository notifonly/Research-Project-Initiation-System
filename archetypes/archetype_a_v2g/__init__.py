"""Archetype A: Variant-to-Function (V2G)."""

from archetypes.archetype_a_v2g.evidence_card import V2GEvidenceCard, BaseEvidenceCard
from archetypes.archetype_a_v2g.gap_patterns import ARCHETYPE_A_GAP_PATTERNS
from archetypes.archetype_a_v2g.skills import ARCHETYPE_A_SKILLS

ARCHETYPE_ID = "archetype_a_v2g"
ARCHETYPE_NAME = "Variant-to-Function (V2G)"

__all__ = [
    "ARCHETYPE_ID",
    "ARCHETYPE_NAME",
    "V2GEvidenceCard",
    "BaseEvidenceCard",
    "ARCHETYPE_A_GAP_PATTERNS",
    "ARCHETYPE_A_SKILLS",
]
