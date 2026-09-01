"""Archetype E: Cross-Ethnic Multi-omics Integration."""

from archetypes.archetype_e_cross_ethnic.evidence_card import CrossEthnicOmicsCard
from archetypes.archetype_e_cross_ethnic.gap_patterns import ARCHETYPE_E_GAP_PATTERNS
from archetypes.archetype_e_cross_ethnic.skills.skill_07_cross_ethnic_card_extract import (
    CrossEthnicCardExtract,
)

ARCHETYPE_ID = "archetype_e_cross_ethnic"
ARCHETYPE_NAME = "Cross-Ethnic Multi-omics Integration (Cross-Ethnic)"

ARCHETYPE_E_SKILLS: dict[str, type] = {
    "s7_evidence_card_extract": CrossEthnicCardExtract,
}

__all__ = [
    "ARCHETYPE_ID",
    "ARCHETYPE_NAME",
    "CrossEthnicOmicsCard",
    "ARCHETYPE_E_GAP_PATTERNS",
    "ARCHETYPE_E_SKILLS",
]
