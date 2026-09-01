"""Archetype C (scAI) specialized skills."""
from archetypes.archetype_c_sc_ai.skills.skill_03_fm_resource_collect import FMResourceCollect

ARCHETYPE_C_SKILLS = {
    "s3_fm_resource_collect": FMResourceCollect,
}

__all__ = ["FMResourceCollect", "ARCHETYPE_C_SKILLS"]
