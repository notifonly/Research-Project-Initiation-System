"""Archetype B: Polygenic Risk Score Methods (PRS)."""

from archetypes.archetype_b_prs.evidence_card import PRSEvidenceCard
from archetypes.archetype_b_prs.gap_patterns import ARCHETYPE_B_GAP_PATTERNS
from archetypes.archetype_b_prs.skills.skill_03_prs_study_collect import PRSStudyCollect

ARCHETYPE_ID = "archetype_b_prs"
ARCHETYPE_NAME = "Polygenic Risk Score Methods (PRS)"

ARCHETYPE_B_SKILLS: dict[str, type] = {
    "s3_prs_study_collect": PRSStudyCollect,
}

__all__ = [
    "ARCHETYPE_ID",
    "ARCHETYPE_NAME",
    "PRSEvidenceCard",
    "ARCHETYPE_B_GAP_PATTERNS",
    "ARCHETYPE_B_SKILLS",
]
