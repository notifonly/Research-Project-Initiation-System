from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from shared.evidence.base_card import BaseEvidenceCard


@dataclass
class CoverageCell:
    card_count: int = 0
    has_fine_mapping: bool = False
    has_colocalization: bool = False
    has_replication: bool = False
    data_available: bool = False
    card_ids: list[str] = field(default_factory=list)
    archetype_specific: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_card(cls, card: BaseEvidenceCard) -> "CoverageCell":
        cell = cls()
        cell.card_count = 1
        cell.card_ids.append(card.card_id)
        if getattr(card, "fine_mapping_method", None):
            cell.has_fine_mapping = True
        if getattr(card, "coloc_result", None):
            cell.has_colocalization = True
        if getattr(card, "has_replication", None):
            cell.has_replication = True
        if getattr(card, "raw_data_accession", None) or getattr(card, "summary_stats_available", None):
            cell.data_available = True
        for attr in ("archetype",):
            val = getattr(card, attr, None)
            if val:
                cell.archetype_specific[attr] = val
        return cell


class CoverageMatrix:
    """Coverage matrix with configurable axes per archetype."""

    DEFAULT_AXES = ("trait", "locus", "functional_modality", "cell_type", "population_ancestry")

    def __init__(self, axes: Optional[list[str]] = None) -> None:
        self.AXES = tuple(axes) if axes else self.DEFAULT_AXES
        self._cells: dict[tuple, CoverageCell] = {}

    def _key(self, axes: dict[str, Any]) -> tuple:
        return tuple(axes.get(a, "unknown") for a in self.AXES)

    def add_card(self, card: BaseEvidenceCard) -> None:
        if not hasattr(card, "coverage_axes"):
            return
        axes = card.coverage_axes()
        key = self._key(axes)
        existing = self._cells.get(key)
        if existing is not None:
            existing.card_count += 1
            existing.card_ids.append(card.card_id)
            if getattr(card, "fine_mapping_method", None):
                existing.has_fine_mapping = True
            if getattr(card, "coloc_result", None):
                existing.has_colocalization = True
            if getattr(card, "has_replication", None):
                existing.has_replication = True
            if getattr(card, "raw_data_accession", None) or getattr(card, "summary_stats_available", None):
                existing.data_available = True
        else:
            self._cells[key] = CoverageCell.from_card(card)

    def get_cell(self, axes: dict[str, Any]) -> CoverageCell | None:
        return self._cells.get(self._key(axes))

    def all_cells(self) -> dict[tuple, CoverageCell]:
        return dict(self._cells)

    def occupied_keys(self) -> set[tuple]:
        return set(self._cells.keys())

    def jaccard(self, other: "CoverageMatrix") -> float:
        a = self.occupied_keys()
        b = other.occupied_keys()
        if not a and not b:
            return 0.0
        union = a | b
        if not union:
            return 0.0
        return len(a & b) / len(union)

    def gap_cells(self, expected_axes: list[dict[str, Any]]) -> list[tuple]:
        expected_keys = {self._key(a) for a in expected_axes}
        return list(expected_keys - self.occupied_keys())

    def summary(self) -> dict[str, Any]:
        cells = list(self._cells.values())
        s = {
            "total_cells": len(cells),
            "total_cards": sum(c.card_count for c in cells),
            "cells_with_data": sum(1 for c in cells if c.data_available),
            "axis_values": {a: sorted({k[i] for k in self._cells}) for i, a in enumerate(self.AXES)},
        }
        # V2G-specific stats (only populated when cards have these fields)
        if any(c.has_fine_mapping for c in cells):
            s["cells_with_fine_mapping"] = sum(1 for c in cells if c.has_fine_mapping)
        if any(c.has_colocalization for c in cells):
            s["cells_with_colocalization"] = sum(1 for c in cells if c.has_colocalization)
        if any(c.has_replication for c in cells):
            s["cells_with_replication"] = sum(1 for c in cells if c.has_replication)
        return s
