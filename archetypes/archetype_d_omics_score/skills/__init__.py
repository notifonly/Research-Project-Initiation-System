"""Archetype D (OmicsScore) specialized skills."""
from archetypes.archetype_d_omics_score.skills.skill_03_score_method_collect import ScoreMethodCollect

ARCHETYPE_D_SKILLS = {
    "s3_score_method_collect": ScoreMethodCollect,
}

__all__ = ["ScoreMethodCollect", "ARCHETYPE_D_SKILLS"]
