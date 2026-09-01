from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from shared.core.llm_client import llm_complete
from shared.core.logging_setup import get_logger

from scripts.p05_harness.domain_prompts import get_prompts
from scripts.p05_harness.mcp.search_engine import SearchEngine

logger = get_logger("p05_harness.redteam")

Severity = Literal["high", "medium", "low"]


@dataclass
class RedTeamFinding:
    check: str
    severity: Severity
    detail: str
    suggestion: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class RedTeamOutput:
    findings: list[RedTeamFinding] = field(default_factory=list)
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    verified_claims: list[dict[str, Any]] = field(default_factory=list)
    unverified_claims: list[dict[str, Any]] = field(default_factory=list)


def _get_redteam_system() -> str:
    return get_prompts().redteam_system


CLAIM_VERIFY_SYSTEM = """你是一个严谨的事实核查专家。你的任务是检查研究方案中的数据相关事实声明，并标记其可信度。

检查以下类型的声明：
1. 数据集规模（如"包含XXX个细胞"）
2. 数据集覆盖范围（如"覆盖XXX个数据集"）
3. 模型/工具可用性（如"XX模型已开源/已发布权重"）
4. 数据源URL/accession

对每个声明标记：
- **verified**：该声明在已有证据（证据卡、检索文献、公开数据源说明）中有明确支撑
- **unverified**：该声明无法在已有证据中找到支撑，可能为LLM幻觉
- **partially_verified**：部分信息有支撑，但关键数据点无对应证据

输出严格的JSON格式，不带markdown代码块标记。"""


async def run_redteam(
    plan: dict[str, Any],
    candidate: dict[str, Any],
    search_engine: SearchEngine | None = None,
    evidence_cards: list[dict[str, Any]] | None = None,
    novelty_papers: list[dict[str, Any]] | None = None,
) -> RedTeamOutput:
    """Phase 1.6: 方法论红队评审 —— 对方案的方法论严谨性做系统性攻击。

    复用 Phase 1.5 的对抗性检索结果以避免重复搜索。
    """
    candidate_id = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
    output = RedTeamOutput()

    # 步骤 A: 方法论四维度评审（LLM，不需工具）
    methodology_findings = await _methodology_review(plan, candidate, novelty_papers or [])
    output.findings = methodology_findings
    output.high_count = sum(1 for f in methodology_findings if f.severity == "high")
    output.medium_count = sum(1 for f in methodology_findings if f.severity == "medium")
    output.low_count = sum(1 for f in methodology_findings if f.severity == "low")
    logger.info(
        f"[RedTeam] {candidate_id}: {len(methodology_findings)} findings "
        f"({output.high_count}H/{output.medium_count}M/{output.low_count}L)"
    )

    # 步骤 B: 数据事实核查（证据卡 + MCP 验证）
    verified, unverified = await _verify_data_claims(
        plan, candidate, search_engine, evidence_cards or []
    )
    output.verified_claims = verified
    output.unverified_claims = unverified
    logger.info(
        f"[RedTeam] {candidate_id}: {len(verified)} verified / {len(unverified)} unverified data claims"
    )

    return output


