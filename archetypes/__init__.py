"""Archetype registry - maps archetype_id to (config, evidence_card_class, gap_patterns, skills)."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Type

import yaml

from shared.evidence.base_card import BaseEvidenceCard
from shared.skills.skill_11_gap_analysis import GapPattern


@dataclass
class ArchetypeTemplate:
    archetype_id: str
    name: str
    config: dict[str, Any]
    evidence_card_class: Type[BaseEvidenceCard]
    gap_patterns: list[GapPattern]
    skills: dict[str, type] = field(default_factory=dict)


_ARCHETYPE_MODULES = {
    "archetype_a_v2g": "archetypes.archetype_a_v2g",
    "archetype_b_prs": "archetypes.archetype_b_prs",
    "archetype_c_sc_ai": "archetypes.archetype_c_sc_ai",
    "archetype_d_omics_score": "archetypes.archetype_d_omics_score",
    "archetype_e_cross_ethnic": "archetypes.archetype_e_cross_ethnic",
    "archetype_f_spatial_gwas": "archetypes.archetype_f_spatial_gwas",
}

_ARCHETYPE_SKILLS_ATTR = {
    "archetype_a_v2g": "ARCHETYPE_A_SKILLS",
    "archetype_b_prs": "ARCHETYPE_B_SKILLS",
    "archetype_c_sc_ai": "ARCHETYPE_C_SKILLS",
    "archetype_d_omics_score": "ARCHETYPE_D_SKILLS",
    "archetype_e_cross_ethnic": "ARCHETYPE_E_SKILLS",
    "archetype_f_spatial_gwas": "ARCHETYPE_F_SKILLS",
}

_ARCHETYPE_GAP_PATTERNS_ATTR = {
    "archetype_a_v2g": "ARCHETYPE_A_GAP_PATTERNS",
    "archetype_b_prs": "ARCHETYPE_B_GAP_PATTERNS",
    "archetype_c_sc_ai": "ARCHETYPE_C_GAP_PATTERNS",
    "archetype_d_omics_score": "ARCHETYPE_D_GAP_PATTERNS",
    "archetype_e_cross_ethnic": "ARCHETYPE_E_GAP_PATTERNS",
    "archetype_f_spatial_gwas": "ARCHETYPE_F_GAP_PATTERNS",
}


def _load_config(archetype_id: str) -> dict[str, Any]:
    cfg_path = Path(__file__).parent / archetype_id / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_archetype(archetype_id: str) -> ArchetypeTemplate:
    """Load an archetype template by id."""
    if archetype_id not in _ARCHETYPE_MODULES:
        raise ValueError(f"Unknown archetype: {archetype_id}. Available: {list(_ARCHETYPE_MODULES)}")
    mod_path = _ARCHETYPE_MODULES[archetype_id]
    mod = importlib.import_module(mod_path)
    cfg = _load_config(archetype_id)
    card_class_path = cfg.get("evidence_card_class")
    if not card_class_path:
        raise ValueError(f"Archetype {archetype_id} config missing evidence_card_class")
    parts = card_class_path.rsplit(".", 1)
    card_mod = importlib.import_module(parts[0])
    card_class: Type[BaseEvidenceCard] = getattr(card_mod, parts[1])
    gap_patterns: list[GapPattern] = getattr(
        importlib.import_module(f"{mod_path}.gap_patterns"),
        _ARCHETYPE_GAP_PATTERNS_ATTR[archetype_id],
    )
    skills: dict[str, type] = getattr(mod, _ARCHETYPE_SKILLS_ATTR[archetype_id], {})
    return ArchetypeTemplate(
        archetype_id=archetype_id,
        name=cfg.get("name", archetype_id),
        config=cfg,
        evidence_card_class=card_class,
        gap_patterns=gap_patterns,
        skills=skills,
    )


def list_archetypes() -> list[str]:
    return list(_ARCHETYPE_MODULES.keys())


__all__ = ["ArchetypeTemplate", "load_archetype", "list_archetypes"]
