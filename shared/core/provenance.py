from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from shared.evidence.base_card import BaseEvidenceCard


HGNC_GENE_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]{1,20}$")
RSID_PATTERN = re.compile(r"^rs\d+$")
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/.+")


@dataclass
class ProvenanceIssue:
    stage: str
    card_id: str
    severity: str  # error | warning | info
    field: str
    message: str


@dataclass
class ProvenanceResult:
    card_id: str
    passed: bool
    issues: list[ProvenanceIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "passed": self.passed,
            "issues": [
                {"stage": i.stage, "severity": i.severity, "field": i.field, "message": i.message}
                for i in self.issues
            ],
        }


class ProvenancePipeline:
    """4-stage provenance: format validation → completeness → backtrace → cross-card consistency."""

    REQUIRED_FIELDS = [
        "card_id",
        "source_type",
        "key_finding",
    ]
    V2G_RECOMMENDED = [
        "trait_label",
        "lead_variant_rsid",
        "functional_modality",
        "cell_type",
        "population_ancestry",
    ]

    def __init__(self, known_genes: Optional[set[str]] = None) -> None:
        self.known_genes = known_genes or set()
        self._llm_backtrace: Any = None

    def set_llm_backtrace(self, fn: Any) -> None:
        self._llm_backtrace = fn

    def validate(self, card: BaseEvidenceCard) -> ProvenanceResult:
        result = ProvenanceResult(card_id=card.card_id, passed=True)
        self._stage1_format(card, result)
        self._stage2_completeness(card, result)
        self._stage3_backtrace(card, result)
        result.passed = not any(i.severity == "error" for i in result.issues)
        return result

    def validate_batch(self, cards: list[BaseEvidenceCard]) -> list[ProvenanceResult]:
        results = [self.validate(c) for c in cards]
        self._stage4_cross_card(cards, results)
        return results

    def _stage1_format(self, card: BaseEvidenceCard, result: ProvenanceResult) -> None:
        if card.source_paper.doi and not DOI_PATTERN.match(card.source_paper.doi):
            result.issues.append(
                ProvenanceIssue("format", card.card_id, "warning", "paper_doi", "DOI format looks invalid")
            )
        if isinstance(card, BaseEvidenceCard):
            v2g = getattr(card, "lead_variant_rsid", None)
            if v2g and not RSID_PATTERN.match(v2g):
                result.issues.append(
                    ProvenanceIssue("format", card.card_id, "error", "lead_variant_rsid", f"Invalid rsID: {v2g}")
                )
        for gene in getattr(card, "locus_genes", []) or []:
            if self.known_genes and gene not in self.known_genes and not HGNC_GENE_PATTERN.match(gene):
                result.issues.append(
                    ProvenanceIssue("format", card.card_id, "warning", "locus_genes", f"Gene symbol suspicious: {gene}")
                )

    def _stage2_completeness(self, card: BaseEvidenceCard, result: ProvenanceResult) -> None:
        d = card.model_dump()
        for f in self.REQUIRED_FIELDS:
            v = d.get(f)
            if v is None or v == "" or v == []:
                result.issues.append(
                    ProvenanceIssue("completeness", card.card_id, "error", f, f"Required field missing: {f}")
                )
        if card.archetype == "v2g":
            for f in self.V2G_RECOMMENDED:
                v = d.get(f)
                if v is None or v == "":
                    result.issues.append(
                        ProvenanceIssue("completeness", card.card_id, "warning", f, f"Recommended field missing: {f}")
                    )

    def _stage3_backtrace(self, card: BaseEvidenceCard, result: ProvenanceResult) -> None:
        if not card.source_location.excerpt and card.key_finding:
            result.issues.append(
                ProvenanceIssue("backtrace", card.card_id, "warning", "source_location.excerpt",
                                "Key finding has no source excerpt for backtrace")
            )
        if card.source_type == "paper" and not card.source_paper.title:
            result.issues.append(
                ProvenanceIssue("backtrace", card.card_id, "error", "source_paper.title", "Paper card missing title")
            )

    def _stage4_cross_card(self, cards: list[BaseEvidenceCard], results: list[ProvenanceResult]) -> None:
        finding_map: dict[str, list[str]] = {}
        for card in cards:
            key = card.key_finding.strip().lower()[:100]
            if key:
                finding_map.setdefault(key, []).append(card.card_id)
        for key, ids in finding_map.items():
            if len(ids) > 1:
                for cid in ids:
                    for r in results:
                        if r.card_id == cid:
                            r.issues.append(
                                ProvenanceIssue("cross_card", cid, "info", "key_finding",
                                                f"Duplicate finding across {len(ids)} cards")
                            )
