from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiteratureCoverageResult:
    candidate_id: str
    evidence_card_count: int = 0
    cited_paper_count: int = 0
    overlapping_count: int = 0
    coverage_ratio: float = 0.0
    missing_key_papers: list[str] = field(default_factory=list)
    status: str = "unknown"


_CITE_PATTERNS = [
    re.compile(r'([A-Z][a-z]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][a-z]+))?),\s*(\d{4})'),
    re.compile(r'\(([^)]+),\s*(\d{4})\)'),
    re.compile(r'(10\.\d{4,}/[^\s"\'<>，。；）)\]】]+)'),
    re.compile(r'(?:GSE|GDS|E-[A-Z]{2,5}-)\d{3,}'),
]

_STOP_WORDS = {'a', 'an', 'the', 'and', 'or', 'of', 'in', 'on', 'to', 'for', 'with',
               'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
               'do', 'does', 'did', 'but', 'not', 'no', 'from', 'by', 'at', 'as'}


def _normalize_title(t: str) -> str:
    t = t.strip().lower()
    t = re.sub(r'[^a-z0-9\s]', '', t)
    words = [w for w in t.split() if w not in _STOP_WORDS and len(w) > 1]
    return ' '.join(words)


def _extract_cited_titles_from_plan(plan: dict[str, Any]) -> set[str]:
    extracted: set[str] = set()

    data_sources = plan.get("data_sources_detail", [])
    for ds in (data_sources or []):
        if isinstance(ds, dict):
            name = (ds.get("name") or "").strip()
            if name:
                extracted.add(name.lower())
            url = str(ds.get("url", ""))
            for p in _CITE_PATTERNS:
                for m in p.finditer(url):
                    extracted.add(m.group(0).lower())

    text_fields = [
        plan.get("summary_zh", ""),
        plan.get("research_question", ""),
        "\n".join(str(s.get("desc", "")) for s in plan.get("technical_roadmap", [])),
    ]
    for text in text_fields:
        for p in _CITE_PATTERNS:
            for m in p.finditer(text):
                extracted.add(m.group(0).lower())

    return extracted


def check_literature_coverage(
    candidate_id: str,
    plan: dict[str, Any],
    evidence_cards: list[dict[str, Any]],
) -> LiteratureCoverageResult:
    result = LiteratureCoverageResult(candidate_id=candidate_id)
    result.evidence_card_count = len(evidence_cards)

    if not evidence_cards:
        result.status = "unknown"
        return result

    cited_markers = _extract_cited_titles_from_plan(plan)
    result.cited_paper_count = len(cited_markers)

    card_norm: list[tuple[str, str, str, str]] = []
    for card in evidence_cards:
        title = (card.get("paper_title") or "").strip()
        doi = (card.get("paper_doi") or "").strip().lower()
        pmid = str(card.get("paper_pmid", "")).strip()
        authors = (card.get("paper_authors") or [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]
        first_author = (authors[0] if authors else "").lower()
        year = str(card.get("paper_year", ""))
        card_norm.append((title, doi, pmid, first_author + " " + year))

    overlap = 0
    missing: list[str] = []
    for title, doi, pmid, afy in card_norm:
        matched = False
        norm_title = _normalize_title(title)
        for cited in cited_markers:
            cited_norm = _normalize_title(cited)
            if not cited_norm:
                continue
            if doi and doi in cited:
                matched = True
                break
            if pmid and pmid in cited:
                matched = True
                break
            cw = set(cited_norm.split())
            tw = set(norm_title.split())
            if cw and tw:
                jaccard = len(cw & tw) / min(len(cw | tw), 50)
                if jaccard > 0.5:
                    matched = True
                    break
            if afy.strip() and afy in cited:
                matched = True
                break
        if matched:
            overlap += 1
        elif len(evidence_cards) <= 50:
            missing.append(title[:100])

    result.overlapping_count = overlap
    result.coverage_ratio = round(overlap / len(evidence_cards), 2)
    result.missing_key_papers = missing

    if result.coverage_ratio >= 0.5:
        result.status = "good"
    elif result.coverage_ratio >= 0.2:
        result.status = "partial"
    elif overlap > 0:
        result.status = "poor"
    else:
        result.status = "poor"

    return result
