"""Archetype C (SC + AI) gap pattern library - 11 patterns for foundation model research."""

from __future__ import annotations

from shared.skills.skill_11_gap_analysis import GapPattern


ARCHETYPE_C_GAP_PATTERNS: list[GapPattern] = [
    GapPattern(
        pattern_id="C1",
        name="single_omics_only",
        description="Foundation model trained on single omics modality (e.g. RNA only); no multi-omics integration",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C2",
        name="no_benchmark",
        description="No standardized benchmark; ad-hoc evaluation only",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C3",
        name="no_celltype_heldout",
        description="No held-out cell type evaluation; in-distribution only",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C4",
        name="weak_baseline",
        description="Weak baseline comparison (e.g. PCA/logistic); no comparison to SOTA foundation models",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C5",
        name="weights_unavailable",
        description="Pretrained weights not released; reproducibility blocked",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.40,
        weight_competition=0.15,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C6",
        name="no_transfer_eval",
        description="Transfer learning to unseen tissue/disease not evaluated",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.30,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C7",
        name="single_tissue",
        description="Foundation model pretrained on single tissue only; generalization untested",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.25,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C8",
        name="scalability_untested",
        description="Scalability to >10M cells not tested; compute efficiency unreported",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.30,
        weight_competition=0.25,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C9",
        name="interpretability_missing",
        description="No interpretability analysis (attention/gene module/latent dissection)",
        weight_evidence_asymmetry=0.25,
        weight_feasibility=0.35,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C10",
        name="no_multimodal_integration",
        description="No multi-modal integration demonstrated (RNA+ATAC+protein); single modality only",
        weight_evidence_asymmetry=0.30,
        weight_feasibility=0.35,
        weight_competition=0.15,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C11",
        name="architecture_homogeneity",
        description="All studied models use Transformer-based architecture; non-Transformer alternatives (Mamba/SSM/Hyena/VQ-VAE) unexplored",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
    GapPattern(
        pattern_id="C12",
        name="no_gwas_integration",
        description="Single-cell foundation model not evaluated on GWAS-informed downstream tasks (variant-to-gene mapping, colocalization, TWAS); population genetics relevance unproven",
        weight_evidence_asymmetry=0.35,
        weight_feasibility=0.25,
        weight_competition=0.20,
        weight_cross_archetype=0.20,
    ),
]


__all__ = ["ARCHETYPE_C_GAP_PATTERNS"]
