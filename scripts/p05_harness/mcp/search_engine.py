from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Optional

from shared.core.config import PROJECT_ROOT
from shared.core.logging_setup import get_logger
from shared.mcp.base.base_mcp import MCPResult
from shared.mcp.registry import MCPRegistry

logger = get_logger("p05_harness.mcp")

DEFAULT_SOURCES = ["semantic_scholar", "pubmed", "biorxiv", "arxiv"]


class SearchEngine:
    """Multi-source literature search + dedup for p05 harness.

    Creates its own lightweight MCPRegistry. Does NOT require a full SkillContext.
    """

    def __init__(
        self,
        sources: list[str] | None = None,
        max_per_source: int = 10,
        year_range: str | None = None,
        recent_boost_year: int = 2024,
    ):
        source_names = sources or DEFAULT_SOURCES
        self.max_per_source = max_per_source
        self.year_range = year_range
        self.recent_boost_year = recent_boost_year
        self.search_calls = 0
        self.lookup_calls = 0  # verify_doi/verify_pmid 直查次数
        self.registry = MCPRegistry(project_id="p05_harness")
        self._sources = [s for s in source_names if self.registry.get(s) is not None]
        logger.info(f"SearchEngine ready: sources={self._sources} recent_boost={self.recent_boost_year}")

    async def search(self, query: str, max_per_source: int | None = None) -> list[dict[str, Any]]:
        self.search_calls += 1
        limit = max_per_source or self.max_per_source

        cache_key = f"{query}|{limit}|{self.year_range or ''}"
        cached = await self._try_cache_get(cache_key)
        if cached is not None:
            return cached

        tasks = []

        for src in self._sources:
            mcp = self.registry.get(src)
            if mcp is None:
                continue
            if src == "semantic_scholar":
                tasks.append(mcp.search(query, limit=limit, year_range=self.year_range))  # type: ignore[attr-defined]
            elif src == "pubmed":
                tasks.append(mcp.search(query, retmax=limit))  # type: ignore[attr-defined]
            elif src in ("arxiv", "crossref"):
                tasks.append(mcp.search(query, limit=limit))  # type: ignore[attr-defined]
            elif src == "biorxiv":
                tasks.append(mcp.search_by_query(query, limit=limit))  # type: ignore[attr-defined]
            elif hasattr(mcp, "search_by_query"):
                tasks.append(mcp.search_by_query(query, limit=limit))  # type: ignore[attr-defined]
            elif hasattr(mcp, "search"):
                tasks.append(mcp.search(query, limit=limit))  # type: ignore[attr-defined]
            else:
                continue

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_papers: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Search task failed: {result}")
                continue
            if isinstance(result, MCPResult):
                papers = self._extract_papers(result)
                all_papers.extend(papers)

        deduped = self._deduplicate(all_papers)
        scored = self._score_and_rank(deduped)
        result = scored[:20]
        await self._try_cache_set(cache_key, result)
        return result

    async def search_multi(self, queries: list[str], max_per_source: int | None = None) -> list[dict[str, Any]]:
        tasks = [self.search(q, max_per_source) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_papers: list[dict[str, Any]] = []
        for papers in results:
            if isinstance(papers, Exception):
                logger.warning(f"search_multi task failed: {papers}")
                continue
            if isinstance(papers, list):
                all_papers.extend(papers)
        return self._deduplicate(all_papers)[:30]

    async def verify_doi(self, doi: str) -> dict[str, Any] | None:
        self.lookup_calls += 1
        mcp = self.registry.get("crossref")
        if mcp is None:
            return None
        try:
            result = await mcp.resolve_doi(doi)  # type: ignore[attr-defined]
            if result.success and isinstance(result.data, dict):
                msg = result.data.get("message", {})
                return {
                    "title": _safe_str(msg, "title", ""),
                    "doi": doi,
                    "year": msg.get("created", {}).get("date-parts", [[None]])[0][0],
                    "verified": True,
                }
        except Exception as e:
            logger.warning(f"DOI verification failed for {doi}: {e}")
        return None

    async def verify_pmid(self, pmid: str) -> dict[str, Any] | None:
        self.lookup_calls += 1
        mcp = self.registry.get("pubmed")
        if mcp is None:
            return None
        try:
            result = await mcp.fetch_summaries([pmid])  # type: ignore[attr-defined]
            if result.success and isinstance(result.data, dict):
                uid_data = result.data.get("result", {}).get(pmid, {})
                if uid_data:
                    return {
                        "title": uid_data.get("title", ""),
                        "pmid": pmid,
                        "year": uid_data.get("pubdate", "")[:4],
                        "verified": True,
                    }
        except Exception as e:
            logger.warning(f"PMID verification failed for {pmid}: {e}")
        return None

    async def close(self) -> None:
        await self.registry.aclose_all()

    @staticmethod
    async def _try_cache_get(cache_key: str) -> list[dict[str, Any]] | None:
        try:
            from shared.core.cache import ResponseCache
            from shared.core.config import settings as _cfg
            raw = await (await ResponseCache.get_instance()).get("mcp", cache_key)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
        return None

    @staticmethod
    async def _try_cache_set(cache_key: str, papers: list[dict[str, Any]]) -> None:
        try:
            from shared.core.cache import ResponseCache
            from shared.core.config import settings as _cfg
            await (await ResponseCache.get_instance()).set(
                "mcp", json.dumps(papers, ensure_ascii=False, default=str),
                _cfg.mcp_cache_ttl_seconds, cache_key,
            )
        except Exception:
            pass

    def _extract_papers(self, result: MCPResult) -> list[dict[str, Any]]:
        papers: list[dict[str, Any]] = []
        data = result.data
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("data") or data.get("results") or data.get("items") or []
            if isinstance(items, dict):
                items = list(items.values())
            if isinstance(items, str):
                return []
        else:
            return []

        for item in items:
            if not isinstance(item, dict):
                continue
            paper = _normalize_paper(item, result.source)
            if paper.get("title"):
                papers.append(paper)
        return papers

    def _deduplicate(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for p in papers:
            title = (p.get("title") or "").strip().lower()
            if not title:
                continue
            key = hashlib.md5(title.encode()).hexdigest()
            if key in seen:
                existing = seen[key]
                if (p.get("citation_count") or 0) > (existing.get("citation_count") or 0):
                    seen[key] = p
                if p.get("doi") and not existing.get("doi"):
                    existing["doi"] = p["doi"]
                if p.get("pmid") and not existing.get("pmid"):
                    existing["pmid"] = p["pmid"]
            else:
                seen[key] = p
        return list(seen.values())

    def _score_and_rank(self, papers: list[dict[str, Any]], recent_boost_year: int | None = None) -> list[dict[str, Any]]:
        boost_year = recent_boost_year if recent_boost_year is not None else self.recent_boost_year

        def _score(p: dict[str, Any]) -> float:
            s = 0.0
            if p.get("citation_count"):
                s += min(int(p["citation_count"]) / 100, 5.0)
            if p.get("year"):
                try:
                    year = int(str(p["year"])[:4])
                    s += max(0, (year - 2018) * 0.2)
                    if year >= boost_year:
                        s += (year - boost_year + 1) * 1.5
                except (ValueError, TypeError):
                    pass
            if p.get("abstract"):
                s += min(len(str(p["abstract"])) / 500, 2.0)
            if p.get("doi"):
                s += 0.5
            if p.get("pmid"):
                s += 0.3
            return s

        scored = [(p, _score(p)) for p in papers]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored]


def boost_recent(papers: list[dict[str, Any]], boost_year: int = 2024) -> list[dict[str, Any]]:
    """Re-rank papers with recency priority for Phase 1.5 and similar callers."""
    se = SearchEngine(recent_boost_year=boost_year)
    return se._score_and_rank(papers, recent_boost_year=boost_year)


def _normalize_paper(item: dict[str, Any], source: str) -> dict[str, Any]:
    if source == "semantic_scholar":
        ext_ids = item.get("externalIds") or {}
        authors_raw = item.get("authors") or []
        authors = [a.get("name", "") for a in authors_raw if isinstance(a, dict)]
        return {
            "title": _safe_str(item, "title"),
            "authors": authors,
            "year": item.get("year"),
            "venue": item.get("venue", ""),
            "abstract": item.get("abstract") or "",
            "doi": ext_ids.get("DOI", ""),
            "pmid": str(ext_ids.get("PubMed", "")) if ext_ids.get("PubMed") else "",
            "citation_count": item.get("citationCount", 0),
            "source": source,
        }
    if source == "pubmed":
        return {
            "title": _safe_str(item, "title"),
            "authors": [],
            "year": item.get("pubdate", "")[:4] if item.get("pubdate") else None,
            "venue": item.get("source", ""),
            "abstract": "",
            "doi": item.get("elocationid", "").replace("doi: ", ""),
            "pmid": str(item.get("uid", "")),
            "citation_count": 0,
            "source": source,
        }
    return {
        "title": _safe_str(item, "title"),
        "authors": item.get("authors") or [],
        "year": item.get("year") or item.get("published_year"),
        "venue": item.get("venue") or item.get("journal", ""),
        "abstract": item.get("abstract") or item.get("summary") or "",
        "doi": item.get("doi") or "",
        "pmid": str(item.get("pmid", "")) if item.get("pmid") else "",
        "citation_count": item.get("citation_count", 0) or item.get("citations", 0),
        "source": source,
    }


def _safe_str(d: dict[str, Any], key: str, default: Any = "") -> Any:
    v = d.get(key, "")
    if isinstance(v, list):
        return v[0] if v else ""
    return v or default
