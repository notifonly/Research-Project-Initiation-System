"""Archetype C (SC + AI) evidence card - single-cell multi-omics foundation model evidence."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from shared.evidence.base_card import BaseEvidenceCard, EvidenceState, ARCHETYPE_SC_FM


class SCFMEvidenceCard(BaseEvidenceCard):
    """Archetype C: Single-cell foundation model evidence card.

    Captures foundation model / representation learning findings for single-cell
    multi-omics data (one paper -> multiple cards).
    Coverage axes for archetype C:
      task x modality x tissue x model_architecture x evaluation_setting.
    """

    archetype: str = ARCHETYPE_SC_FM

    task: Optional[str] = None
    task_category: Optional[str] = None
    modality_omics: Optional[str] = None
    modalities_integrated: list[str] = Field(default_factory=list)
    tissue: Optional[str] = None
    cell_type: Optional[str] = None
    model_architecture: Optional[str] = None
    model_family: Optional[str] = None
    pretext_task: Optional[str] = None
    pretext_objective: Optional[str] = None
    downstream_task: Optional[str] = None
    n_cells_pretrain: Optional[int] = None
    n_cells_finetune: Optional[int] = None
    n_features_input: Optional[int] = None
    n_parameters: Optional[int] = None
    embedding_dim: Optional[int] = None
    eval_metric_name: Optional[str] = None
    eval_metric_value: Optional[float] = None
    baseline_method: Optional[str] = None
    baseline_metric_value: Optional[float] = None
    improvement_over_baseline: Optional[float] = None
    held_out_cell_types: Optional[EvidenceState] = None
    held_out_tissues: Optional[EvidenceState] = None
    batch_correction_evaluated: Optional[EvidenceState] = None
    transfer_evaluated: Optional[EvidenceState] = None
    interpretability_assessed: Optional[EvidenceState] = None
    code_available: Optional[EvidenceState] = None
    weights_available: Optional[EvidenceState] = None
    dataset_available: Optional[EvidenceState] = None
    raw_data_accession: Optional[str] = None
    model_hub: Optional[str] = None

    # Deep-read enrichment fields (populated when s6c_deep_read notes are available)
    evidence_status: Optional[str] = None      # directly_stated | inferred | author_claim | unresolved
    evidence_strength: Optional[str] = None     # fully_supported | partially_supported | insufficient | conflicting
    deep_read_source: Optional[str] = None      # paper_id of the deep-read note that informed this card

    # GWAS integration fields
    gwas_trait: Optional[str] = None
    gwas_locus: Optional[str] = None
    coloc_method: Optional[str] = None
    coloc_score: Optional[float] = None
    gwas_dataset: Optional[str] = None

    def coverage_axes(self) -> dict:
        return {
            "task": self.task or self.task_category or "unknown",
            "modality": self.modality_omics or ("multi" if len(self.modalities_integrated) > 1 else "single"),
            "tissue": self.tissue or "unknown",
            "model_architecture": self.model_architecture or self.model_family or "unknown",
            "evaluation_setting": (
                "held_out_celltype" if self.held_out_cell_types == EvidenceState.CONFIRMED else
                "held_out_tissue" if self.held_out_tissues == EvidenceState.CONFIRMED else
                "standard"
            ),
        }


__all__ = ["SCFMEvidenceCard"]
