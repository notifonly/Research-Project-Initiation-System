"""Archetype A (V2G) specialized skills."""
from archetypes.archetype_a_v2g.skills.skill_03_v2g_locus_collect import V2GLocusCollect
from archetypes.archetype_a_v2g.skills.skill_10_functional_evidence_search import FunctionalEvidenceSearch

ARCHETYPE_A_SKILLS = {
    "s3_v2g_locus_collect": V2GLocusCollect,
    "s10_functional_evidence_search": FunctionalEvidenceSearch,
}

__all__ = ["V2GLocusCollect", "FunctionalEvidenceSearch", "ARCHETYPE_A_SKILLS"]
