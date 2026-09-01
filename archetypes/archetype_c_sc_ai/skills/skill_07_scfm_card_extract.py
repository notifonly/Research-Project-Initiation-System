"""S7 SCFMCardExtract (Archetype C-specific) - extract structured single-cell
foundation model evidence cards from screened papers with domain-specific prompts."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.evidence.base_card import BaseEvidenceCard, EvidenceState, EVIDENCE_STATE_WEIGHTS, SourceLocation, SourcePaper
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s7_scfm_extract")

SCFM_IRRELEVANT_KEYWORDS = [
    "content validity", "face validity", "CVI", "nursing",
    "psychometric", "questionnaire", "scale validation",
    "Delphi", "focus group", "qualitative interview",
]

SCFM_DOMAIN_PROMPT = """You are a bioinformatics evidence extractor specializing in single-cell
multi-omics foundation models. Extract up to {max_findings} distinct findings from this paper.

For each finding, identify the SPECIFIC model (scVI, scGPT, Geneformer, scFoundation, UCE, MultiVI,
or other named model) and its evaluation details.

=== FIELD DESCRIPTIONS ===

task: What the model does. Choose from:
  cell_type_annotation, gene_expression_prediction, batch_correction, data_integration,
  perturbation_prediction, grn_inference, embedding_evaluation, multimodal_integration,
  cross_species_transfer, dimensionality_reduction

task_category: Broader category:
  supervised_prediction, unsupervised_representation, batch_integration,
  multi_modal_fusion, transfer_learning

modality_omics: Primary data modality. Choose from:
  scRNA-seq, scATAC-seq, CITE-seq, multiome_RNA_ATAC, spatial_transcriptomics,
  sc_proteomics, sc_perturb-seq

modalities_integrated: List all modalities this model handles
  (e.g., ["scRNA-seq", "scATAC-seq"])

tissue: Tissue(s) data came from (e.g., PBMC, brain_cortex, bone_marrow, lung, pancreas)
cell_type: Specific cell type(s) if mentioned (e.g., CD4+_T_cells, microglia)

model_architecture: Architecture type. Choose from:
  VAE, transformer, GNN, MLP, attention, CNN, U-Net, diffusion, Mamba, SSM, Hyena, VQ-VAE

model_family: Model family name. Choose from:
  scVI_family, scGPT, Geneformer, scFoundation, UCE, MultiVI, scBERT,
  scGEN, scArches, SIMVI, scTab, scimilarity, TOSICA, RegFormer,
  GeneMamba, MambaCell, scHyena, scLong, CLM-X, cellVQ, other

pretext_task: Pretraining objective (e.g., masked_gene_prediction, cell_expression_reconstruction)
pretext_objective: Loss function or learning objective used
downstream_task: Specific downstream evaluation task

n_cells_pretrain: Number of cells used for pretraining (integer)
n_cells_finetune: Number of cells used for fine-tuning (integer)
n_parameters: Number of model parameters (integer, e.g. 100000000 for 100M)
embedding_dim: Embedding dimension size (integer)

eval_metric_name: Evaluation metric (e.g., macro_F1, accuracy, ARI, NMI, AUROC, Pearson_r)
eval_metric_value: Numeric value of evaluation metric
baseline_method: Baseline method compared against (e.g., PCA, scVI_v1, logistic_regression)
baseline_metric_value: Baseline method's metric value
improvement_over_baseline: Relative improvement (e.g., 0.15 for 15%)

held_out_cell_types (str): "confirmed" if model was tested on unseen cell types, "reported_not_done" if paper says NOT tested, "not_applicable" if model doesn't support held-out eval, "conflicting" if different sections contradict, "" or omit if not mentioned (treated as "not_extracted")
held_out_tissues (str): same as above
batch_correction_evaluated (str): "confirmed" / "reported_not_done" / "not_applicable" / "conflicting" / omit
transfer_evaluated (str): "confirmed" / "reported_not_done" / "not_applicable" / "conflicting" / omit
interpretability_assessed (str): "confirmed" / "reported_not_done" / "not_applicable" / "conflicting" / omit

