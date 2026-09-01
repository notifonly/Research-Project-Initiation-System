"""S7 EvidenceCardExtract - extract structured evidence cards from screened papers (per-finding granularity)."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.evidence.base_card import BaseEvidenceCard, SourceLocation, SourcePaper
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s7_evidence_extract")


def _try_parse_float(raw: str) -> Optional[float]:
    """Extract float from LLM strings like '~5%', '0.65-0.70', '<0.70', 'HR=1.2'."""
    if not raw:
        return None
    match = re.search(r'-?[\d]+\.?[\d]*(?:[eE][+-]?\d+)?', raw.replace(",", ""))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _try_parse_int(raw: str) -> Optional[int]:
    """Extract int from LLM strings like '~50000', 'n=1000'."""
    if not raw:
        return None
    match = re.search(r'-?[\d]+', raw.replace(",", ""))
    if match:
        try:
            return int(match.group())
        except ValueError:
            return None
    return None


class ExtractTarget(BaseModel):
    paper_id: str = ""
    title: str = ""
    doi: Optional[str] = None
    pmid: Optional[str] = None
    abstract: str = ""
    year: Optional[int] = None
    authors: list[str] = Field(default_factory=list)
    venue: str = ""
    url: str = ""
    full_text: Optional[str] = None


class EvidenceCardExtractInput(SkillInput):
    targets: list[ExtractTarget] = Field(default_factory=list)
    archetype: str = ""
    max_findings_per_paper: int = 5
    max_targets: int = 5
    extraction_text_truncate: int = 6000
    normalized_traits: list[dict[str, str]] = Field(default_factory=list)
    normalized_genes: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceCardExtractOutput(SkillOutput):
    cards: list[BaseEvidenceCard] = Field(default_factory=list)
    paper_count: int = 0
    findings_count: int = 0


class EvidenceCardExtract(BaseSkill):
    """S7: Extract structured evidence cards (per-finding) from screened papers via LLM."""

    name = "evidence_card_extract"
    description = "Extract per-finding evidence cards from papers; one paper may yield multiple cards."
    uses_llm = True
    budget_phase = BudgetPhase.EXTRACTION
    input_schema = EvidenceCardExtractInput
    output_schema = EvidenceCardExtractOutput

    def _resolve_card_class(self, ctx: SkillContext) -> type[BaseEvidenceCard]:
        """Resolve the evidence card class from archetype config, falling back to V2GEvidenceCard."""
        arch_cfg = ctx.archetype_config or {}
        if "_evidence_card_class" in arch_cfg:
            return arch_cfg["_evidence_card_class"]
        from shared.evidence.base_card import V2GEvidenceCard
        return V2GEvidenceCard

    async def execute(self, inp: EvidenceCardExtractInput, ctx: SkillContext) -> EvidenceCardExtractOutput:
        card_class = self._resolve_card_class(ctx)
        cards: list[BaseEvidenceCard] = []
        traits = [t.get("efo_label", t.get("raw", "")) for t in inp.normalized_traits]
        genes = [g.get("symbol", "") for g in inp.normalized_genes]
        topic_id = ctx.scratch.get("_candidate_topic_id", "")

        max_papers = inp.max_targets
        targets = inp.targets[:max_papers]
        if len(inp.targets) > max_papers:
            logger.info(f"Capping targets from {len(inp.targets)} to {max_papers}")

        tasks = [self._extract_from_paper(t, inp, ctx, traits, genes, card_class, topic_id) for t in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, paper_cards in enumerate(results):
            if isinstance(paper_cards, BaseException):
                logger.warning(f"Extract failed for '{targets[i].title}': {paper_cards}")
                continue
            cards.extend(paper_cards)
            for c in paper_cards:
                if ctx.card_store:
                    try:
                        ctx.card_store.add(c)
                    except Exception as e:
                        logger.warning(f"card store add failed: {e}")

        self._metrics.update({
            "papers": len(targets),
            "cards": len(cards),
            "avg_findings": round(len(cards) / max(1, len(targets)), 2),
        })
        return EvidenceCardExtractOutput(
            skill_name=self.name,
            cards=cards,
            paper_count=len(targets),
            findings_count=len(cards),
        )

    def _build_archetype_fields(self, archetype: str) -> dict[str, Any]:
        """Map archetype to default fields/prompts for LLM extraction."""
        field_registry = {
            "v2g": {
                "field_list": (
                    "trait_label, lead_variant_rsid, chrom, pos, locus_genes (list), "
                    "causal_gene_claimed, cell_type, tissue, functional_modality "
                    "(eQTL|pQTL|sQTL|chromatin|splicing|regulatory|other), "
                    "sample_size, population_ancestry, p_value, effect_size_beta, "
                    "fine_mapping_method, coloc_result, has_replication (bool), "
                    "summary_stats_available (bool), code_available (bool), raw_data_accession (str)"
                ),
                "coverage_critical": (
                    "CRITICAL: Always provide trait_label, functional_modality, cell_type, "
                    "population_ancestry, and lead_variant_rsid (or genomic_position). "
                    "Infer from context even if not explicitly stated."
                ),
            },
            "prs": {
                "field_list": (
                    "trait_label, target_population, discovery_ancestry, validation_ancestry, "
                    "sample_size_discovery, sample_size_validation, n_snps_in_prs, "
                    "prs_method, prs_method_family, clumping_threshold, p_value_threshold, "
                    "effect_size_metric, effect_size_value, auc, or_per_sd, c_index, "
                    "baseline_risk, calibration_method, calibration_result, "
                    "transportability_tested (bool), transportability_result, "
                    "validation_cohort, external_validation (bool), interaction_terms (bool), "
                    "rare_variants_included (bool), "
                    "summary_stats_available (bool), code_available (bool), weights_available (bool), "
                    "raw_data_accession (str)"
                ),
                "coverage_critical": (
                    "CRITICAL: Always provide trait_label, prs_method (or prs_method_family), "
                    "validation_ancestry (or discovery_ancestry), validation_cohort, "
                    "and transportability_tested. Infer from context even if not explicitly stated."
                ),
            },
            "sc_fm": {
                "field_list": (
                    "task, task_category, modality_omics, modalities_integrated (list), "
                    "tissue, cell_type, model_architecture, model_family, "
                    "pretext_task, pretext_objective, downstream_task, "
                    "n_cells_pretrain, n_cells_finetune, n_features_input, n_parameters, "
                    "embedding_dim, eval_metric_name, eval_metric_value, "
                    "baseline_method, baseline_metric_value, improvement_over_baseline, "
                    "held_out_cell_types (str: confirmed/reported_not_done/not_reported/not_applicable/conflicting), held_out_tissues (same), "
                    "batch_correction_evaluated (same), transfer_evaluated (same), "
                    "interpretability_assessed (same), "
                    "code_available (same), weights_available (same), dataset_available (same), "
                    "raw_data_accession (str), model_hub"
                ),
                "coverage_critical": (
                    "CRITICAL: Always provide task (or task_category), modality_omics, "
                    "tissue, model_architecture (or model_family), and evaluation mode "
                    "(held_out_cell_types or held_out_tissues). Infer from context even if not explicitly stated."
                ),
            },
            "omics_score": {
                "field_list": (
                    "score_name, score_type, score_family, "
                    "omics_layers (list), primary_omics_layer, "
                    "trait_targeted, feature_count, feature_selection_method, "
                    "model_type, model_algorithm, "
                    "sample_size_discovery, sample_size_validation, "
                    "age_range_min, age_range_max, population_ancestry, "
                    "validation_cohort, external_validation (bool), "
                    "eval_metric_name, eval_metric_value, auc, c_index, "
                    "correlation_target, mae, "
                    "calibration_method, calibration_result, "
                    "transportability_tested (bool), transportability_result, "
                    "clinical_cutoff, comparison_to_clinical_score, "
                    "longitudinal_eval (bool), interpretability_method, "
                    "sex_stratified (bool), cell_type_specific (bool), "
                    "code_available (bool), weights_available (bool), data_available (bool), "
                    "raw_data_accession (str)"
                ),
                "coverage_critical": (
                    "CRITICAL: Always provide score_type (or score_family), omics_layers (or primary_omics_layer), "
                    "trait_targeted, validation_cohort, and transportability_tested. "
                    "Infer from context even if not explicitly stated."
                ),
            },
        }
        return field_registry.get(archetype, field_registry["v2g"])

    async def _extract_from_paper(
        self,
        target: ExtractTarget,
        inp: EvidenceCardExtractInput,
        ctx: SkillContext,
        traits: list[str],
        genes: list[str],
        card_class: type[BaseEvidenceCard],
        topic_id: str = "",
    ) -> list[BaseEvidenceCard]:
        text = target.full_text or target.abstract or target.title
        if not text or len(text.strip()) < 30:
            return []

        arch_fields = self._build_archetype_fields(inp.archetype)
        truncate_len = inp.extraction_text_truncate
        coverage_note = arch_fields.get("coverage_critical", "")

        prompt = f"""You are a meticulous bioinformatics evidence extractor. Extract up to {inp.max_findings_per_paper} distinct findings/conclusions from this paper as structured evidence.