async def _methodology_review(
    plan: dict[str, Any],
    candidate: dict[str, Any],
    novelty_papers: list[dict[str, Any]],
) -> list[RedTeamFinding]:
    """LLM 对方案做四维度方法论评审。"""
    candidate_id = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
    summary = plan.get("summary_zh", "")[:800]
    roadmap = plan.get("technical_roadmap", [])
    roadmap_text = ""
    if roadmap:
        roadmap_text = "\n".join(
            f"步骤{i+1}. {s.get('step_name', '')}：{s.get('desc', '')[:200]}"
            for i, s in enumerate(roadmap[:5])
        )
    data_sources = plan.get("data_sources_detail", [])
    ds_text = ""
    if data_sources:
        for ds in data_sources[:8]:
            if isinstance(ds, dict):
                ds_text += f"- {ds.get('name', '?')}: {ds.get('url', '?')}\n"

    baseline_text = plan.get("baseline_methods", "")
    if not baseline_text:
        feasibility = plan.get("feasibility", {})
        if isinstance(feasibility, dict):
            baseline_text = json.dumps(feasibility, ensure_ascii=False)
    else:
        baseline_text = str(baseline_text)[:500]

    novelty_text = ""
    if novelty_papers:
        novelty_text = "\n".join(
            f"- {p.get('title', 'N/A')} ({p.get('year', '')}) {str(p.get('abstract', ''))[:150]}"
            for p in novelty_papers[:10]
        )

    domain = get_prompts().domain_name
    prompt = f"""请对以下{domain}研究方案进行系统性方法论红队评审。

## 研究方案摘要
{summary}

## 技术路线
{roadmap_text}

## 数据源
{ds_text}

## 基线方案
{baseline_text}

## 新颖性检索到的已有工作（供参考）
{novelty_text}

## 评审要求

从以下四个维度逐一检查，每个发现给出严重程度:

1. **数据泄漏风险**
   - 评测集与预训练语料是否可能重叠？
   - 使用了持续更新资源（CELLxGENE/HCA等）时，是否指定快照版本？
   - 数据集划分（train/val/test）是否合理？

2. **反馈信号有效性**
   - 方案中声称的学习信号（奖励/损失）在部署时是否实际可得？
   - 是否存在先用标签指导选择、再用选择预测标签的循环矛盾？
   - 如果方案涉及在线学习/主动学习，真值获取是否可行？

3. **基线充分性**
   - 是否包含 oracle/上界、随机基线、全局最优固定模型、简单启发式？
   - 缺失任何一类即记录

4. **可复现性**
   - 数据版本/accession/快照日期是否明确？
   - 声称使用的模型权重是否可公开获取？
   - 超参数、训练配置是否完整？

## 输出格式
[
  {{
    "check": "检查维度名称（如 data_leakage, feedback_validity, baseline_adequacy, reproducibility）",
    "severity": "high|medium|low",
    "detail": "问题详细描述（中文，2-5句）",
    "suggestion": "改进建议（中文，1-3句）",
    "evidence": ["指向方案中具体字段或段落"]
  }}
]

如果没有发现问题，返回空数组。只输出JSON数组。"""

    try:
        raw = await llm_complete(prompt, system=_get_redteam_system(), temperature=0.3, max_tokens=4000)
        data = _parse_json_response(raw)
        findings: list[RedTeamFinding] = []
        if isinstance(data, list):
            for item in data:
                sev_raw = str(item.get("severity", "low")).lower()
                sev: Severity = "high" if "high" in sev_raw else ("medium" if "medium" in sev_raw else "low")
                findings.append(RedTeamFinding(
                    check=str(item.get("check", "")),
                    severity=sev,
                    detail=str(item.get("detail", "")),
                    suggestion=str(item.get("suggestion", "")),
                    evidence=item.get("evidence", []),
                ))
        return findings
    except Exception as e:
        logger.warning(f"[RedTeam-method] {candidate_id}: review failed: {e}")
        return []


