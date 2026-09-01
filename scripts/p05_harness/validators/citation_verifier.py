from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from scripts.p05_harness.mcp.search_engine import SearchEngine

# 数据集/数据库 accession 模式：GEO、ArrayExpress、ENCODE、SRA
_ACCESSION_PATTERN = r"((?:GSE|GDS)\d{3,}|E-[A-Z]{2,5}-\d{3,}|ENC(?:SR|FF)\d{3}[A-Z]{3}|[SED]RP\d{4,})"

# 每类引用最多验证条数（控制 MCP 开销）
_MAX_VERIFY_PER_TYPE = {"doi": 15, "pmid": 10, "accession": 10, "author_year": 8}


@dataclass
class CitationCheckResult:
    ref_type: str = ""  # doi | pmid | accession | author_year
    doi: str = ""
    pmid: str = ""
    title: str = ""
    accession: str = ""
    display: str = ""  # 人类可读的引用串，用于报告与告警
    exists: bool = False
    # 三态：verified（核实通过）| not_found（疑似幻觉）| unverifiable（检索手段无法核实，需人工复核）
    status: str = ""
    verified_title: str = ""
    verified_year: str = ""
    error: str = ""


async def verify_citations(
    plan: dict[str, Any],
    search_engine: SearchEngine,
    context_keywords: str = "",
) -> list[CitationCheckResult]:
    """Verify all references cited in a research plan via MCP lookups.

    支持四类引用：DOI（CrossRef 解析）、PMID（PubMed 摘要）、
    数据集 accession（文献检索是否存在提及）、作者-年份（启发式检索匹配）。
    context_keywords 提供领域关键词（如方法名/疾病名），提高作者-年份检索命中率。
    """
    refs = _extract_references(plan)
    results: list[CitationCheckResult] = []

    type_counts: dict[str, int] = {}
    for ref in refs:
        ref_type = ref.get("type", "")
        count = type_counts.get(ref_type, 0)
        if count >= _MAX_VERIFY_PER_TYPE.get(ref_type, 5):
            continue
        type_counts[ref_type] = count + 1

        result = CitationCheckResult(
            ref_type=ref_type,
            doi=ref.get("doi", ""),
            pmid=ref.get("pmid", ""),
            title=ref.get("title", ""),
            accession=ref.get("accession", ""),
            display=ref.get("display", ""),
        )

        if ref.get("doi"):
            # DOI 解析接口可靠：找不到即为强幻觉信号
            verified = await search_engine.verify_doi(ref["doi"])
            if verified:
                result.exists = True
                result.status = "verified"
                result.verified_title = verified.get("title", "")
                result.verified_year = str(verified.get("year") or "")
            else:
                result.status = "not_found"
                result.error = f"DOI {ref['doi']} not found"
        elif ref.get("pmid"):
            verified = await search_engine.verify_pmid(ref["pmid"])
            if verified:
                result.exists = True
                result.status = "verified"
                result.verified_title = verified.get("title", "")
                result.verified_year = str(verified.get("year") or "")
            else:
                result.status = "not_found"
                result.error = f"PMID {ref['pmid']} not found"
        elif ref.get("accession"):
            # accession 无专门解析接口，文献检索对数据集编号覆盖有限：
            # 检不到不代表幻觉，标记为 unverifiable 需人工在 GEO/ENCODE 核对
            papers = await search_engine.search(ref["accession"], max_per_source=3)
            if papers:
                result.exists = True
                result.status = "verified"
                result.verified_title = papers[0].get("title", "")
                result.verified_year = str(papers[0].get("year") or "")
            else:
                result.status = "unverifiable"
                result.error = f"Accession {ref['accession']} 文献检索未覆盖，建议人工在 GEO/ENCODE 核实"
        elif ref.get("name") and ref.get("year"):
            # 作者-年份启发式：宽检索（含领域关键词）后匹配年份 ±1 + 第一作者姓氏
            verified = await _verify_author_year(ref["name"], ref["year"], search_engine, context_keywords)
            if verified:
                result.exists = True
                result.status = "verified"
                result.verified_title = verified.get("title", "")
                result.verified_year = str(verified.get("year") or "")
            else:
                result.status = "not_found"
                result.error = f"{ref['name']} ({ref['year']}) 未检索到匹配文献（疑似幻觉，建议人工复核）"

        results.append(result)

    return results


