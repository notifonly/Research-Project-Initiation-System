"""S11 GapAnalysis - identify evidence gaps via coverage matrix + gap pattern library.

Gap analysis across 4 archetypes (each with 10 domain-specific patterns):
  v2g:        P1-P10  (functional_modality, fine_mapping, coloc, ancestry, replication)
  prs:        B1-B10  (ancestry_discovery, external_validation, transportability,
                        method_comparison, threshold_sweep, rare_variants,
                        interaction_effects, calibration, clinical_cutoff, cross_trait)
  sc_fm:      C1-C10  (modality_omics, benchmark, held_out_celltype, weak_baseline,
                        weights_release, transfer_eval, single_tissue, scalability,
                        interpretability, multimodal_integration)
  omics_score:D1-D10  (omics_layers, external_validation, calibration,
                        transportability, age_range, single_ancestry, clinical_cutoff,
                        interpretability, clinical_score_comparison, longitudinal)

Archetype detection uses card.archetype string, NOT field values (converted cards
have all archetype-specific fields as None). When adding a new archetype, add:
  1. A _has_{archetype}_fields() method checking c.archetype
  2. An if-block with 10 pattern-specific gap checks
  3. Corresponding gap patterns in archetypes/{archetype}/gap_patterns.py
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.evidence.coverage_matrix import CoverageMatrix
from shared.evidence.base_card import (
    BaseEvidenceCard,
    EvidenceState,
    EVIDENCE_STATE_WEIGHTS,
    ARCHETYPE_V2G,
    ARCHETYPE_PRS,
    ARCHETYPE_SC_FM,
    ARCHETYPE_OMICS_SCORE,
    ARCHETYPE_CROSS_ETHNIC,
)
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s11_gap_analysis")


class GapPattern(BaseModel):
    pattern_id: str
    name: str
    description: str
    weight_evidence_asymmetry: float = 0.35
    weight_feasibility: float = 0.25
    weight_competition: float = 0.20
    weight_cross_archetype: float = 0.20


class IdentifiedGap(BaseModel):
    gap_id: str = ""
    pattern_id: str = ""
    axis: str = ""
    description: str = ""
    score: float = 0.0
    feasibility: float = 0.5
    competition: float = 0.5
    cross_archetype: float = 0.0
    supporting_cards: list[str] = Field(default_factory=list)
    all_supporting_card_ids: list[str] = Field(default_factory=list)
    contradicting_card_ids: list[str] = Field(default_factory=list)
    uncertain_card_ids: list[str] = Field(default_factory=list)
    coverage_denominator: int = 0
    coverage_numerator: int = 0
    gap_confidence: float = 0.0
    evidence_links: list[GapEvidenceLink] = Field(default_factory=list)


class GapEvidenceLink(BaseModel):
    """Structured evidence link between a gap and a specific card, with matched rules and weights."""
    card_id: str = ""
    matched_field: str = ""
    matched_rule: str = ""
    weight: float = 0.0
    rationale: str = ""


class GapAnalysisInput(SkillInput):
    cards: list[BaseEvidenceCard] = Field(default_factory=list)
    coverage_matrix: Optional[CoverageMatrix] = None
    gap_patterns: list[GapPattern] = Field(default_factory=list)


class GapAnalysisOutput(SkillOutput):
    gaps: list[IdentifiedGap] = Field(default_factory=list)
    gap_cells: list[str] = Field(default_factory=list)
    top_gaps: list[IdentifiedGap] = Field(default_factory=list)


GAP_PATTERNS_DEFAULT = [
    GapPattern(pattern_id="P1", name="functional_modality_missing", description="Locus has no functional modality evidence (eQTL/pQTL/etc.)"),
    GapPattern(pattern_id="P2", name="single_modality", description="Only one functional modality (e.g. eQTL only), no triangulation"),
    GapPattern(pattern_id="P3", name="cell_type_coverage_hole", description="Relevant cell type for trait has no evidence"),
    GapPattern(pattern_id="P4", name="cross_trait_borrowing", description="Functional evidence borrowed from another trait; not validated for target trait"),
    GapPattern(pattern_id="P5", name="fine_mapping_missing", description="Locus lacks fine-mapping; credible set unknown"),
    GapPattern(pattern_id="P6", name="coloc_unverified", description="Colocalization between GWAS and QTL not tested"),
    GapPattern(pattern_id="P7", name="ancestry_single", description="All evidence from single ancestry (EUR only)"),
    GapPattern(pattern_id="P8", name="no_replication", description="No replication cohort; single-cohort findings"),
    GapPattern(pattern_id="P9", name="public_data_underexploited", description="Public datasets available but unused"),
    GapPattern(pattern_id="P10", name="cross_archetype_bridge", description="Bridge to another archetype (e.g. PRS/foundation model) unexplored"),
]


class GapAnalysis(BaseSkill):
    """S11: Identify evidence gaps via coverage matrix + gap pattern library."""

    name = "gap_analysis"
    description = "Identify evidence gaps using coverage matrix and gap pattern library"
    uses_llm = False
    budget_phase = BudgetPhase.SYNTHESIS
    input_schema = GapAnalysisInput
    output_schema = GapAnalysisOutput

    def _derive_expected_axes(self, cards: list[BaseEvidenceCard]) -> list[dict[str, Any]]:
        """Build expected coverage cells from cross-product of observed axis values."""
        if not cards:
            return []
        axes_values: dict[str, set[Any]] = {}
        for c in cards:
            ax = c.coverage_axes()
            for k, v in ax.items():
                axes_values.setdefault(k, set()).add(v)
        if not axes_values:
            return []
        expected: list[dict[str, Any]] = [{}]
        for axis, values in axes_values.items():
            resolved = values or {"unknown"}
            expected = [dict(e, **{axis: v}) for e in expected for v in resolved]
        return expected

    def _has_v2g_fields(self, cards: list[BaseEvidenceCard]) -> bool:
        return any(getattr(c, "archetype", "") == ARCHETYPE_V2G for c in cards)

    def _has_prs_fields(self, cards: list[BaseEvidenceCard]) -> bool:
        return any(getattr(c, "archetype", "") == ARCHETYPE_PRS for c in cards)

    def _has_sc_fm_fields(self, cards: list[BaseEvidenceCard]) -> bool:
        return any(getattr(c, "archetype", "") == ARCHETYPE_SC_FM for c in cards)

    def _has_omics_score_fields(self, cards: list[BaseEvidenceCard]) -> bool:
        return any(getattr(c, "archetype", "") == ARCHETYPE_OMICS_SCORE for c in cards)

    def _has_cross_ethnic_fields(self, cards: list[BaseEvidenceCard]) -> bool:
        return any(getattr(c, "archetype", "") == ARCHETYPE_CROSS_ETHNIC for c in cards)

    @staticmethod
    def _classify_evidence_by_state(
        matching_cards: list[BaseEvidenceCard],
        field_name: str,
    ) -> dict[str, Any]:
        """Classify matching cards by EvidenceState, computing weighted gap strength.

        Returns dict with:
          weighted_numerator: sum of weights for matched cards
          effective_denominator: cards excluding NOT_APPLICABLE
          state_counts: counts per EvidenceState value
          contradicting: cards with CONFLICTING state (separate category)
        """
        total_weight = 0.0
        denominator = 0
        state_counts: dict[str, int] = {}
        contradicting_ids: list[str] = []

        for c in matching_cards:
            state = getattr(c, field_name, None)
            if state is None:
                state_counts["not_extracted"] = state_counts.get("not_extracted", 0) + 1
                continue
            state_key = state.value if isinstance(state, EvidenceState) else str(state)
            state_counts[state_key] = state_counts.get(state_key, 0) + 1

            if state == EvidenceState.NOT_APPLICABLE:
                continue
            denominator += 1
            weight = EVIDENCE_STATE_WEIGHTS.get(state, 0.0)
            total_weight += weight
            if state == EvidenceState.CONFLICTING:
                contradicting_ids.append(
                    c.card_id if hasattr(c, "card_id") else ""
                )

        return {
            "weighted_numerator": round(total_weight, 3),
            "effective_denominator": denominator,
            "state_counts": state_counts,
            "contradicting_ids": contradicting_ids,
        }

    def _build_gap_with_evidence(
        self,
        cards: list[BaseEvidenceCard],
        matching_cards: list[BaseEvidenceCard],
        gap_id: str,
        pattern_id: str,
        axis: str,
        description: str,
        score: float = 0.0,
        feasibility: float = 0.5,
        competition: float = 0.5,
        cross_archetype: float = 0.0,
        evidence_links: list[GapEvidenceLink] | None = None,
    ) -> IdentifiedGap:
        total = len(cards)
        matched = len(matching_cards)
        all_ids = [c.card_id for c in matching_cards if hasattr(c, "card_id")]
        id_set = set(all_ids)
        other_ids = [c.card_id for c in cards if hasattr(c, "card_id") and c.card_id not in id_set]
        coverage_ratio = matched / max(total, 1)
        gap_confidence = 0.3 + 0.7 * coverage_ratio if matched > 0 else 0.0
        if len(other_ids) < 5:
            gap_confidence = min(gap_confidence, 0.3)

        return IdentifiedGap(
            gap_id=gap_id,
            pattern_id=pattern_id,
            axis=axis,
            description=description,
            score=score,
            feasibility=feasibility,
            competition=competition,
            cross_archetype=cross_archetype,
            supporting_cards=all_ids[:10],
            all_supporting_card_ids=all_ids,
            contradicting_card_ids=other_ids[:10],
            coverage_denominator=total,
            coverage_numerator=matched,
            gap_confidence=round(gap_confidence, 3),
            evidence_links=evidence_links or [],
        )

    @staticmethod
    def _build_gap_evidence_links(
        matching_cards: list[BaseEvidenceCard],
        axis: str,
        match_rule: str = "field_missing",
    ) -> list[GapEvidenceLink]:
        links: list[GapEvidenceLink] = []
        for c in matching_cards:
            cid = getattr(c, "card_id", "")
            if not cid:
                continue
            field_value = getattr(c, axis, None)
            if field_value is None:
                rationale = f"Card {cid}: {axis} not populated (not extracted)"
                weight = 1.0
            elif isinstance(field_value, EvidenceState):
                if field_value == EvidenceState.REPORTED_NOT_DONE:
                    rationale = f"Card {cid}: {axis}={field_value.value} (paper explicitly states not done)"
                    weight = 1.0
                elif field_value == EvidenceState.NOT_REPORTED:
                    rationale = f"Card {cid}: {axis}={field_value.value} (paper does not mention)"
                    weight = 0.55
                else:
                    rationale = f"Card {cid}: {axis}={field_value.value}"
                    weight = 0.0
            else:
                rationale = f"Card {cid}: {axis} value is {field_value!r} ({match_rule})"
                weight = 0.5
            links.append(GapEvidenceLink(
                card_id=cid,
                matched_field=axis,
                matched_rule=match_rule,
                weight=weight,
                rationale=rationale,
            ))
        return links

    async def execute(self, inp: GapAnalysisInput, ctx: SkillContext) -> GapAnalysisOutput:
        patterns = inp.gap_patterns or GAP_PATTERNS_DEFAULT
        matrix = inp.coverage_matrix
        if matrix is None:
            matrix = CoverageMatrix()
            for c in inp.cards:
                matrix.add_card(c)

        gaps: list[IdentifiedGap] = []
        expected_axes = self._derive_expected_axes(inp.cards)
        gap_cells = [str(g) for g in matrix.gap_cells(expected_axes)]

        is_v2g = self._has_v2g_fields(inp.cards)

        # Pattern P1/P2: per-locus modality analysis (V2G-specific)
        if is_v2g:
            modality_by_locus: dict[str, set[str]] = {}
            for c in inp.cards:
                for g in (getattr(c, "locus_genes", None) or []):
                    modality_by_locus.setdefault(g, set())
                    mod = getattr(c, "functional_modality", None)
                    if mod:
                        modality_by_locus[g].add(mod)
            for locus, mods in modality_by_locus.items():
                if not mods:
                    gaps.append(IdentifiedGap(
                        gap_id=f"P1_{locus}", pattern_id="P1", axis="functional_modality",
                        description=f"Locus {locus}: no functional modality evidence",
                        score=0.9, feasibility=0.7, competition=0.4, cross_archetype=0.2,
                    ))
                elif len(mods) == 1:
                    gaps.append(IdentifiedGap(
                        gap_id=f"P2_{locus}", pattern_id="P2", axis="functional_modality",
                        description=f"Locus {locus}: single modality only ({list(mods)[0]}); no triangulation",
                        score=0.7, feasibility=0.6, competition=0.5, cross_archetype=0.3,
                    ))

            # Pattern P5/P6: fine-mapping & coloc
            no_fine = [c for c in inp.cards if not getattr(c, "fine_mapping_method", None)]
            no_coloc = [c for c in inp.cards if not getattr(c, "coloc_result", None)]
            if no_fine:
                gaps.append(IdentifiedGap(
                    gap_id="P5_aggregate", pattern_id="P5", axis="fine_mapping",
                    description=f"{len(no_fine)} cards lack fine-mapping; credible sets unknown",
                    score=0.8, feasibility=0.8, competition=0.3, cross_archetype=0.1,
                    supporting_cards=[c.card_id for c in no_fine[:10]],
                ))
            if no_coloc:
                gaps.append(IdentifiedGap(
                    gap_id="P6_aggregate", pattern_id="P6", axis="colocalization",
                    description=f"{len(no_coloc)} cards lack colocalization test (GWAS vs QTL)",
                    score=0.75, feasibility=0.85, competition=0.3, cross_archetype=0.1,
                    supporting_cards=[c.card_id for c in no_coloc[:10]],
                ))

            # Pattern P7: ancestry diversity
            ancestries = {getattr(c, "population_ancestry", None) for c in inp.cards if getattr(c, "population_ancestry", None)}
            if len(ancestries) <= 1:
                gaps.append(IdentifiedGap(
                    gap_id="P7_ancestry", pattern_id="P7", axis="population_ancestry",
                    description=f"Single ancestry only ({ancestries or 'unknown'}); no diversity",
                    score=0.7, feasibility=0.6, competition=0.4, cross_archetype=0.2,
                ))

            # Pattern P8: replication
            no_repl = [c for c in inp.cards if not getattr(c, "has_replication", None)]
            if no_repl:
                gaps.append(IdentifiedGap(
                    gap_id="P8_replication", pattern_id="P8", axis="replication",
                    description=f"{len(no_repl)} cards lack replication cohort",
                    score=0.65, feasibility=0.5, competition=0.5, cross_archetype=0.1,
                ))

        # Pattern B1-B10: PRS-specific gap analysis
        is_prs = self._has_prs_fields(inp.cards)
        if is_prs:
            # B1: ancestry_limited_discovery
            disc_ancestries = {getattr(c, "discovery_ancestry", None) for c in inp.cards if getattr(c, "discovery_ancestry", None)}
            if len(disc_ancestries) <= 1:
                gaps.append(IdentifiedGap(
                    gap_id="B1_ancestry_limited", pattern_id="B1", axis="discovery_ancestry",
                    description=f"PRS discovery in single ancestry ({disc_ancestries or 'unknown'}); no cross-ancestry discovery",
                    score=0.75, feasibility=0.55, competition=0.35, cross_archetype=0.25,
                ))

            # B2: no_external_validation
            no_ext_valid = [c for c in inp.cards if not getattr(c, "external_validation", None)]
            if no_ext_valid:
                gaps.append(IdentifiedGap(
                    gap_id="B2_no_external_validation", pattern_id="B2", axis="external_validation",
                    description=f"{len(no_ext_valid)} cards lack external validation cohort",
                    score=0.8, feasibility=0.5, competition=0.3, cross_archetype=0.2,
                    supporting_cards=[c.card_id for c in no_ext_valid[:10]],
                ))

            # B3: transportability_untested
            no_transport = [c for c in inp.cards if not getattr(c, "transportability_tested", None)]
            if no_transport:
                gaps.append(IdentifiedGap(
                    gap_id="B3_transportability_untested", pattern_id="B3", axis="transportability",
                    description=f"{len(no_transport)} cards have not tested PRS transportability across populations",
                    score=0.75, feasibility=0.45, competition=0.3, cross_archetype=0.25,
                    supporting_cards=[c.card_id for c in no_transport[:10]],
                ))

            # B4: method_comparison_missing
            prs_methods = {getattr(c, "prs_method", None) for c in inp.cards if getattr(c, "prs_method", None)}
            if len(prs_methods) <= 1:
                gaps.append(IdentifiedGap(
                    gap_id="B4_method_comparison", pattern_id="B4", axis="prs_method",
                    description=f"Single PRS method used ({prs_methods or 'none'}); no benchmark vs LDpred2/PRS-CS/lassosum",
                    score=0.7, feasibility=0.7, competition=0.35, cross_archetype=0.2,
                ))

            # B5: polygenicity_threshold_unexplored
            thresholds = {getattr(c, "p_value_threshold", None) for c in inp.cards if getattr(c, "p_value_threshold", None)}
            if len(thresholds) <= 1:
                gaps.append(IdentifiedGap(
                    gap_id="B5_threshold_unexplored", pattern_id="B5", axis="p_value_threshold",
                    description="Single p-value threshold used; no threshold sensitivity sweep (0.5, 0.05, 5e-8)",
                    score=0.55, feasibility=0.75, competition=0.3, cross_archetype=0.15,
                ))

            # B6: rare_variant_exclusion
            no_rare = [c for c in inp.cards if not getattr(c, "rare_variants_included", None)]
            if no_rare:
                gaps.append(IdentifiedGap(
                    gap_id="B6_rare_variant_exclusion", pattern_id="B6", axis="rare_variants",
                    description=f"{len(no_rare)} cards excluded rare variants; no rare-variant PRS comparison",
                    score=0.65, feasibility=0.5, competition=0.3, cross_archetype=0.2,
                    supporting_cards=[c.card_id for c in no_rare[:10]],
                ))

            # B7: interaction_effects_missing
            no_interact = [c for c in inp.cards if not getattr(c, "interaction_terms", None)]
            if no_interact:
                gaps.append(IdentifiedGap(
                    gap_id="B7_interaction_missing", pattern_id="B7", axis="interaction_terms",
                    description=f"{len(no_interact)} cards lack gene-environment or sex-interaction terms",
                    score=0.6, feasibility=0.55, competition=0.25, cross_archetype=0.2,
                    supporting_cards=[c.card_id for c in no_interact[:10]],
                ))

            # B8: calibration_untested
            no_calib = [c for c in inp.cards if not getattr(c, "calibration_method", None)]
            if no_calib:
                gaps.append(IdentifiedGap(
                    gap_id="B8_calibration_untested", pattern_id="B8", axis="calibration",
                    description=f"{len(no_calib)} cards lack PRS calibration assessment",
                    score=0.7, feasibility=0.65, competition=0.3, cross_archetype=0.15,
                    supporting_cards=[c.card_id for c in no_calib[:10]],
                ))

            # B9: clinical_cutoff_absent
            no_cutoff = [c for c in inp.cards if not getattr(c, "baseline_risk", None)]
            if no_cutoff:
                gaps.append(IdentifiedGap(
                    gap_id="B9_clinical_cutoff_absent", pattern_id="B9", axis="baseline_risk",
                    description=f"{len(no_cutoff)} cards lack clinical risk threshold/decision curve analysis",
                    score=0.65, feasibility=0.6, competition=0.3, cross_archetype=0.2,
                    supporting_cards=[c.card_id for c in no_cutoff[:10]],
                ))

            # B10: cross_trait_prs_unused
            gaps.append(IdentifiedGap(
                gap_id="B10_cross_trait", pattern_id="B10", axis="cross_trait",
                description="Cross-trait PRS (multi-trait LDpred2 / PRS-CSx) unexplored for boosting precision",
                score=0.55, feasibility=0.55, competition=0.2, cross_archetype=0.35,
            ))

        # Pattern C1-C10: scAI/foundation-model gap analysis
        is_sc_fm = self._has_sc_fm_fields(inp.cards)
        if is_sc_fm:
            total_cards = len(inp.cards)
            no_modality = [c for c in inp.cards if not getattr(c, "modality_omics", None) and not getattr(c, "modalities_integrated", None)]
            if no_modality:
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_modality,
                    gap_id="C1_single_omics", pattern_id="C1", axis="modality_omics",
                    description=f"{len(no_modality)}/{total_cards} cards lack omics modality specification; no multi-omics evidence",
                    score=0.8, feasibility=0.7, competition=0.3, cross_archetype=0.2,
                ))
            no_bench = [c for c in inp.cards if not getattr(c, "eval_metric_name", None)]
            if no_bench:
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_bench,
                    gap_id="C2_no_benchmark", pattern_id="C2", axis="eval_metric",
                    description=f"{len(no_bench)}/{total_cards} cards lack standardized evaluation metric",
                    score=0.75, feasibility=0.8, competition=0.3, cross_archetype=0.15,
                ))
            no_heldout = [c for c in inp.cards if getattr(c, "held_out_cell_types", None) != EvidenceState.CONFIRMED]
            if no_heldout:
                ev = self._classify_evidence_by_state(no_heldout, "held_out_cell_types")
                evidence_weight = ev["weighted_numerator"]
                explicit_no = ev["state_counts"].get("reported_not_done", 0)
                not_reported = ev["state_counts"].get("not_reported", 0)
                conflicting = len(ev["contradicting_ids"])
                desc = (
                    f"{len(no_heldout)}/{total_cards} cards lack held-out cell type evaluation"
                    f" (explicit_no={explicit_no}, unreported={not_reported}"
                )
                if conflicting:
                    desc += f", conflicting={conflicting}"
                desc += ")"
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_heldout,
                    gap_id="C3_no_heldout", pattern_id="C3", axis="held_out_cell_types",
                    description=desc,
                    score=round(0.35 + 0.45 * evidence_weight / max(ev["effective_denominator"], 1), 2),
                    feasibility=0.65, competition=0.25, cross_archetype=0.2,
                    evidence_links=self._build_gap_evidence_links(no_heldout, "held_out_cell_types", "not_confirmed"),
                ))
            no_baseline = [c for c in inp.cards if not getattr(c, "baseline_method", None)]
            if no_baseline:
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_baseline,
                    gap_id="C4_weak_baseline", pattern_id="C4", axis="baseline_method",
                    description=f"{len(no_baseline)}/{total_cards} cards lack baseline method comparison (e.g. PCA/logistic)",
                    score=0.7, feasibility=0.75, competition=0.3, cross_archetype=0.15,
                ))
            no_weights = [c for c in inp.cards if getattr(c, "weights_available", None) != EvidenceState.CONFIRMED]
            if no_weights:
                ev = self._classify_evidence_by_state(no_weights, "weights_available")
                evidence_weight = ev["weighted_numerator"]
                explicit_no = ev["state_counts"].get("reported_not_done", 0)
                conflicting = len(ev["contradicting_ids"])
                desc = f"{len(no_weights)}/{total_cards} cards: pretrained weights not released"
                if explicit_no or conflicting:
                    desc += f" (explicit_no={explicit_no}"
                    if conflicting:
                        desc += f", conflicting={conflicting}"
                    desc += ")"
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_weights,
                    gap_id="C5_weights_unavailable", pattern_id="C5", axis="weights_available",
                    description=desc,
                    score=round(0.25 + 0.40 * evidence_weight / max(ev["effective_denominator"], 1), 2),
                    feasibility=0.4, competition=0.25, cross_archetype=0.25,
                    evidence_links=self._build_gap_evidence_links(no_weights, "weights_available", "not_confirmed"),
                ))
            no_transfer = [c for c in inp.cards if getattr(c, "transfer_evaluated", None) != EvidenceState.CONFIRMED]
            if no_transfer:
                ev = self._classify_evidence_by_state(no_transfer, "transfer_evaluated")
                evidence_weight = ev["weighted_numerator"]
                explicit_no = ev["state_counts"].get("reported_not_done", 0)
                desc = f"{len(no_transfer)}/{total_cards} cards lack transfer learning evaluation"
                if explicit_no:
                    desc += f" (explicit_no={explicit_no})"
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_transfer,
                    gap_id="C6_no_transfer", pattern_id="C6", axis="transfer_evaluated",
                    description=desc,
                    score=round(0.30 + 0.45 * evidence_weight / max(ev["effective_denominator"], 1), 2),
                    feasibility=0.55, competition=0.25, cross_archetype=0.25,
                    evidence_links=self._build_gap_evidence_links(no_transfer, "transfer_evaluated", "not_confirmed"),
                ))
            tissues = {getattr(c, "tissue", None) for c in inp.cards if getattr(c, "tissue", None)}
            if len(tissues) <= 1:
                single_tissue_cards = [c for c in inp.cards if getattr(c, "tissue", None)]
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=single_tissue_cards,
                    gap_id="C7_single_tissue", pattern_id="C7", axis="tissue",
                    description=f"Single tissue ({tissues or 'unknown'}); multi-tissue generalization untested",
                    score=0.7, feasibility=0.6, competition=0.35, cross_archetype=0.15,
                ))
            no_scale = [c for c in inp.cards if not getattr(c, "n_cells_pretrain", None)]
            if no_scale:
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_scale,
                    gap_id="C8_scalability", pattern_id="C8", axis="n_cells_pretrain",
                    description=f"{len(no_scale)}/{total_cards} cards lack scalability metrics (n_cells_pretrain)",
                    score=0.6, feasibility=0.7, competition=0.3, cross_archetype=0.2,
                ))
            no_interp = [c for c in inp.cards if getattr(c, "interpretability_assessed", None) != EvidenceState.CONFIRMED]
            if no_interp:
                ev = self._classify_evidence_by_state(no_interp, "interpretability_assessed")
                evidence_weight = ev["weighted_numerator"]
                explicit_no = ev["state_counts"].get("reported_not_done", 0)
                desc = f"{len(no_interp)}/{total_cards} cards lack interpretability analysis (attention/gene module)"
                if explicit_no:
                    desc += f" (explicit_no={explicit_no})"
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_interp,
                    gap_id="C9_interpretability", pattern_id="C9", axis="interpretability_assessed",
                    description=desc,
                    score=round(0.25 + 0.45 * evidence_weight / max(ev["effective_denominator"], 1), 2),
                    feasibility=0.5, competition=0.3, cross_archetype=0.2,
                    evidence_links=self._build_gap_evidence_links(no_interp, "interpretability_assessed", "not_confirmed"),
                ))
            multi_mod = [c for c in inp.cards if getattr(c, "modalities_integrated", None) and len(getattr(c, "modalities_integrated", None) or []) > 1]
            if not multi_mod:
                all_with_mod = [c for c in inp.cards if getattr(c, "modalities_integrated", None)]
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=all_with_mod,
                    gap_id="C10_multi_modal", pattern_id="C10", axis="modalities_integrated",
                    description="No cards demonstrate multi-modal integration (RNA+ATAC+protein)",
                    score=0.75, feasibility=0.5, competition=0.25, cross_archetype=0.3,
                ))
            archs = {getattr(c, "model_architecture", None) for c in inp.cards if getattr(c, "model_architecture", None)}
            non_transformer = {"Mamba", "SSM", "Hyena", "VQ-VAE", "GNN", "CNN", "VAE"}
            n_total = sum(1 for c in inp.cards if getattr(c, "model_architecture", None))
            n_transformer = sum(1 for c in inp.cards if getattr(c, "model_architecture", None) in {"transformer", "attention"})
            n_non_transformer = sum(1 for c in inp.cards if getattr(c, "model_architecture", None) in non_transformer)
            n_known = n_transformer + n_non_transformer
            if n_total > 0:
                transformer_ratio = n_transformer / n_total if n_total > 0 else 0
                if transformer_ratio > 0.70 or (n_known > 0 and n_transformer / n_known > 0.90):
                    all_trans = sorted(archs & {"transformer", "attention"})
                    non_trans = sorted(archs & non_transformer)
                    arch_str = ", ".join(all_trans) if all_trans else "transformer/attention"
                    alt_str = ", ".join(non_trans) if non_trans else "none"
                    tf_cards = [c for c in inp.cards if getattr(c, "model_architecture", None) in {"transformer", "attention"}]
                    gaps.append(self._build_gap_with_evidence(
                        cards=[c for c in inp.cards if getattr(c, "model_architecture", None)],
                        matching_cards=tf_cards,
                        gap_id="C11_architecture_homogeneity", pattern_id="C11", axis="model_architecture",
                        description=f"Architecture diversity deficit: {n_transformer}/{n_total} ({transformer_ratio:.0%}) cards use transformer-based ({arch_str}); only {n_non_transformer} cards ({alt_str}) use non-Transformer alternatives",
                        score=0.75 if transformer_ratio > 0.90 else 0.65,
                        feasibility=0.55, competition=0.2, cross_archetype=0.3,
                    ))
            gwas_keywords = ["GWAS", "colocalization", "coloc", "TWAS", "eQTL", "variant-to-gene",
                             "fine-mapping", "QTL", "genome-wide", "Mendelian randomization"]
            gwas_fields = ["task", "task_category", "eval_metric_name", "downstream_task"]
            has_gwas = []
            no_gwas = []
            for c in inp.cards:
                found = False
                for f in gwas_fields:
                    val = getattr(c, f, None) or ""
                    if any(kw.lower() in str(val).lower() for kw in gwas_keywords):
                        found = True
                        break
                if found:
                    has_gwas.append(c)
                else:
                    no_gwas.append(c)
            total_non_empty = len([c for c in inp.cards if any(getattr(c, f, None) for f in gwas_fields)])
            if not has_gwas and total_non_empty > 0:
                gaps.append(self._build_gap_with_evidence(
                    cards=inp.cards, matching_cards=no_gwas[:15],
                    gap_id="C12_no_gwas", pattern_id="C12", axis="gwas_integration",
                    description=f"{len(inp.cards)} cards: no GWAS-informed downstream evaluation (variant-to-gene, colocalization, TWAS); single-cell models disconnected from population genetics",
                    score=0.75, feasibility=0.55, competition=0.2, cross_archetype=0.35,
                ))

        # Pattern D1-D10: omics-score gap analysis
        is_omics_score = self._has_omics_score_fields(inp.cards)
        if is_omics_score:
            multi_layer = [c for c in inp.cards if getattr(c, "omics_layers", None) and len(getattr(c, "omics_layers", None) or []) > 1]
            if not multi_layer:
                gaps.append(IdentifiedGap(
                    gap_id="D1_single_layer", pattern_id="D1", axis="omics_layers",
                    description="No cards use multi-omics integration (single layer only)",
                    score=0.8, feasibility=0.7, competition=0.3, cross_archetype=0.2,
                ))
            no_ext = [c for c in inp.cards if not getattr(c, "external_validation", None)]
            if no_ext:
                gaps.append(IdentifiedGap(
                    gap_id="D2_no_external", pattern_id="D2", axis="external_validation",
                    description=f"{len(no_ext)} cards lack external validation cohort",
                    score=0.85, feasibility=0.5, competition=0.25, cross_archetype=0.15,
                ))
            no_calib = [c for c in inp.cards if not getattr(c, "calibration_method", None)]
            if no_calib:
                gaps.append(IdentifiedGap(
                    gap_id="D3_no_calibration", pattern_id="D3", axis="calibration",
                    description=f"{len(no_calib)} cards lack calibration assessment (discrimination only)",
                    score=0.75, feasibility=0.65, competition=0.3, cross_archetype=0.15,
                ))
            no_transport = [c for c in inp.cards if not getattr(c, "transportability_tested", None)]
            if no_transport:
                gaps.append(IdentifiedGap(
                    gap_id="D4_no_transport", pattern_id="D4", axis="transportability",
                    description=f"{len(no_transport)} cards lack transportability testing across cohorts",
                    score=0.8, feasibility=0.45, competition=0.25, cross_archetype=0.2,
                ))
            has_age = [c for c in inp.cards if getattr(c, "age_range_min", None) is not None or getattr(c, "age_range_max", None) is not None]
            if not has_age:
                gaps.append(IdentifiedGap(
                    gap_id="D5_narrow_age", pattern_id="D5", axis="age_range",
                    description="No cards specify age range; generalization across ages untested",
                    score=0.6, feasibility=0.7, competition=0.35, cross_archetype=0.15,
                ))
            ancestries = {getattr(c, "population_ancestry", None) for c in inp.cards if getattr(c, "population_ancestry", None)}
            if len(ancestries) <= 1:
                gaps.append(IdentifiedGap(
                    gap_id="D6_single_ancestry", pattern_id="D6", axis="population_ancestry",
                    description=f"Single ancestry ({ancestries or 'unknown'}); cross-ancestry unvalidated",
                    score=0.75, feasibility=0.55, competition=0.3, cross_archetype=0.2,
                ))
            no_cutoff = [c for c in inp.cards if not getattr(c, "clinical_cutoff", None)]
            if no_cutoff:
                gaps.append(IdentifiedGap(
                    gap_id="D7_no_cutoff", pattern_id="D7", axis="clinical_cutoff",
                    description=f"{len(no_cutoff)} cards lack clinical risk cutoff / decision curve",
                    score=0.7, feasibility=0.6, competition=0.3, cross_archetype=0.15,
                ))
            no_interp = [c for c in inp.cards if not getattr(c, "interpretability_method", None)]
            if no_interp:
                gaps.append(IdentifiedGap(
                    gap_id="D8_no_interp", pattern_id="D8", axis="interpretability",
                    description=f"{len(no_interp)} cards lack feature-level interpretability analysis",
                    score=0.65, feasibility=0.5, competition=0.3, cross_archetype=0.2,
                ))
            no_clin = [c for c in inp.cards if not getattr(c, "comparison_to_clinical_score", None)]
            if no_clin:
                gaps.append(IdentifiedGap(
                    gap_id="D9_no_clinical", pattern_id="D9", axis="comparison_to_clinical_score",
                    description=f"{len(no_clin)} cards lack comparison to existing clinical scores",
                    score=0.7, feasibility=0.55, competition=0.3, cross_archetype=0.2,
                ))
            no_long = [c for c in inp.cards if not getattr(c, "longitudinal_eval", None)]
            if no_long:
                gaps.append(IdentifiedGap(
                    gap_id="D10_no_longitudinal", pattern_id="D10", axis="longitudinal_eval",
                    description=f"{len(no_long)} cards lack longitudinal evaluation; cross-sectional only",
                    score=0.7, feasibility=0.5, competition=0.25, cross_archetype=0.25,
                ))

        is_cross_ethnic = self._has_cross_ethnic_fields(inp.cards)
        if is_cross_ethnic:
            cross = [c for c in inp.cards if getattr(c, "archetype", "") == ARCHETYPE_CROSS_ETHNIC]
            if not cross:
                cross = inp.cards
            # E1: single population
            ancestries = {getattr(c, "ancestry_comparison", None) for c in cross if getattr(c, "ancestry_comparison", None)}
            if len(ancestries) <= 1:
                gaps.append(IdentifiedGap(
                    gap_id="E1_single_population", pattern_id="E1", axis="ancestry_comparison",
                    description=f"{len(cross)} cards: cross-ethnic comparison missing; single population only ({ancestries or 'none'})",
                    score=0.85, feasibility=0.5, competition=0.25, cross_archetype=0.3,
                ))
            # E2: no cross-ethnic replication
            no_repl = [c for c in cross if not getattr(c, "cross_ethnic_replication", None)]
            if no_repl:
                gaps.append(IdentifiedGap(
                    gap_id="E2_no_replication", pattern_id="E2", axis="cross_ethnic_replication",
                    description=f"{len(no_repl)}/{len(cross)} cards lack cross-ethnic replication validation",
                    score=0.8, feasibility=0.45, competition=0.2, cross_archetype=0.25,
                ))
            # E3: biomarker portability untested
            biomarker_cards = [c for c in cross if getattr(c, "omics_layers", None) and any(lm in ("proteomics", "metabolomics") for lm in (getattr(c, "omics_layers", None) or []))]
            if biomarker_cards:
                no_portability = [c for c in biomarker_cards if not getattr(c, "portability_score", None)]
                if no_portability:
                    gaps.append(IdentifiedGap(
                        gap_id="E3_biomarker_portability", pattern_id="E3", axis="portability",
                        description=f"{len(no_portability)}/{len(biomarker_cards)} biomarker cards lack quantitative portability assessment across populations",
                        score=0.8, feasibility=0.5, competition=0.2, cross_archetype=0.25,
                    ))
            # E4: PRS transportability untested across ethnicities
            prs_cards = [c for c in cross if getattr(c, "method_family", None) and "prs" in str(getattr(c, "method_family", "")).lower()]
            if prs_cards:
                no_transport = [c for c in prs_cards if not getattr(c, "cross_ethnic_replication", None)]
                if no_transport:
                    gaps.append(IdentifiedGap(
                        gap_id="E4_prs_transportability", pattern_id="E4", axis="prs_transportability",
                        description=f"{len(no_transport)}/{len(prs_cards)} PRS cards lack cross-ethnic transportability validation",
                        score=0.85, feasibility=0.4, competition=0.2, cross_archetype=0.3,
                    ))
            # E5: MR not cross-validated
            mr_cards = [c for c in cross if getattr(c, "method", None) and "mendelian randomization" in str(getattr(c, "method", "")).lower()]
            if mr_cards:
                no_cross_mr = [c for c in mr_cards if not getattr(c, "cross_ethnic_replication", None)]
                if no_cross_mr:
                    gaps.append(IdentifiedGap(
                        gap_id="E5_mr_not_cross_validated", pattern_id="E5", axis="causal_inference",
                        description=f"{len(no_cross_mr)}/{len(mr_cards)} MR estimates not cross-validated across populations",
                        score=0.75, feasibility=0.45, competition=0.25, cross_archetype=0.25,
                    ))
            # E6: single omics layer
            multi_layer = [c for c in cross if getattr(c, "omics_layers", None) and len(getattr(c, "omics_layers", None) or []) > 1]
            if not multi_layer:
                gaps.append(IdentifiedGap(
                    gap_id="E6_single_omics", pattern_id="E6", axis="omics_layers",
                    description=f"{len(cross)} cards: single omics layer only; multi-omics integration missing",
                    score=0.7, feasibility=0.6, competition=0.2, cross_archetype=0.25,
                ))
            # E7: biobank underutilized
            biobanks = {getattr(c, "biobank_source", None) for c in cross if getattr(c, "biobank_source", None)}
            major_banks = {"UKB", "FinnGen", "Biobank Japan", "China Kadoorie", "All of Us"}
            used_banks = biobanks & major_banks
            if len(used_banks) <= 1:
                gaps.append(IdentifiedGap(
                    gap_id="E7_biobank_underutilized", pattern_id="E7", axis="biobank_source",
                    description=f"Only {len(used_banks)}/{len(major_banks)} major biobanks utilized: {used_banks or 'none'}",
                    score=0.6, feasibility=0.8, competition=0.3, cross_archetype=0.25,
                ))
            # E8: harmonization missing
            no_harmonized = [c for c in cross if not getattr(c, "harmonization_method", None)]
            if no_harmonized:
                gaps.append(IdentifiedGap(
                    gap_id="E8_harmonization_missing", pattern_id="E8", axis="harmonization_method",
                    description=f"{len(no_harmonized)}/{len(cross)} cards lack data harmonization method across populations",
                    score=0.75, feasibility=0.5, competition=0.2, cross_archetype=0.2,
                ))
            # E9: population-specific confounded
            pop_specific = [c for c in cross if getattr(c, "population_specific_finding", None)]
            if pop_specific:
                gaps.append(IdentifiedGap(
                    gap_id="E9_population_confounded", pattern_id="E9", axis="population_specific_finding",
                    description=f"{len(pop_specific)}/{len(cross)} cards have population-specific findings; confounding (env/lifestyle/ascertainment) not addressed",
                    score=0.65, feasibility=0.45, competition=0.25, cross_archetype=0.25,
                ))
            # E10: cross-archetype unexplored
            gaps.append(IdentifiedGap(
                gap_id="E10_cross_archetype", pattern_id="E10", axis="cross_archetype",
                description="Bridge to V2G (archetype A) or PRS (archetype B) methodology for cross-ethnic omics unexplored",
                score=0.55, feasibility=0.5, competition=0.15, cross_archetype=1.0,
            ))

        # Pattern P3: coverage holes (generic - works for all archetypes)
        if gap_cells:
            sample_cards = [c.card_id for c in (inp.cards or [])[:10] if hasattr(c, 'card_id')]
            gaps.append(IdentifiedGap(
                gap_id="P3_celltype", pattern_id="P3", axis="coverage",
                description=f"{len(gap_cells)} empty coverage cells from expected axis combinations",
                score=0.85, feasibility=0.6, competition=0.4, cross_archetype=0.3,
                supporting_cards=sample_cards,
            ))

        # Pattern P9: public data underexploited
        no_data = [c for c in inp.cards if not getattr(c, "raw_data_accession", None) and not getattr(c, "summary_stats_available", None)]
        if no_data:
            gaps.append(self._build_gap_with_evidence(
                cards=inp.cards, matching_cards=no_data,
                gap_id="P9_public_data", pattern_id="P9", axis="data",
                description=f"{len(no_data)}/{len(inp.cards)} cards do not reference public data accessions",
                score=0.6, feasibility=0.9, competition=0.3, cross_archetype=0.2,
            ))

        # Pattern P10: cross-archetype bridge
        p10_sample = [c.card_id for c in (inp.cards or [])[:10] if hasattr(c, 'card_id')]
        gaps.append(IdentifiedGap(
            gap_id="P10_bridge", pattern_id="P10", axis="cross_archetype",
            description="Cross-archetype bridge (PRS scoring / foundation model integration) unexplored",
            score=0.5, feasibility=0.5, competition=0.2, cross_archetype=1.0,
            supporting_cards=p10_sample,
        ))

        # Score each gap with 4-dim weighted
        pat_weights = {p.pattern_id: p for p in patterns}
        for g in gaps:
            p = pat_weights.get(g.pattern_id)
            if p:
                g.score = (
                    g.score * p.weight_evidence_asymmetry
                    + g.feasibility * p.weight_feasibility
                    + (1 - g.competition) * p.weight_competition
                    + g.cross_archetype * p.weight_cross_archetype
                )

        gaps.sort(key=lambda x: x.score, reverse=True)
        top = gaps[:5]
        self._metrics.update({
            "total_gaps": len(gaps),
            "gap_cells": len(gap_cells),
            "top_gap_score": top[0].score if top else 0.0,
        })
        return GapAnalysisOutput(
            skill_name=self.name,
            gaps=gaps,
            gap_cells=gap_cells,
            top_gaps=top,
        )
