"""Archetype C: Single-Cell Multi-omics + AI (Foundation Models)."""

from archetypes.archetype_c_sc_ai.evidence_card import SCFMEvidenceCard
from archetypes.archetype_c_sc_ai.gap_patterns import ARCHETYPE_C_GAP_PATTERNS
from archetypes.archetype_c_sc_ai.skills.skill_03_fm_resource_collect import FMResourceCollect

ARCHETYPE_ID = "archetype_c_sc_ai"
ARCHETYPE_NAME = "Single-Cell Multi-omics + AI (Foundation Models)"

ARCHETYPE_C_SKILLS: dict[str, type] = {
    "s3_fm_resource_collect": FMResourceCollect,
}

__all__ = [
    "ARCHETYPE_ID",
    "ARCHETYPE_NAME",
    "SCFMEvidenceCard",
    "ARCHETYPE_C_GAP_PATTERNS",
    "ARCHETYPE_C_SKILLS",
]