async def _verify_data_claims(
    plan: dict[str, Any],
    candidate: dict[str, Any],
    search_engine: SearchEngine | None,
    evidence_cards: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """核查方案中的数据事实声明（规模、模型可用性等）。

    Returns:
        (verified_claims, unverified_claims)
    """
    claims = _extract_data_claims(plan)
    if not claims:
        return [], []

    # 从证据卡和公开数据源构建"已知事实"上下文
    known_facts = _build_known_facts(evidence_cards)

    candidate_id = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
    verified: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []

    for claim in claims:
        # 先尝试用已知事实匹配
        if _match_known_fact(claim, known_facts):
            claim["status"] = "verified"
            claim["evidence_source"] = "evidence_card"
            verified.append(claim)
            continue

        # 用 MCP 搜索验证（如有 search_engine 且声明含具体标识符）
        if search_engine and claim.get("identifiers"):
            mcp_result = await _mcp_fact_check(claim, search_engine)
            if mcp_result["verified"]:
                claim["status"] = "verified"
                claim["evidence_source"] = mcp_result.get("source", "mcp")
                claim["mcp_evidence"] = mcp_result.get("evidence", "")
                verified.append(claim)
                continue

        claim["status"] = "unverified"
        unverified.append(claim)

    logger.debug(
        f"[RedTeam-verify] {candidate_id}: {len(verified)} verified, "
        f"{len(unverified)} unverified out of {len(claims)} claims"
    )
    return verified, unverified


def _extract_data_claims(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """从方案文本中提取数据相关的声明。"""
    claims: list[dict[str, Any]] = []

    # 规模声明模式："包含XX个细胞", "XX个数据集", "XX million"
    size_patterns = [
        (re.compile(r'(\d[\d,.]*[万千万亿]?\s*(?:个|条|份|张)?\s*(?:细胞|数据集|样本|基因|蛋白|scFM))'), "scale"),
        (re.compile(r'(\d[\d,.]*\s*(?:million|thousand|billion)\s*(?:cells|datasets|samples))', re.IGNORECASE), "scale"),
        (re.compile(r'覆盖\s*(\d[\d,.]*[万千万亿]?\s*[个份]?\s*(?:细胞|数据集|组织))'), "coverage"),
    ]

    text_fields = [
        ("summary_zh", plan.get("summary_zh", "")),
        ("data_sources_detail", "\n".join(
            str(ds.get("name", "")) + " " + str(ds.get("desc", ""))
            for ds in plan.get("data_sources_detail", []) if isinstance(ds, dict)
        )),
    ]
    for field_name, text in text_fields:
        for pattern, claim_type in size_patterns:
            for m in pattern.finditer(text):
                claims.append({
                    "claim_text": m.group(0),
                    "claim_type": claim_type,
                    "source_field": field_name,
                    "status": "unverified",
                    "identifiers": [],
                })

    # 数据源 URL/accession 声明
    data_sources = plan.get("data_sources_detail", [])
    for ds in data_sources:
        if isinstance(ds, dict):
            url = ds.get("url", "")
            name = ds.get("name", "")
            identifiers = _extract_identifiers(url)
            if name or url:
                claims.append({
                    "claim_text": f"{name}: {url}" if name else url,
                    "claim_type": "data_source",
                    "source_field": "data_sources_detail",
                    "status": "unverified",
                    "identifiers": identifiers,
                })

    return claims


def _extract_identifiers(text: str) -> list[str]:
    """从文本中提取 DOI/GSE/PMID/GitHub URL 等标识符。"""
    ids: list[str] = []
    doi_match = re.search(r"(10\.\d{4,}/[^\s\"'<>，。；）)\]】]+)", text)
    if doi_match:
        ids.append(doi_match.group(1).rstrip(".,;:)}]，。 ）】"))
    gse_match = re.search(r"((?:GSE|GDS|E-[A-Z]{2,5}-)\d{3,})", text)
    if gse_match:
        ids.append(gse_match.group(0))
    pmid_match = re.search(r"(?:PMID|pmid)[: ]*(\d{7,8})", text)
    if pmid_match:
        ids.append(pmid_match.group(1))
    gh_match = re.search(r"(github\.com/[\w.-]+/[\w.-]+)", text, re.IGNORECASE)
    if gh_match:
        ids.append(gh_match.group(0))
    return ids


def _build_known_facts(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从证据卡中构建已知事实索引。"""
    facts: list[dict[str, Any]] = []
    for card in cards:
        title = card.get("paper_title", "")
        doi = card.get("paper_doi", "")
        pmid = card.get("paper_pmid", "")
        abstract = card.get("paper_abstract", "")
        keywords = card.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",")]
        facts.append({
            "title": title,
            "doi": str(doi).lower() if doi else "",
            "pmid": str(pmid) if pmid else "",
            "abstract": str(abstract or "")[:500],
            "keywords": [str(k).lower() for k in keywords],
        })
    return facts


def _match_known_fact(claim: dict[str, Any], known_facts: list[dict[str, Any]]) -> bool:
    """检查声明是否被证据卡中的已知事实支撑。"""
    ids = claim.get("identifiers", [])
    claim_text = claim.get("claim_text", "").lower()

    for fact in known_facts:
        for id_val in ids:
            if id_val.lower() in fact["doi"] or id_val in fact["pmid"]:
                return True

        # 数值类声明的模糊匹配（如"36M细胞"出现在证据卡摘要中）
        claim_vals = re.findall(r'\d+\.?\d*', claim_text)
        if claim_vals:
            for val in claim_vals:
                if val in fact["abstract"].lower():
                    return True
                if val in fact["title"].lower():
                    return True

    return False


async def _mcp_fact_check(claim: dict[str, Any], search_engine: SearchEngine) -> dict[str, Any]:
    """用 MCP 搜索验证数据声明。"""
    result = {"verified": False, "source": "", "evidence": ""}
    identifiers = claim.get("identifiers", [])

    for id_val in identifiers:
        if id_val.startswith("10."):
            verified = await search_engine.verify_doi(id_val)
            if verified:
                result["verified"] = True
                result["source"] = "crossref"
                result["evidence"] = json.dumps(verified, ensure_ascii=False)
                return result
        if id_val.isdigit() and 7 <= len(id_val) <= 8:
            verified = await search_engine.verify_pmid(id_val)
            if verified:
                result["verified"] = True
                result["source"] = "pubmed"
                result["evidence"] = json.dumps(verified, ensure_ascii=False)
                return result

    return result


def format_redteam_warnings(output: RedTeamOutput) -> str:
    """将红队评审结果格式化为警告文本，注入到 critique 上下文中。"""
    if not output.findings:
        return ""

    lines = ["## 方法论红队评审结果（Phase 1.6）"]

    if output.high_count > 0:
        lines.append(f"\n### 高风险问题 ({output.high_count})")
        for f in output.findings:
            if f.severity == "high":
                lines.append(f"\n- **[{f.check}]** {f.detail}")
                lines.append(f"  建议: {f.suggestion}")

    if output.medium_count > 0:
        lines.append(f"\n### 中风险问题 ({output.medium_count})")
        for f in output.findings:
            if f.severity == "medium":
                lines.append(f"\n- **[{f.check}]** {f.detail}")
                lines.append(f"  建议: {f.suggestion}")

    if output.unverified_claims:
        lines.append(f"\n### 未核实的数据声明 ({len(output.unverified_claims)})")
        for c in output.unverified_claims[:5]:
            lines.append(f"  - [待核实] {c['claim_text']}")

    return "\n".join(lines)


def _parse_json_response(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) > 2:
            text = "\n".join(lines[1:-1])
    return json.loads(text)