code_available (str): "confirmed" / "reported_not_done" / "not_applicable" / "conflicting" / omit
weights_available (str): "confirmed" / "reported_not_done" / "not_applicable" / "conflicting" / omit
dataset_available (str): "confirmed" / "reported_not_done" / "not_applicable" / "conflicting" / omit
raw_data_accession: GEO/SRA/ArrayExpress accession if mentioned
model_hub: HuggingFace model ID or GitHub repo URL if mentioned

=== IMPORTANT ===
- Every finding MUST have a task or task_category AND a model_family or model_architecture.
- For numeric fields (n_cells_*, n_parameters, embedding_dim, *metric_value), extract exact
  numbers when stated. Leave null when not reported.
- For boolean fields, strictly return true or false based on explicit paper statements.
- If a field is not mentioned, leave it null/empty — do NOT guess.
- If the paper does NOT describe a single-cell foundation model, return an empty list []."""


def _try_parse_float(raw: str) -> Optional[float]:
    if not raw:
        return None
    match = re.search(r'-?[\d]+\.?[\d]*(?:[eE][+-]?\d+)?', str(raw).replace(",", ""))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _try_parse_int(raw: str) -> Optional[int]:
    if not raw:
        return None
    match = re.search(r'-?[\d]+', str(raw).replace(",", ""))
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


class SCFMExtractInput(SkillInput):
    targets: list[ExtractTarget] = Field(default_factory=list)
    archetype: str = ""
    max_findings_per_paper: int = 5
    max_targets: int = 20
    extraction_text_truncate: int = 8000
    normalized_traits: list[dict[str, str]] = Field(default_factory=list)
    normalized_genes: list[dict[str, Any]] = Field(default_factory=list)
    deep_read_notes: list[dict[str, Any]] = Field(default_factory=list)


class SCFMExtractOutput(SkillOutput):
    cards: list[BaseEvidenceCard] = Field(default_factory=list)
    paper_count: int = 0
    findings_count: int = 0
    irrelevant_count: int = 0


class SCFMCardExtract(BaseSkill):
    """S7 (Archetype C): Extract structured sc_fm evidence cards from screened papers.

    Overrides shared EvidenceCardExtract with a domain-specific prompt tuned for
    single-cell foundation model papers. Includes a pre-filter to skip papers
    clearly unrelated to sc multi-omics AI (e.g., nursing CVI studies).
    """

    name = "s7_evidence_card_extract"
    description = "Extract per-finding sc_fm evidence cards with domain-specific prompts"
    uses_llm = True
    budget_phase = BudgetPhase.EXTRACTION
    input_schema = SCFMExtractInput
    output_schema = SCFMExtractOutput

    def _resolve_card_class(self, ctx: SkillContext) -> type[BaseEvidenceCard]:
        arch_cfg = ctx.archetype_config or {}
        if "_evidence_card_class" in arch_cfg:
            return arch_cfg["_evidence_card_class"]
        from shared.evidence.base_card import BaseEvidenceCard
        return BaseEvidenceCard

    @staticmethod
    def _is_irrelevant(title: str, abstract: str) -> bool:
        combined = (title + " " + abstract).lower()
        for kw in SCFM_IRRELEVANT_KEYWORDS:
            if kw.lower() in combined:
                return True
        return False

    async def execute(self, inp: SCFMExtractInput, ctx: SkillContext) -> SCFMExtractOutput:
        card_class = self._resolve_card_class(ctx)
        cards: list[BaseEvidenceCard] = []
        irrelevant = 0
        topic_id = ctx.scratch.get("_candidate_topic_id", "")

        # Index deep_read_notes by paper_id for fast lookup
        notes_by_paper = self._index_deep_read_notes(inp.deep_read_notes)

        max_papers = inp.max_targets
        targets = inp.targets[:max_papers]
        if len(inp.targets) > max_papers:
            logger.info(f"Capping targets from {len(inp.targets)} to {max_papers}")

        deep_read_count = 0
        tasks = []
        for t in targets:
            if self._is_irrelevant(t.title, t.abstract):
                logger.info(f"Skipping irrelevant paper: {t.title[:80]}...")
                irrelevant += 1
                continue
            note = notes_by_paper.get(t.paper_id) or notes_by_paper.get(t.pmid or "")
            if note:
                deep_read_count += 1
                tasks.append(self._extract_from_deep_read(t, note, card_class, topic_id))
            else:
                tasks.append(self._extract_from_paper(t, inp, ctx, card_class, topic_id))

        self._metrics["deep_read_enriched"] = deep_read_count
        paper_count = len(tasks)
        logger.info(
            f"S7 routing: {deep_read_count}/{paper_count} papers via deep_read, "
            f"{paper_count - deep_read_count} via paper extraction "
            f"(notes_indexed={len(notes_by_paper)}, irrelevant_skipped={irrelevant})"
        )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, paper_cards in enumerate(results):
            if isinstance(paper_cards, BaseException):
                logger.warning(f"Extract failed: {paper_cards}")
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
            "irrelevant_skipped": irrelevant,
            "avg_findings": round(len(cards) / max(1, len(targets) - irrelevant), 2),
        })
        return SCFMExtractOutput(
            skill_name=self.name,
            cards=cards,
            paper_count=len(targets),
            findings_count=len(cards),
            irrelevant_count=irrelevant,
        )

    @staticmethod
    def _index_deep_read_notes(notes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Index deep_read_notes by paper_id for fast lookup."""
        index: dict[str, dict[str, Any]] = {}
        for note in notes:
            if isinstance(note, dict):
                pid = note.get("paper_id", "")
                if pid:
                    index[pid] = note
        return index

    # SC_FM enum value sets for heuristics-based field extraction from deep-read facts
    _TASK_VALUES = {
        "cell_type_annotation", "gene_expression_prediction", "batch_correction",
        "data_integration", "perturbation_prediction", "grn_inference",
        "embedding_evaluation", "multimodal_integration", "cross_species_transfer",
        "dimensionality_reduction",
    }
    _TASK_SYNONYMS = {
        "cell_type_annotation": ["cell type annotation", "cell-type annotation", "cell type classification",
                                 "cell type identification", "cell annotation", "annotat"],
        "gene_expression_prediction": ["gene expression prediction", "expression prediction",
                                        "predict gene expression", "impute gene expression"],
        "batch_correction": ["batch correction", "batch effect", "batch integration"],
        "data_integration": ["data integration", "integrat", "multi-dataset", "cross-dataset"],
        "perturbation_prediction": ["perturbation prediction", "perturbation response",
                                     "predict perturbation", "perturb-seq"],
        "grn_inference": ["grn inference", "gene regulatory network", "grn"],
        "embedding_evaluation": ["embedding evaluation", "representation evaluation",
                                  "benchmark embedding"],
        "multimodal_integration": ["multimodal integration", "multi-omics integration",
                                    "multi-modal", "cross-modality"],
        "cross_species_transfer": ["cross-species", "cross species", "species transfer"],
        "dimensionality_reduction": ["dimensionality reduction", "dimension reduction"],
    }
    _TASK_CATEGORY_VALUES = {
        "supervised_prediction", "unsupervised_representation", "batch_integration",
        "multi_modal_fusion", "transfer_learning",
    }
    _MODALITY_VALUES = {
        "scRNA-seq", "scATAC-seq", "CITE-seq", "multiome_RNA_ATAC",
        "spatial_transcriptomics", "sc_proteomics", "sc_perturb-seq",
    }
    _MODALITY_SYNONYMS = {
        "scRNA-seq": ["scrna-seq", "scrna seq", "single-cell rna", "single cell rna",
                      "rna-seq", "transcriptom"],
        "scATAC-seq": ["scatac-seq", "scatac seq", "single-cell atac", "single cell atac",
                       "atac-seq", "atac seq"],
        "CITE-seq": ["cite-seq", "cite seq", "citeseq"],
        "spatial_transcriptomics": ["spatial transcriptom", "spatial gene", "visium", "merfish", "spatial omics"],
        "sc_proteomics": ["proteomics", "protein", "mass cytometry", "cytof"],
        "sc_perturb-seq": ["perturb-seq", "perturb seq", "crispr"],
        "multiome_RNA_ATAC": ["multiome", "rna+atac", "rna and atac", "multi-omics", "snrna-seq+snatac-seq"],
    }
    _ARCHITECTURE_VALUES = {
        "VAE", "transformer", "GNN", "MLP", "attention", "CNN", "U-Net",
        "diffusion", "Mamba", "SSM", "Hyena", "VQ-VAE",
    }
    _ARCHITECTURE_SYNONYMS = {
        "VAE": ["vae", "variational autoencoder", "variational auto-encoder"],
        "transformer": ["transformer", "self-attention", "self attention"],
        "GNN": ["gnn", "graph neural network", "graph convolution"],
        "MLP": ["mlp", "multilayer perceptron", "multi-layer perceptron", "fully connected"],
        "attention": ["attention mechanism", "attention-based"],
        "CNN": ["cnn", "convolutional neural network", "1d cnn", "convolution neural"],
        "U-Net": ["u-net", "unet", "u net"],
        "diffusion": ["diffusion model", "denoising diffusion", "score-based"],
        "Mamba": ["mamba", "state space model", "selective state space", "ssm"],
        "Hyena": ["hyena"],
        "VQ-VAE": ["vq-vae", "vqvae", "vector quantized"],
        "SSM": ["ssm", "state space", "structured state"],
    }
    _MODEL_FAMILY_VALUES = {
        "scVI_family", "scGPT", "Geneformer", "scFoundation", "UCE", "MultiVI",
        "scBERT", "scGEN", "scArches", "SIMVI", "scTab", "scimilarity",
        "TOSICA", "RegFormer", "GeneMamba", "MambaCell", "scHyena", "scLong",
        "CLM-X", "cellVQ",
    }
    _TISSUE_VALUES = {
        "PBMC", "brain_cortex", "bone_marrow", "lung", "pancreas", "liver",
        "heart", "kidney", "skin", "spleen", "colon", "breast", "prostate",
        "ovary", "testis", "retina", "placenta", "thymus", "lymph_node",
        "adipose", "muscle", "blood", "brain", "intestine", "stomach",
    }
    _TISSUE_SYNONYMS = {
        "PBMC": ["pbmc", "peripheral blood mononuclear", "pbmcs"],
        "brain_cortex": ["brain cortex", "cortex", "cortical"],
        "bone_marrow": ["bone marrow", "haematopoietic", "hematopoietic", "hspc"],
        "lung": ["lung", "pulmonary"],
        "pancreas": ["pancreas", "pancreatic"],
        "liver": ["liver", "hepatic", "hepatocyte"],
        "heart": ["heart", "cardiac", "cardiomyocyte"],
        "kidney": ["kidney", "renal"],
        "skin": ["skin", "dermal", "epidermal"],
        "blood": ["blood", "whole blood"],
        "colon": ["colon", "colorectal", "intestinal"],
        "brain": ["brain", "neural", "cerebral"],
        "breast": ["breast", "mammary"],
        "lymph_node": ["lymph node", "lymphoid"],
        "spleen": ["spleen"],
    }
    _CELL_TYPE_VALUES = {
        "CD4+_T_cells", "CD8+_T_cells", "B_cells", "NK_cells", "monocytes",
        "macrophages", "microglia", "neutrophils", "dendritic_cells",
        "fibroblasts", "endothelial_cells", "epithelial_cells",
        "hepatocytes", "neurons", "astrocytes", "oligodendrocytes",
        "cardiomyocytes", "keratinocytes", "melanocytes", "stem_cells",
    }
    _CELL_TYPE_SYNONYMS = {
        "CD4+_T_cells": ["cd4+ t cell", "cd4 t cell", "cd4+t cell", "cd4t cell", "helper t cell"],
        "CD8+_T_cells": ["cd8+ t cell", "cd8 t cell", "cd8+t cell", "cd8t cell", "cytotoxic t cell"],
        "B_cells": ["b cell", "b-cell", "b lymphocyte"],
        "NK_cells": ["nk cell", "natural killer", "nk-cell"],
        "monocytes": ["monocyte"],
        "macrophages": ["macrophage"],
        "microglia": ["microglia", "microglial"],
        "neutrophils": ["neutrophil"],
        "dendritic_cells": ["dendritic cell", "dc cell", "dendrit"],
        "fibroblasts": ["fibroblast"],
        "endothelial_cells": ["endothelial cell", "endothelium"],
        "epithelial_cells": ["epithelial cell", "epithelium"],
        "hepatocytes": ["hepatocyte", "liver cell"],
        "neurons": ["neuron", "neuronal"],
        "astrocytes": ["astrocyte"],
        "oligodendrocytes": ["oligodendrocyte"],
        "cardiomyocytes": ["cardiomyocyte", "cardiac muscle cell"],
        "stem_cells": ["stem cell", "progenitor"],
    }

    @classmethod
    def _match_enum(cls, text_lower: str, enum_set: set[str],
                    synonyms: dict[str, list[str]] | None = None) -> str:
        for val in enum_set:
            # Direct normalized match
            key = val.lower().replace("_", " ").replace("-", "")
            if key in text_lower:
                return val
            # Direct substring (case-insensitive)
            if val.lower() in text_lower:
                return val
        # Try synonym matching
        if synonyms:
            for val, syns in synonyms.items():
                if val not in enum_set:
                    continue
                for s in syns:
                    if s in text_lower:
                        return val
        return ""

    @classmethod
    def _extract_fields_from_facts(cls, facts_text: str) -> dict[str, Any]:
        text_lower = facts_text.lower()
        return {
            "task": cls._match_enum(text_lower, cls._TASK_VALUES, cls._TASK_SYNONYMS),
            "task_category": cls._match_enum(text_lower, cls._TASK_CATEGORY_VALUES),
            "modality_omics": cls._match_enum(text_lower, cls._MODALITY_VALUES, cls._MODALITY_SYNONYMS),
            "model_architecture": cls._match_enum(text_lower, cls._ARCHITECTURE_VALUES, cls._ARCHITECTURE_SYNONYMS),
            "model_family": cls._match_enum(text_lower, cls._MODEL_FAMILY_VALUES),
            "tissue": cls._match_enum(text_lower, cls._TISSUE_VALUES, cls._TISSUE_SYNONYMS),
            "cell_type": cls._match_enum(text_lower, cls._CELL_TYPE_VALUES, cls._CELL_TYPE_SYNONYMS),
        }

    async def _llm_extract_missing_fields(
        self, title: str, text: str, missing_keys: list[str]
    ) -> dict[str, Any]:
        """Lightweight LLM extraction for specific coverage-critical fields that heuristics missed."""
        from shared.core.llm_client import llm_complete, _parse_json

        prompt = f"""Extract ONLY the following fields from this single-cell paper.
Return a JSON object with exactly the requested fields (empty string if unknown).

Title: {title}

Text:
{text}

Fields to extract: {', '.join(missing_keys)}

Valid values:
- task: cell_type_annotation, gene_expression_prediction, batch_correction, data_integration, perturbation_prediction, grn_inference, embedding_evaluation, multimodal_integration, cross_species_transfer, dimensionality_reduction
- task_category: supervised_prediction, unsupervised_representation, batch_integration, multi_modal_fusion, transfer_learning
- model_architecture: VAE, transformer, GNN, MLP, attention, CNN, U-Net, diffusion, Mamba, SSM, Hyena, VQ-VAE
- model_family: scVI_family, scGPT, Geneformer, scFoundation, UCE, MultiVI, scBERT, scGEN, scArches, SIMVI, scTab, scimilarity, TOSICA, RegFormer, GeneMamba, MambaCell, scHyena, scLong, CLM-X, cellVQ, other
- modality_omics: scRNA-seq, scATAC-seq, CITE-seq, multiome_RNA_ATAC, spatial_transcriptomics, sc_proteomics, sc_perturb-seq

Return ONLY the JSON object, no prose."""  # noqa: E501
        try:
            raw = await llm_complete(
                prompt,
                system="Extract structured fields from bioinformatics papers. Output valid JSON only.",
                budget=None,
                phase=self.budget_phase,
            )
            result = _parse_json(raw)
            if isinstance(result, dict):
                return {k: str(result.get(k, "")) for k in missing_keys}
        except Exception as e:
            logger.warning(f"LLM supplement failed for missing fields {missing_keys}: {e}")
        return {}

    async def _extract_from_deep_read(
        self,
        target: ExtractTarget,
        note: dict[str, Any],
        card_class: type[BaseEvidenceCard],
        topic_id: str = "",
    ) -> list[BaseEvidenceCard]:
        """Build evidence cards from a deep-read note's structured facts, claims, and judgments.
        
        Uses heuristics to extract coverage-critical enum fields (task, modality, etc.)
        from fact statements. Falls back to full LLM extraction if the paper text is long.
        """
        cards: list[BaseEvidenceCard] = []
        paper_id = target.paper_id or ""

        source_paper = SourcePaper(
            title=target.title,
            doi=target.doi,
            pmid=target.pmid,
            year=target.year,
            venue=target.venue,
            authors=target.authors or [],
            url=target.url,
        )

        facts = note.get("facts", [])
        judgments = note.get("judgments", [])
        judg_by_claim = {j.get("claim_id", ""): j for j in judgments if isinstance(j, dict)}

        # Concatenate all fact statements for enum field extraction
        all_facts_text = " ".join(
            f.get("statement", "") for f in facts if isinstance(f, dict) and f.get("statement")
        )
        dr_fields = self._extract_fields_from_facts(all_facts_text)

        # Extract model_family from paper title as an additional signal
        title_model = self._match_enum(target.title.lower(), self._MODEL_FAMILY_VALUES)
        if title_model and not dr_fields.get("model_family"):
            dr_fields["model_family"] = title_model

        # LLM supplement for coverage-critical fields still empty after heuristics
        critical_fields = ["task", "task_category", "model_architecture", "model_family", "modality_omics"]
        missing = [k for k in critical_fields if not dr_fields.get(k)]
        if missing and all_facts_text:
            paper_text = target.full_text or target.abstract or target.title
            if len(paper_text) > 50:
                llm_fields = await self._llm_extract_missing_fields(target.title, paper_text[:3000], missing)
                for k, v in llm_fields.items():
                    if v:
                        dr_fields[k] = v

        for i, fact in enumerate(facts):
            if not isinstance(fact, dict):
                continue
            statement = fact.get("statement", "")
            if not statement:
                continue
            loc = fact.get("source_locator", {})
            if isinstance(loc, dict):
                loc_text = loc.get("section", "") or ""
            else:
                loc_text = ""

            evidence_status = fact.get("evidence_status", "author_claim")
            evidence_strength = "partially_supported" if judgments else "insufficient"
            claims_for_judgment = [j for cid, j in judg_by_claim.items() if j.get("subject", "") in statement]
            if claims_for_judgment:
                evidence_strength = claims_for_judgment[0].get("verdict", "insufficient")

            fields = {
                "card_id": f"card_dr_{paper_id}_{i:03d}",
                "source_type": "paper",
                "source_paper": source_paper,
                "source_location": SourceLocation(section=loc_text),
                "reliability_flag": "medium" if target.doi or target.pmid else "unverified",
                "key_finding": statement,
                "method_brief": "",
                "archetype": "sc_fm",
                "tags": [f"candidate:{topic_id}"] if topic_id else [],
                "evidence_status": evidence_status,
                "evidence_strength": evidence_strength,
                "deep_read_source": note.get("paper_id", ""),
                # Inject coverage-critical fields from heuristic extraction
                "task": dr_fields.get("task", ""),
                "task_category": dr_fields.get("task_category", ""),
                "modality_omics": dr_fields.get("modality_omics", ""),
                "model_architecture": dr_fields.get("model_architecture", ""),
                "model_family": dr_fields.get("model_family", ""),
                "tissue": dr_fields.get("tissue", ""),
                "cell_type": dr_fields.get("cell_type", ""),
                "modalities_integrated": [],
            }
            try:
                card = card_class(**fields)
                cards.append(card)
            except Exception as e:
                logger.warning(
                    f"Deep-read card validation failed for paper={paper_id} "
                    f"finding_idx={i}: {e}"
                )

        if cards:
            logger.info(
                f"Deep-read: {len(cards)} cards from {target.title[:80]}; "
                f"task={dr_fields.get('task','?')}, model={dr_fields.get('model_family','?')}, "
                f"tissue={dr_fields.get('tissue','?')}"
            )
        return cards

    async def _extract_from_paper(
        self,
        target: ExtractTarget,
        inp: SCFMExtractInput,
        ctx: SkillContext,
        card_class: type[BaseEvidenceCard],
        topic_id: str = "",
    ) -> list[BaseEvidenceCard]:
        text = target.full_text or target.abstract or target.title
        if not text or len(text.strip()) < 100:
            return []

        truncate_len = inp.extraction_text_truncate
        prompt = SCFM_DOMAIN_PROMPT.format(max_findings=inp.max_findings_per_paper)
        prompt += f"""

=== PAPER ===
Title: {target.title}
DOI: {target.doi or 'N/A'} | PMID: {target.pmid or 'N/A'} | Year: {target.year or ''}
Venue: {target.venue or ''}
Authors: {', '.join(target.authors[:5]) if target.authors else ''}

Abstract/Text:
{text[:truncate_len]}

Return a JSON list of finding objects. Each object MUST have ALL of these REQUIRED fields:
key_finding, method_brief, task, task_category, model_architecture, model_family.
If the paper does not explicitly state a required field, infer from context when possible; only leave empty when truly unstated.
The "task" field MUST be one of: cell_type_annotation, gene_expression_prediction, batch_correction,
data_integration, perturbation_prediction, grn_inference, embedding_evaluation,
multimodal_integration, cross_species_transfer, dimensionality_reduction.
The "model_family" field MUST be one of: scVI_family, scGPT, Geneformer, scFoundation, UCE,
MultiVI, scBERT, scGEN, scArches, SIMVI, scTab, scimilarity, TOSICA, RegFormer,
GeneMamba, MambaCell, scHyena, scLong, CLM-X, cellVQ, other.
Return [] only if the paper has NO relevance to single-cell or foundation models at all.

Return ONLY the JSON array, no prose or markdown."""

        from shared.core.llm_client import llm_complete, _parse_json
        raw = await llm_complete(
            prompt,
            system="You are a bioinformatics evidence extractor. Output valid JSON only.",
            budget=ctx.budget,
            phase=self.budget_phase,
        )
        result = _parse_json(raw)
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
            card = self._build_card(target, finding, card_class, topic_id)
            cards.append(card)

        if cards:
            first_card = cards[0]
            logger.info(
                f"Extracted {len(cards)} findings from {target.title[:80]}; "
                f"task={first_card.task}, task_cat={first_card.task_category}, "
                f"model_family={first_card.model_family}, arch={first_card.model_architecture}"
            )
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
        result = SCFMCardExtract._coerce_str(v)
        return result if result else None

    @staticmethod
    def _coerce_int(v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return _try_parse_int(v)
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _coerce_float(v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return _try_parse_float(v)
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _coerce_evidence_state(v: Any) -> Optional[EvidenceState]:
        if v is None or v == "":
            return None
        if isinstance(v, EvidenceState):
            return v
        if isinstance(v, bool):
            return EvidenceState.CONFIRMED if v else EvidenceState.REPORTED_NOT_DONE
        if isinstance(v, str):
            v_lower = v.lower().strip()
            for state in EvidenceState:
                if state.value == v_lower:
                    return state
            if v_lower in ("yes", "true", "1", "y"):
                return EvidenceState.CONFIRMED
            if v_lower in ("no", "false", "0", "n"):
                return EvidenceState.REPORTED_NOT_DONE
        if isinstance(v, (int, float)):
            return EvidenceState.CONFIRMED if bool(v) else EvidenceState.REPORTED_NOT_DONE
        return None

    def _build_card(self, target: ExtractTarget, finding: dict[str, Any],
                    card_class: type[BaseEvidenceCard], topic_id: str = "") -> BaseEvidenceCard:
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

        reliability = "unverified"
        if target.doi or target.pmid:
            reliability = "medium"

        fields: dict[str, Any] = {
            "card_id": f"card_{uuid.uuid4().hex[:12]}",
            "source_type": "paper",
            "source_paper": paper,
            "source_location": location,
            "reliability_flag": reliability,
            "key_finding": self._coerce_str(finding.get("key_finding")),
            "method_brief": self._coerce_str(finding.get("method_brief")),
            "limitation_explicit": self._coerce_opt_str(finding.get("limitation_explicit")),
            "limitation_implicit": self._coerce_opt_str(finding.get("limitation_implicit")),
            "archetype": "sc_fm",
            "tags": finding.get("tags", []) if isinstance(finding.get("tags"), list) else [],
        }
        if topic_id:
            fields["tags"].append(f"candidate:{topic_id}")

        int_fields = {
            "n_cells_pretrain", "n_cells_finetune", "n_features_input",
            "n_parameters", "embedding_dim",
        }
        float_fields = {
            "eval_metric_value", "baseline_metric_value", "improvement_over_baseline",
        }
        evidence_state_fields = {
            "held_out_cell_types", "held_out_tissues", "batch_correction_evaluated",
            "transfer_evaluated", "interpretability_assessed",
            "code_available", "weights_available", "dataset_available",
        }
        list_fields = {"modalities_integrated"}

        model_fields = set(card_class.model_fields.keys())
        for k, v in finding.items():
            if k in model_fields and k not in fields:
                if k in int_fields:
                    fields[k] = self._coerce_int(v)
                elif k in float_fields:
                    fields[k] = self._coerce_float(v)
                elif k in evidence_state_fields:
                    fields[k] = self._coerce_evidence_state(v)
                elif k in list_fields:
                    fields[k] = v if isinstance(v, list) else [v] if v else []
                else:
                    fields[k] = self._coerce_str(v)

        return card_class(**fields)

    async def quality_gate(self, output: SCFMExtractOutput, ctx: SkillContext) -> bool:
        cards = output.cards
        findings_count = output.findings_count
        paper_count = output.paper_count

        if findings_count < 1:
            logger.error(
                "S7 quality gate FAILED: 0 findings extracted "
                f"(paper_count={paper_count})"
            )
            return False

        identity_empty = sum(1 for c in cards if not getattr(c, "key_finding", ""))
        if identity_empty > 0:
            logger.error(
                f"S7 quality gate FAILED (identity): {identity_empty}/{len(cards)} cards "
                f"have empty key_finding"
            )
            return False

        deep_read_cards = [c for c in cards if getattr(c, "deep_read_source", None)]
        if deep_read_cards:
            evidence_linked = sum(1 for c in deep_read_cards if getattr(c, "evidence_status", None))
            evidence_rate = evidence_linked / len(deep_read_cards)
            if evidence_rate < 0.6:
                logger.error(
                    f"S7 quality gate FAILED (evidence): only {evidence_linked}/{len(deep_read_cards)} "
                    f"deep-read cards have evidence_status (rate={evidence_rate:.1%}, threshold=60%)"
                )
                return False

        filled = sum(1 for c in cards
                     if (getattr(c, "task", None) and getattr(c, "task", "unknown") != "unknown")
                     or (getattr(c, "task_category", None) and getattr(c, "task_category", "unknown") != "unknown"))
        fill_rate = filled / max(findings_count, 1)
        min_fill = 0.15 if paper_count <= 1 else 0.40
        if paper_count > 3 and fill_rate < min_fill:
            logger.error(
                f"S7 quality gate FAILED (domain): only {filled}/{findings_count} cards "
                f"have task/task_category info (fill_rate={fill_rate:.1%}, threshold={min_fill:.0%}, "
                f"paper_count={paper_count})"
            )
            return False

        if paper_count > 0:
            avg_cards = findings_count / paper_count
            if avg_cards > 10:
                logger.warning(
                    f"S7 cardinality WARNING: {avg_cards:.1f} avg cards/paper "
                    f"({findings_count} cards from {paper_count} papers)"
                )

        dr_info = ""
        if deep_read_cards:
            dr_info = f", evidence_rate={sum(1 for c in deep_read_cards if getattr(c, 'evidence_status', None))/len(deep_read_cards):.1%}"
        logger.info(
            f"S7 quality gate passed: fill_rate={fill_rate:.1%}{dr_info}, "
            f"cards={findings_count}, papers={paper_count}"
        )
        return True
