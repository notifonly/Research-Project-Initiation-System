from __future__ import annotations

import asyncio
from typing import Any, Optional

from pydantic import Field

from shared.core.token_budget import BudgetPhase
from shared.mcp.base.base_mcp import MCPResult
from pydantic import BaseModel

from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput


class MultiSourceSearchInput(SkillInput):
    queries: list[str] = Field(default_factory=list)
    max_per_source: int = 20
    sources: list[str] = Field(default_factory=lambda: ["semantic_scholar", "pubmed", "biorxiv", "arxiv", "crossref"])
    year_range: Optional[str] = None


class PaperHitModel(BaseModel):
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    doi: Optional[str] = None
    pmid: Optional[str] = None
    abstract: str = ""
    url: str = ""
    source: str = ""
    citation_count: int = 0


class MultiSourceSearchOutput(SkillOutput):
    papers: list[dict[str, Any]] = Field(default_factory=list)
    per_source_counts: dict[str, int] = Field(default_factory=dict)
    deduplicated_count: int = 0


class MultiSourceSearch(BaseSkill):
    """S4: Search across multiple literature sources in parallel, deduplicate results."""

    name = "multi_source_search"
    description = "Search Semantic Scholar, PubMed, bioRxiv, arXiv, Crossref, PMC, Europe PMC in parallel and deduplicate"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = MultiSourceSearchInput
    output_schema = MultiSourceSearchOutput

    async def execute(self, inp: MultiSourceSearchInput, ctx: SkillContext) -> MultiSourceSearchOutput:
        tasks: list[tuple[str, Any]] = []
        for query in inp.queries:
            if "semantic_scholar" in inp.sources:
                tasks.append(("semantic_scholar", ctx.mcp_registry.semantic_scholar().search(
                    query, limit=inp.max_per_source, year_range=inp.year_range)))
            if "pubmed" in inp.sources:
                tasks.append(("pubmed", ctx.mcp_registry.pubmed().search(
                    query, retmax=inp.max_per_source)))
            if "biorxiv" in inp.sources:
                tasks.append(("biorxiv", ctx.mcp_registry.biorxiv().search_by_query(
                    query, limit=inp.max_per_source)))
            if "arxiv" in inp.sources:
                tasks.append(("arxiv", ctx.mcp_registry.arxiv().search(
                    query, limit=inp.max_per_source)))
            if "crossref" in inp.sources:
                tasks.append(("crossref", ctx.mcp_registry.crossref().search(
                    query, limit=inp.max_per_source)))
            if "pmc" in inp.sources:
                tasks.append(("pmc", ctx.mcp_registry.pmc().search(
                    query, limit=inp.max_per_source)))
            if "europe_pmc" in inp.sources:
                tasks.append(("europe_pmc", ctx.mcp_registry.europe_pmc().search(
                    query, limit=inp.max_per_source)))

        results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        source_names = [t[0] for t in tasks]

        all_papers: list[dict[str, Any]] = []
        per_source: dict[str, int] = {}
        for source, result in zip(source_names, results):
            if isinstance(result, Exception):
                continue
            if not isinstance(result, MCPResult) or not result.success:
                continue
            papers = await self._extract_papers(source, result.data, ctx)
            per_source[source] = per_source.get(source, 0) + len(papers)
            all_papers.extend(papers)

        deduped = self._deduplicate(all_papers)
        deduped = [p for p in deduped if p.get("title") or p.get("abstract")]
        self._metrics.update({
            "raw_count": len(all_papers),
            "deduped_count": len(deduped),
            "sources_used": list(per_source.keys()),
        })
        return MultiSourceSearchOutput(
            papers=deduped,
            per_source_counts=per_source,
            deduplicated_count=len(deduped),
        )

    async def _extract_papers(self, source: str, data: Any, ctx: SkillContext) -> list[dict[str, Any]]:
        papers: list[dict[str, Any]] = []
        if data is None:
            return papers
        if source == "semantic_scholar":
            for p in data.get("data", []):
                ext_ids = p.get("externalIds", {}) or {}
                papers.append({
                    "title": p.get("title", ""),
                    "authors": [a.get("name", "") for a in p.get("authors", [])] if isinstance(p.get("authors"), list) else [],
                    "year": p.get("year"),
                    "venue": p.get("venue", ""),
                    "doi": ext_ids.get("DOI"),
                    "pmid": ext_ids.get("PubMed"),
                    "abstract": p.get("abstract") or "",
                    "url": f"https://www.semanticscholar.org/paper/{p.get('paperId','')}",
                    "source": source,
                    "citation_count": p.get("citationCount", 0),
                    "paper_id": p.get("paperId", ""),
                })
        elif source == "pubmed":
            id_list = data.get("esearchresult", {}).get("idlist", [])
            if id_list and ctx.mcp_registry:
                try:
                    pmids_to_fetch = id_list[:50]
                    summ_resp = await ctx.mcp_registry.pubmed().fetch_summaries(pmids_to_fetch)
                    abstract_map: dict[str, str] = {}
                    try:
                        abs_resp = await ctx.mcp_registry.pubmed().fetch_full_records(pmids_to_fetch)
                        if abs_resp.success and abs_resp.data and isinstance(abs_resp.data, str):
                            abstract_map = self._parse_medline_abstracts(abs_resp.data)
                    except Exception:
                        pass
                    if summ_resp.success and summ_resp.data:
                        result_map = summ_resp.data.get("result", {})
                        for pmid in id_list:
                            entry = result_map.get(pmid, {})
                            if not isinstance(entry, dict):
                                continue
                            authors = [a.get("name", "") for a in (entry.get("authors") or []) if isinstance(a, dict)]
                            papers.append({
                                "title": entry.get("title", ""),
                                "authors": authors,
                                "year": int(entry.get("pubdate", "0")[:4]) if entry.get("pubdate", "")[:4].isdigit() else None,
                                "venue": entry.get("fulljournalname", entry.get("source", "")),
                                "doi": None,
                                "pmid": pmid,
                                "abstract": abstract_map.get(pmid, ""),
                                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                "source": source,
                                "citation_count": 0,
                                "paper_id": pmid,
                            })
                        return papers
                except Exception:
                    pass
            for pmid in id_list:
                papers.append({
                    "title": "",
                    "authors": [],
                    "year": None,
                    "venue": "",
                    "doi": None,
                    "pmid": pmid,
                    "abstract": "",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "source": source,
                    "citation_count": 0,
                    "paper_id": pmid,
                })
        elif source in ("arxiv",):
            import feedparser
            try:
                parsed = data if isinstance(data, dict) else feedparser.parse(data)
                entries = parsed.get("entries", []) if isinstance(parsed, dict) else parsed.entries
                for entry in entries if isinstance(entries, list) else []:
                    arxiv_id = entry.get("id", "").split("/abs/")[-1] if isinstance(entry.get("id"), str) else ""
                    papers.append({
                        "title": entry.get("title", "").replace("\n", " ").strip(),
                        "authors": [a.get("name", "") for a in (entry.get("authors") or [])] if isinstance(entry.get("authors"), list) else [],
                        "year": int(entry.get("published", "0")[:4]) if entry.get("published") else None,
                        "venue": "arXiv",
                        "doi": None,
                        "pmid": None,
                        "abstract": entry.get("summary", "").replace("\n", " ").strip(),
                        "url": entry.get("link", f"https://arxiv.org/abs/{arxiv_id}"),
                        "source": source,
                        "citation_count": 0,
                        "paper_id": arxiv_id,
                        "arxiv_id": arxiv_id,
                    })
            except Exception:
                pass
        elif source in ("crossref",):
            for item in (data.get("message", {}).get("items", []) if isinstance(data, dict) else []):
                papers.append({
                    "title": item.get("title", [""])[0] if item.get("title") else "",
                    "authors": [a.get("family", "") for a in (item.get("author") or []) if isinstance(a, dict)],
                    "year": int(item.get("published-print", {}).get("date-parts", [[None]])[0][0] or
                               item.get("published-online", {}).get("date-parts", [[None]])[0][0] or 0),
                    "venue": (item.get("container-title") or [""])[0],
                    "doi": item.get("DOI"),
                    "pmid": None,
                    "abstract": (item.get("abstract") or "").replace("<p>", "").replace("</p>", ""),
                    "url": item.get("URL") or f"https://doi.org/{item.get('DOI', '')}",
                    "source": source,
                    "citation_count": item.get("is-referenced-by-count", 0),
                    "paper_id": item.get("DOI", ""),
                })
        elif source in ("pmc", "europe_pmc"):
            items = []
            if source == "europe_pmc" and isinstance(data, dict):
                items = data.get("resultList", {}).get("result", [])
            elif isinstance(data, dict):
                items = data.get("esearchresult", {}).get("idlist", [])
                for pmid in items[:50]:
                    papers.append({
                        "title": "",
                        "authors": [],
                        "year": None,
                        "venue": "",
                        "doi": None,
                        "pmid": pmid,
                        "abstract": "",
                        "url": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmid}/" if source == "pmc" else f"https://europepmc.org/article/MED/{pmid}",
                        "source": source,
                        "citation_count": 0,
                        "paper_id": pmid,
                    })
                return papers
            for item in items:
                papers.append({
                    "title": item.get("title", ""),
                    "authors": [a.strip() for a in (item.get("authorString", "") or "").split(",") if a.strip()],
                    "year": int(item.get("firstPublicationDate", "0")[:4]) if item.get("firstPublicationDate") else None,
                    "venue": item.get("journalTitle", "") or item.get("bookOrReportDetails", {}).get("publisher", ""),
                    "doi": item.get("doi"),
                    "pmid": str(item.get("pmid", "")),
                    "pmcid": item.get("pmcid", "") or item.get("id"),
                    "abstract": item.get("abstractText", ""),
                    "url": item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url", "") if isinstance(item.get("fullTextUrlList"), dict) else "",
                    "source": source,
                    "citation_count": item.get("citedByCount", 0),
                    "paper_id": item.get("id", "") or item.get("pmcid", ""),
                })
        return papers

    @staticmethod
    def _parse_medline_abstracts(raw: str) -> dict[str, str]:
        records = raw.split("\n\n\n")
        abstracts: dict[str, str] = {}
        for rec in records:
            pmid = None
            ab_lines: list[str] = []
            in_ab = False
            for line in rec.split("\n"):
                if line.startswith("PMID- "):
                    pmid = line[6:].strip()
                    in_ab = False
                elif line.startswith("AB  - "):
                    in_ab = True
                    ab_lines.append(line[6:].strip())
                elif line.startswith("      ") and in_ab:
                    ab_lines.append(line.strip())
                elif line and not line.startswith(" "):
                    in_ab = False
            if pmid and ab_lines:
                abstracts[pmid] = " ".join(ab_lines)
        return abstracts

    def _deduplicate(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for p in papers:
            key = p.get("doi") or p.get("pmid") or p.get("paper_id") or p.get("title", "").lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(p)
        return deduped

    async def quality_gate(self, output: MultiSourceSearchOutput, ctx: SkillContext) -> bool:
        if not output.success:
            return False
        return output.deduplicated_count > 0