async def _verify_author_year(
    name: str, year: str, search_engine: SearchEngine, context_keywords: str = ""
) -> dict[str, Any] | None:
    """Verify an author-year style citation via heuristic search.

    两轮检索：先用 姓氏+年份+领域关键词 精确查，未命中再退回 姓氏+年份 宽查；
    年份容忍 ±1（预印本与正式发表年份差异）。
    """
    surname = name.split()[0].strip().rstrip(",")
    if not surname:
        return None
    try:
        target_year = int(str(year)[:4])
    except ValueError:
        return None

    # 查询策略：精确（姓氏+年份+领域词）→ 领域词无年份（API 对年份窄化敏感）→ 宽查（姓氏+年份）
    queries: list[tuple[str, int]] = [(f"{surname} {year}", 10)]
    if context_keywords:
        queries.insert(0, (f"{surname} {year} {context_keywords}", 5))
        queries.insert(1, (f"{surname} {context_keywords}", 5))

    seen_titles: set[str] = set()
    for query, per_source in queries:
        papers = await search_engine.search(query, max_per_source=per_source)
        for p in papers:
            title_key = (p.get("title") or "").strip().lower()
            if title_key and title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            try:
                paper_year = int(str(p.get("year") or "")[:4])
            except ValueError:
                continue
            if abs(paper_year - target_year) > 1:
                continue
            authors = p.get("authors") or []
            author_text = " ".join(str(a) for a in authors).lower()
            if surname.lower() in author_text or not authors:
                return p
    return None


def _extract_references(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract all citable references from a research plan."""
    refs: list[dict[str, Any]] = []

    data_sources = plan.get("data_sources_detail", [])
    for ds in (data_sources or []):
        if isinstance(ds, dict):
            url = ds.get("url", "")
            ref_info = _parse_citation_from_text(str(url))
            if ref_info.get("doi") or ref_info.get("pmid") or ref_info.get("accession"):
                ref_info["title"] = ds.get("name", "")
                refs.append(ref_info)
            # 数据集名称本身是 accession 的情况（如 name=GSE200633）
            name = str(ds.get("name", ""))
            acc_match = re.fullmatch(_ACCESSION_PATTERN, name.strip())
            if acc_match and not any(r.get("accession") == acc_match.group(1) for r in refs):
                refs.append({
                    "type": "accession",
                    "accession": acc_match.group(1),
                    "title": name,
                    "display": acc_match.group(1),
                })

    text_fields = [
        plan.get("summary_zh", ""),
        plan.get("research_question", ""),
        "\n".join(str(s.get("desc", "")) for s in plan.get("technical_roadmap", [])),
        "\n".join(str(s.get("desc", "")) for s in plan.get("innovation_points", [])),
    ]
    for text in text_fields:
        refs.extend(_parse_citations_from_text(text))

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for r in refs:
        # 去重键覆盖所有引用类型，避免 accession/author-year 引用被静默丢弃
        key = (
            r.get("doi")
            or r.get("pmid")
            or r.get("accession")
            or (f"{r.get('name')}|{r.get('year')}" if r.get("name") else "")
            or r.get("title", "")
        )
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


def _parse_citation_from_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}

    doi_match = re.search(r"(10\.\d{4,}/[^\s\"'<>，。；）)\]】]+)", text)
    if doi_match:
        result["type"] = "doi"
        result["doi"] = doi_match.group(1).rstrip(".,;:)}]，。 ）】")
        result["display"] = f"doi:{result['doi']}"

    pmid_match = re.search(r"(?:PMID|pmid)[: ]*(\d{7,8})", text)
    if pmid_match:
        result["type"] = result.get("type") or "pmid"
        result["pmid"] = pmid_match.group(1)
        result.setdefault("display", f"PMID:{result['pmid']}")

    acc_match = re.search(_ACCESSION_PATTERN, text)
    if acc_match:
        result["type"] = result.get("type") or "accession"
        result["accession"] = acc_match.group(1)
        result.setdefault("display", result["accession"])

    return result


def _parse_citations_from_text(text: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []

    dois = re.findall(r"(10\.\d{4,}/[^\s\"'<>，。；）)\]】]+)", text)
    for doi in dois:
        clean = doi.rstrip(".,;:)}]，。 ）】")
        if clean:
            refs.append({"type": "doi", "doi": clean, "display": f"doi:{clean}"})

    pmids = re.findall(r"(?:PMID|pmid)[: ]*(\d{7,8})", text)
    for pmid in pmids:
        refs.append({"type": "pmid", "pmid": pmid, "display": f"PMID:{pmid}"})

    for acc in re.findall(_ACCESSION_PATTERN, text):
        refs.append({"type": "accession", "accession": acc, "display": acc})

    author_year = re.findall(r'([A-Z][a-z]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][a-z]+))?),\s*(\d{4})', text)
    if not author_year:
        author_year = re.findall(r'\(([^)]{3,40}),\s*(\d{4})\)', text)
    for name_part, year in author_year:
        name = name_part.strip()
        refs.append({
            "type": "author_year",
            "name": name,
            "year": year,
            "display": f"{name}, {year}",
        })

    return refs
