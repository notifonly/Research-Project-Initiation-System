from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from shared.utils.ids import gen_id, utc_now_iso


class EvidenceState(str, Enum):
    CONFIRMED = "confirmed"
    REPORTED_NOT_DONE = "reported_not_done"
    NOT_REPORTED = "not_reported"
    NOT_EXTRACTED = "not_extracted"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"

EVIDENCE_STATE_WEIGHTS: dict[EvidenceState, float] = {
    EvidenceState.REPORTED_NOT_DONE: 1.00,
    EvidenceState.NOT_REPORTED: 0.55,
    EvidenceState.CONFIRMED: 0.00,
    EvidenceState.NOT_EXTRACTED: 0.00,
    EvidenceState.CONFLICTING: 0.00,
    EvidenceState.NOT_APPLICABLE: 0.00,
}


ARCHETYPE_V2G = "v2g"
ARCHETYPE_PRS = "prs"
ARCHETYPE_SC_FM = "sc_fm"
ARCHETYPE_OMICS_SCORE = "omics_score"
ARCHETYPE_CROSS_ETHNIC = "cross_ethnic_multiomics"
ARCHETYPE_SPATIAL_GWAS = "spatial_gwas_network"
ARCHETYPE_BASE = "base"

VALID_ARCHETYPES = frozenset({ARCHETYPE_V2G, ARCHETYPE_PRS, ARCHETYPE_SC_FM, ARCHETYPE_OMICS_SCORE, ARCHETYPE_CROSS_ETHNIC, ARCHETYPE_SPATIAL_GWAS, ARCHETYPE_BASE})


class SourcePaper(BaseModel):
    doi: Optional[str] = None
    pmid: Optional[str] = None
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    url: Optional[str] = None


class SourceLocation(BaseModel):
    section: str = ""
    excerpt: str = ""
    page: Optional[int] = None
    table_or_figure: Optional[str] = None


SourceType = Literal["paper", "database", "preprint", "code_repo", "dataset"]


class BaseEvidenceCard(BaseModel):
    """Base evidence card - one paper can yield multiple cards (per-finding granularity)."""

    card_id: str = Field(default_factory=lambda: gen_id("card"))
    source_type: SourceType = "paper"
    source_paper: SourcePaper = Field(default_factory=SourcePaper)
    source_database: Optional[str] = None
    source_location: SourceLocation = Field(default_factory=SourceLocation)
    extracted_at: str = Field(default_factory=utc_now_iso)
    reliability_flag: Literal["high", "medium", "low", "unverified"] = "unverified"
    key_finding: str = ""
    method_brief: str = ""
    limitation_explicit: Optional[str] = None
    limitation_implicit: Optional[str] = None
    archetype: str = "base"
    tags: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    def coverage_axes(self) -> dict[str, Any]:
        """Map card fields to the archetype-specific coverage axes.
        Subclasses must override this to return 5 axes matching their archetype config.
        """
        return {}

    def to_flat_dict(self) -> dict:
        d = self.model_dump()
        paper = d.pop("source_paper", {})
        loc = d.pop("source_location", {})
        for k, v in paper.items():
            d[f"paper_{k}"] = v
        for k, v in loc.items():
            d[f"loc_{k}"] = v
        d["tags_str"] = "|".join(d.get("tags", []))
        return d


class V2GEvidenceCard(BaseEvidenceCard):
    """Archetype A: Variant-to-Function evidence card (35+ fields)."""

    archetype: str = "v2g"
    trait_efo: Optional[str] = None
    trait_label: Optional[str] = None
    lead_variant_rsid: Optional[str] = None
    genomic_position: Optional[str] = None
    chrom: Optional[str] = None
    pos: Optional[int] = None
    locus_genes: list[str] = Field(default_factory=list)
    functional_modality: Optional[str] = None
    causal_gene_claimed: Optional[str] = None
    cell_type: Optional[str] = None
    tissue: Optional[str] = None
    sample_size: Optional[int] = None
    population_ancestry: Optional[str] = None
    p_value: Optional[float] = None
    effect_size_beta: Optional[float] = None
    significance_threshold: Optional[float] = None
    fine_mapping_method: Optional[str] = None
    coloc_result: Optional[str] = None
    has_replication: Optional[bool] = None
    summary_stats_available: Optional[bool] = None
    code_available: Optional[bool] = None
    raw_data_accession: Optional[str] = None

    def coverage_axes(self) -> dict:
        return {
            "trait": self.trait_label or self.trait_efo or "unknown",
            "locus": self.lead_variant_rsid or self.genomic_position or "unknown",
            "functional_modality": self.functional_modality or "unknown",
            "cell_type": self.cell_type or "unknown",
            "population_ancestry": self.population_ancestry or "unknown",
        }
