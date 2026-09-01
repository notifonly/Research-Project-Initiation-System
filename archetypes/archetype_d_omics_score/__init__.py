"""Archetype D: Multi-omics Phenotypic Scoring (Aging / Digital Immunity)."""

from archetypes.archetype_d_omics_score.evidence_card import OmicsScoreEvidenceCard
from archetypes.archetype_d_omics_score.gap_patterns import ARCHETYPE_D_GAP_PATTERNS
from archetypes.archetype_d_omics_score.skills.skill_03_score_method_collect import ScoreMethodCollect

ARCHETYPE_ID = "archetype_d_omics_score"
ARCHETYPE_NAME = "Multi-omics Phenotypic Scoring"

ARCHETYPE_D_SKILLS: dict[str, type] = {
    "s3_score_method_collect": ScoreMethodCollect,
}

__all__ = [
    "ARCHETYPE_ID",
    "ARCHETYPE_NAME",
    "OmicsScoreEvidenceCard",
    "ARCHETYPE_D_GAP_PATTERNS",
    "ARCHETYPE_D_SKILLS",
]
