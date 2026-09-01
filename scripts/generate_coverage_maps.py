"""B4: Generate coverage_map.json for all 7 projects from existing evidence cards.
Zero LLM cost — purely rules-based data processing.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from archetypes import load_archetype
from shared.evidence.coverage_matrix import CoverageMatrix


PROJECT_DIRS = [
    ("p01_gwas_perturb_seq", "archetype_a_v2g"),
    ("p02_gwas_spatial", "archetype_a_v2g"),
    ("p03_gwas_scatac", "archetype_a_v2g"),
    ("p04_prs_advance", "archetype_b_prs"),
    ("p05_sc_multiomics_ai", "archetype_c_sc_ai"),
    ("p06_digital_immune", "archetype_d_omics_score"),
    ("p07_aging_clock", "archetype_d_omics_score"),
    ("p09_spatial_gwas_network", "archetype_f_spatial_gwas"),
]

COVERAGE_AGGREGATE_FIELDS = {
    "archetype_a_v2g": ["has_fine_mapping", "has_colocalization", "has_replication", "data_available"],
    "archetype_b_prs": ["data_available"],
    "archetype_c_sc_ai": ["data_available"],
    "archetype_d_omics_score": ["data_available"],
    "archetype_f_spatial_gwas": ["code_available", "data_available"],
}


def generate_coverage_map(project_dir_name: str, archetype_id: str) -> dict:
    """Load evidence cards, populate coverage matrix, return the serialized map."""
    template = load_archetype(archetype_id)
    card_class = template.evidence_card_class
    coverage_axes = template.config.get("coverage_axes", [])
    matrix = CoverageMatrix(axes=coverage_axes)

    cards_path = (
        PROJECT_ROOT / "projects" / project_dir_name / "output" / "evidence_cards.jsonl"
    )

    if not cards_path.exists():
        alt_path = (
            PROJECT_ROOT / "data" / "l1_warm" / project_dir_name / "cards.jsonl"
        )
        if alt_path.exists():
            cards_path = alt_path
        else:
            print(f"  SKIP: no evidence_cards.jsonl found for {project_dir_name}")
            return {}

    total = 0
    with cards_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            try:
                if "paper_doi" in raw or "paper_title" in raw:
                    raw.setdefault("source_paper", {})
                    raw.setdefault("source_location", {})
                    for prefix, target in [("paper_", "source_paper"), ("loc_", "source_location")]:
                        obj = {}
                        for k in list(raw.keys()):
                            if k.startswith(prefix):
                                obj[k[len(prefix):]] = raw.pop(k)
                        if obj:
                            raw[target] = obj
                    for drop_key in ("tags_str", "_search_text"):
                        raw.pop(drop_key, None)
                card = card_class.model_validate(raw)
                matrix.add_card(card)
                total += 1
            except Exception:
                try:
                    from shared.evidence.base_card import V2GEvidenceCard
                    card = V2GEvidenceCard.model_validate(raw)
                    matrix.add_card(card)
                    total += 1
                except Exception:
                    pass

    cells = matrix.all_cells()
    agg_fields = COVERAGE_AGGREGATE_FIELDS.get(archetype_id, ["data_available"])
    cmap = []
    for key, cell in cells.items():
        entry = {ax: val for ax, val in zip(coverage_axes, key)}
        entry["card_count"] = cell.card_count
        for field in agg_fields:
            entry[field] = getattr(cell, field, False)
        if cell.archetype_specific:
            entry["archetype_specific"] = cell.archetype_specific
        cmap.append(entry)

    output_path = (
        PROJECT_ROOT / "projects" / project_dir_name / "output" / "coverage_map.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(cmap, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return {
        "cells": len(cells),
        "cards": total,
        "axes": coverage_axes,
        "path": str(output_path),
    }


def main():
    print("B4: Generating coverage maps for all 7 projects...")
    for proj_name, arch_id in PROJECT_DIRS:
        result = generate_coverage_map(proj_name, arch_id)
        if result:
            print(
                f"  {proj_name}: {result['cells']} cells from {result['cards']} cards "
                f"(axes: {', '.join(result['axes'])})"
            )
    print("Done.")


if __name__ == "__main__":
    main()