Paper: {target.title}
DOI: {target.doi or 'N/A'} | PMID: {target.pmid or 'N/A'} | Year: {target.year}
Archetype: {inp.archetype}
Known traits: {traits}
Known genes: {genes}

Text:
{text[:truncate_len]}

{coverage_note}

Return JSON: a list of finding objects, each with fields:
- key_finding (str)
- method_brief (str)
- limitation_explicit (str), limitation_implicit (str)
- {arch_fields['field_list']}
Only include fields you can find evidence for; leave others null/empty."""

        result = await self._llm(prompt, ctx, structured=list)
        if isinstance(result, dict):
            for v in result.values():
                if isinstance(v, list):
                    result = v
                    break
        if not isinstance(result, list):
            return []

        cards: list[BaseEvidenceCard] = []
        for finding in result:
            if not isinstance(finding, dict) or not finding.get("key_finding"):
                continue
            card = self._build_card(target, finding, card_class, inp.archetype, topic_id)
            cards.append(card)
        return cards

    @staticmethod
    def _coerce_str(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return ", ".join(str(x) for x in v if x)
        if isinstance(v, str):
            return v
        return str(v)

    @staticmethod
    def _coerce_opt_str(v: Any) -> Optional[str]:
        result = EvidenceCardExtract._coerce_str(v)
        return result if result else None

    @staticmethod
    def _coerce_int(v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _coerce_float(v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    def _build_card(self, target: ExtractTarget, finding: dict[str, Any],
                    card_class: type[BaseEvidenceCard], archetype: str,
                    topic_id: str = "") -> BaseEvidenceCard:
        paper = SourcePaper(
            doi=target.doi,
            pmid=target.pmid,
            title=target.title,
            authors=target.authors,
            year=target.year,
            venue=target.venue,
            url=target.url,
        )
        location = SourceLocation(
            section=finding.get("section", "abstract"),
            excerpt=(finding.get("key_finding", "") or "")[:500],
        )

        fields: dict[str, Any] = {
            "card_id": f"card_{uuid.uuid4().hex[:12]}",
            "source_type": "paper",
            "source_paper": paper,
            "source_location": location,
            "reliability_flag": "medium" if (target.doi or target.pmid) else "unverified",
            "key_finding": self._coerce_str(finding.get("key_finding")),
            "method_brief": self._coerce_str(finding.get("method_brief")),
            "limitation_explicit": self._coerce_opt_str(finding.get("limitation_explicit")),
            "limitation_implicit": self._coerce_opt_str(finding.get("limitation_implicit")),
            "archetype": archetype,
            "tags": finding.get("tags", []) if isinstance(finding.get("tags"), list) else [],
        }
        if topic_id:
            fields["tags"].append(f"candidate:{topic_id}")

        model_fields = set(card_class.model_fields.keys())
        for k, v in finding.items():
            if k in model_fields and k not in fields:
                fields[k] = self._sanitize_field_value(k, v, card_class)

        return card_class(**fields)

    @staticmethod
    def _sanitize_field_value(name: str, value: Any, card_class: type[BaseEvidenceCard]) -> Any:
        """Coerce LLM string output to expected pydantic field type (float/int/bool/list)."""
        field_info = card_class.model_fields.get(name)
        if field_info is None:
            return value
        annotation = str(field_info.annotation)
        if value is None:
            if "list" in annotation:
                return []
            return None
        if isinstance(value, bool):
            if "str" in annotation:
                return "True" if value else "False"
            return value
        if "float" in annotation and isinstance(value, str):
            return _try_parse_float(value)
        if "int" in annotation and isinstance(value, str):
            return _try_parse_int(value)
        if "bool" in annotation and isinstance(value, str):
            return value.lower() in ("yes", "true", "1", "y")
        return value
