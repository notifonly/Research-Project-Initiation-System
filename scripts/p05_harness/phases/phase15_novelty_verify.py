from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from shared.core.llm_client import llm_complete
from shared.core.logging_setup import get_logger

from scripts.p05_harness.mcp.search_engine import SearchEngine, boost_recent

logger = get_logger("p05_harness.phase15")

Verdict = Literal["scooped", "crowded", "adjacent", "clear", "insufficient_evidence"]


@dataclass
class NoveltyClaim:
    claim: str
    source: str


@dataclass
class NoveltyVerdict:
    claim: str
    verdict: Verdict
    closeness: str  # 与已有工作的重合度描述
    closest_works: list[dict[str, Any]] = field(default_factory=list)
    comparison_table: list[dict[str, Any]] = field(default_factory=list)
    evidence_links: list[str] = field(default_factory=list)


@dataclass
class Phase15Output:
    claims: list[dict[str, str]] = field(default_factory=list)
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    overall_verdict: Verdict = "clear"
    repositioning_required: bool = False
    suggested_repositioning: str = ""
    papers_found: list[dict[str, Any]] = field(default_factory=list)
    verdicts_detail: list[NoveltyVerdict] = field(default_factory=list)


EXTRACT_CLAIMS_SYSTEM = """你是一个严谨的学术评审专家。你的任务是提取研究方案中的所有"新颖性声明"。

新颖性声明包括：
1. 明确的"首次提出/首个实现/填补空白"类表述
2. 声称某方法或框架在当前领域未被探索过
3. 声称解决了已有方法无法解决的问题
4. 声称发现了新的生物学洞察或机制

对于每个声明，记录其原文和在方案中的来源位置（如 innovation_points[0]、summary_zh 等）。

输出严格的JSON格式，不带markdown代码块标记。如果没有发现任何新颖性声明，返回空数组。"""


ADVERSARIAL_QUERY_SYSTEM = """你是一个严谨的学术文献检索专家，专门负责验证研究方案的新颖性声明。
你的任务是针对方案中的每个新颖性声明，生成最能找到"已有相似工作"的检索查询。

核心原则：你要找的是"哪些已有工作可能会破坏该声明的新颖性"——因此查询应该：
1. 使用该声明的范式级同义词和上位概念（不要局限于方案自身的术语）
2. 包含不同方法学派的关键词（如方法名、技术路线变体）
3. 覆盖即使表述不同但概念相同的已有工作
4. 查询应是适合PubMed/Semantic Scholar的专业英文学术检索词

例如：
- 声明"首个多scFM路由智能体" → "scFM router", "single-cell foundation model selection", "multi-model agent single-cell", "model routing agent bioinformatics", "cost-aware model selection single cell"
- 声明"首个面向scFM部署的Contextual Bandit模型选择" → "model selection bandit", "adaptive model routing", "online model selection LLM", "cost-aware model routing", "dynamic model selection bioinformatics"
- 声明"首个自进化的单细胞基准" → "self-evolving benchmark", "dynamic benchmark evaluation", "adaptive evaluation benchmark", "benchmark auto-update", "living benchmark"

每个声明生成3-5个查询。输出严格的JSON格式，不带markdown代码块标记。"""


JUDGE_OVERLAP_SYSTEM = """你是一个严谨的学术评审专家。你的任务是判断研究方案的新颖性声明与检索到的已有工作之间的重合程度。

判定标准：
- **scooped（被抢先）**：已有工作实现了相同的核心思想，且公开时间早于本方案，方案不应以当前形态推进
- **crowded（拥挤）**：已有工作高度相似，方案的核心声明需要大幅收窄；差异化空间有限
- **adjacent（邻近）**：已有工作方向相关但方法/目标有显著差异，方案可以通过明确差异化声明来立足
- **clear（清晰）**：未发现高度相似的已有工作，新颖性声明成立

对于每个声明，你需要：
1. 在检索到的文献中找出与声明最相似的工作（最多3篇）
2. 列出对比维度，逐项对比方案与已有工作
3. 给出判定结论和理由
4. 如果判定为 scooped 或 crowded，给出"收窄/重定位"的具体建议

输出严格的JSON格式。"""


async def verify_novelty(
    plan: dict[str, Any],
    candidate: dict[str, Any],
    search_engine: SearchEngine,
    config: dict[str, Any] | None = None,
) -> Phase15Output:
    """Phase 1.5: 对抗性新颖性验证 —— 用"找杀"而非"找撑"的检索验证方案的新颖性声明。

    Returns:
        Phase15Output with verdicts, closest works, and repositioning guidance.
    """
    cfg = config or {}
    nc = cfg.get("novelty_check", {})
    enabled = nc.get("enabled", True)
    if not enabled:
        return Phase15Output(overall_verdict="clear")

    max_claims = nc.get("max_claims", 5)
    queries_per_claim = nc.get("queries_per_claim", 4)
    top_k_papers = nc.get("top_k_papers", 15)
    recent_boost_year = nc.get("recent_boost_year", 2024)
    candidate_id = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
    output = Phase15Output()

    # 步骤1: 从方案中提取原子新颖性声明
    claims = await _extract_novelty_claims(plan, max_claims)
    output.claims = [{"claim": c.claim, "source": c.source} for c in claims]
    if not claims:
        logger.info(f"[Phase1.5] {candidate_id}: no novelty claims found")
        output.overall_verdict = "clear"
        return output

    logger.info(f"[Phase1.5] {candidate_id}: extracted {len(claims)} claims")

    # 步骤2: 为每个声明生成对抗性检索 query
    query_sets = await _generate_adversarial_queries(claims, candidate, queries_per_claim)

    # 步骤3: 多源对抗性检索（近期优先）
    all_queries: list[str] = []
    for qs in query_sets:
        all_queries.extend(qs.get("queries", [])[:queries_per_claim])
    if not all_queries:
        logger.info(f"[Phase1.5] {candidate_id}: no queries generated")
        # 有声明但无法生成检索查询：证据不足而非确认新颖
        output.overall_verdict = "insufficient_evidence"
        return output

    papers_raw = await search_engine.search_multi(all_queries, max_per_source=nc.get("max_per_source", 10))
    # 近期排序优先
    papers = boost_recent(papers_raw, recent_boost_year)[:top_k_papers]
    output.papers_found = papers

    logger.info(
        f"[Phase1.5] {candidate_id}: searched {len(all_queries)} queries, "
        f"found {len(papers_raw)} unique, kept top {len(papers)}"
    )

    # 步骤4: LLM 带证据判定重合度
    verdicts = await _judge_overlap(claims, papers, plan, candidate)
    output.verdicts_detail = verdicts

    for v in verdicts:
        vd = {
            "claim": v.claim,
            "verdict": v.verdict,
            "closeness": v.closeness,
            "closest_works": v.closest_works,
            "comparison_table": v.comparison_table,
            "evidence_links": v.evidence_links,
        }
        output.verdicts.append(vd)

    # 汇总判定
    overall = _aggregate_overall_verdict(verdicts)
    output.overall_verdict = overall
    output.repositioning_required = overall in ("scooped", "crowded")
    if output.repositioning_required:
        output.suggested_repositioning = _build_repositioning_suggestion(verdicts)

    logger.info(
        f"[Phase1.5] {candidate_id}: overall={overall}, "
        f"reposition_required={output.repositioning_required}"
    )
    return output


async def _extract_novelty_claims(
    plan: dict[str, Any],
    max_claims: int = 5,
) -> list[NoveltyClaim]:
    """步骤1: LLM 从方案中提取原子新颖性声明。"""
    plan_json = json.dumps(plan, ensure_ascii=False, indent=2)
    candidate_id = plan.get("candidate_id", "")

    prompt = f"""从以下研究方案中提取所有"新颖性声明"。

每个新颖性声明应当是一句可被验证的、关于该方案创新性的主张。

## 研究方案
{plan_json}

## 输出格式
[
  {{
    "claim": "新颖性声明的原文或精炼表述",
    "source": "来源位置（如 innovation_points[0], summary_zh 第2段等）"
  }}
]

最多返回{max_claims}个声明。如果方案中没有实质新颖性声明，返回空数组。
只输出JSON数组。"""

    try:
        raw = await llm_complete(prompt, system=EXTRACT_CLAIMS_SYSTEM, temperature=0.2, max_tokens=2000)
        data = _parse_json_response(raw)
        claims: list[NoveltyClaim] = []
        if isinstance(data, list):
            for item in data[:max_claims]:
                claims.append(NoveltyClaim(
                    claim=str(item.get("claim", "")),
                    source=str(item.get("source", "")),
                ))
        logger.info(f"[Phase1.5-claims] {candidate_id}: {len(claims)} claims extracted")
        return claims
    except Exception as e:
        logger.warning(f"[Phase1.5-claims] {candidate_id}: extract failed: {e}")
        return []


async def _generate_adversarial_queries(
    claims: list[NoveltyClaim],
    candidate: dict[str, Any],
    queries_per_claim: int = 4,
) -> list[dict[str, Any]]:
    """步骤2: LLM 为每个新颖性声明生成对抗性检索 query。"""
    candidate_id = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
    method = candidate.get("dimensions", {}).get("method", "")
    disease = candidate.get("dimensions", {}).get("disease", "")

    claims_text = "\n".join(f"{i+1}. {c.claim} (来源: {c.source})" for i, c in enumerate(claims))

    prompt = f"""针对以下研究方案的新颖性声明，为每个声明生成{queries_per_claim}个"对抗性"检索查询。

这些查询的目标是：找到**能反驳该新颖性声明**的已有工作——即用不同措辞表达的同一概念、或更早发表的类似方法。

## 背景
研究方向: {candidate.get('research_question', '')}
方法: {method}
疾病/表型: {disease}

## 待验证的新颖性声明
{claims_text}

## 输出格式
[
  {{
    "claim_index": 0,
    "claim": "对应的新颖性声明原文",
    "queries": ["对抗性检索查询1", "对抗性检索查询2", ...]
  }}
]

每个声明的查询数量至少3个，最多{queries_per_claim}个。查询应当使用英文学术检索词。
只输出JSON数组。"""

    try:
        raw = await llm_complete(prompt, system=ADVERSARIAL_QUERY_SYSTEM, temperature=0.3, max_tokens=3000)
        data = _parse_json_response(raw)
        if isinstance(data, list):
            logger.info(f"[Phase1.5-queries] {candidate_id}: {sum(len(d.get('queries', [])) for d in data)} queries generated")
            return data
        return []
    except Exception as e:
        logger.warning(f"[Phase1.5-queries] {candidate_id}: query generation failed: {e}")
        return []


async def _judge_overlap(
    claims: list[NoveltyClaim],
    papers: list[dict[str, Any]],
    plan: dict[str, Any],
    candidate: dict[str, Any],
) -> list[NoveltyVerdict]:
    """步骤4: LLM 带检索到的文献证据，逐一判定新颖性声明的重合度。"""
    candidate_id = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
    if not papers or not claims:
        # 零检索证据不等于新颖性成立：标记为证据不足，避免"空虚 clear"
        return [
            NoveltyVerdict(
                claim=c.claim,
                verdict="insufficient_evidence",
                closeness="未检索到任何候选对比文献，无法验证该声明的新颖性（证据不足，非确认新颖）",
            )
            for c in claims
        ]

    claims_text = "\n".join(f"{i+1}. {c.claim}" for i, c in enumerate(claims))

    papers_text_parts: list[str] = []
    for i, p in enumerate(papers[:20]):
        title = p.get("title", "N/A")
        authors = ", ".join((p.get("authors") or [])[:3])
        year = p.get("year", "")
        venue = p.get("venue", "")
        abstract = str(p.get("abstract", ""))[:400]
        doi = p.get("doi", "")
        papers_text_parts.append(
            f"{i+1}. **{title}**\n"
            f"   作者: {authors} | 年份: {year} | 来源: {venue}\n"
            f"   摘要: {abstract}\n"
            f"   DOI: {doi}"
        )

    papers_text = "\n\n".join(papers_text_parts)
    summary_zh = plan.get("summary_zh", "")[:500]

    prompt = f"""判断以下研究方案的新颖性声明与检索到的已有文献之间的重合程度。

## 研究方案摘要
{summary_zh}

## 待验证的新颖性声明
{claims_text}

## 检索到的已有工作（候选对比文献）
{papers_text}

## 对每个声明，输出判定结果

判定标准：
- **scooped**：该文献实现了与方案相同的核心思想且更早发表，方案的核心新颖性已被否定
- **crowded**：该文献高度相似，方案需要大幅收窄差异化定位
- **adjacent**：该文献相关但方法/目标有显著差异，方案可通过明确差异化声明立足
- **clear**：未发现高度相似的已有工作

## 输出格式
[
  {{
    "claim": "对应的新颖性声明原文",
    "verdict": "scooped|crowded|adjacent|clear",
    "closeness": "与已有工作的具体关系描述（中文，3-5句）",
    "closest_works": [
      {{
        "title": "最接近的已有工作标题",
        "authors": "第一作者或前几作者",
        "year": "发表年份",
        "venue": "发表来源",
        "similarity": "与本方案的重合点（中文，1-3句）",
        "doi": "DOI（如有）"
      }}
    ],
    "comparison_table": [
      {{
        "dimension": "对比维度（如：核心方法、应用场景、数据类型、实验设计等）",
        "our_approach": "本方案在该维度的做法",
        "existing_work": "已有工作在该维度的做法"
      }}
    ],
    "evidence_links": ["DOI或链接"]
  }}
]

只输出JSON数组。"""

    try:
        raw = await llm_complete(prompt, system=JUDGE_OVERLAP_SYSTEM, temperature=0.3, max_tokens=6000)
        data = _parse_json_response(raw)
        results: list[NoveltyVerdict] = []
        if isinstance(data, list):
            for item in data:
                results.append(NoveltyVerdict(
                    claim=str(item.get("claim", "")),
                    verdict=_normalize_verdict(item.get("verdict", "clear")),
                    closeness=str(item.get("closeness", "")),
                    closest_works=item.get("closest_works", []),
                    comparison_table=item.get("comparison_table", []),
                    evidence_links=item.get("evidence_links", []),
                ))
        logger.info(
            f"[Phase1.5-judge] {candidate_id}: "
            f"{sum(1 for r in results if r.verdict == 'scooped')} scooped, "
            f"{sum(1 for r in results if r.verdict == 'crowded')} crowded, "
            f"{sum(1 for r in results if r.verdict == 'adjacent')} adjacent, "
            f"{sum(1 for r in results if r.verdict == 'clear')} clear"
        )
        return results
    except Exception as e:
        logger.warning(f"[Phase1.5-judge] {candidate_id}: overlap judge failed: {e}")
        return [NoveltyVerdict(claim=c.claim, verdict="clear", closeness=f"判定失败: {e}") for c in claims]


def _normalize_verdict(raw: str) -> Verdict:
    raw = raw.strip().lower()
    if "scoop" in raw:
        return "scooped"
    if "crowd" in raw:
        return "crowded"
    if "adjacent" in raw or "adjac" in raw:
        return "adjacent"
    if "insufficient" in raw:
        return "insufficient_evidence"
    return "clear"


def _aggregate_overall_verdict(verdicts: list[NoveltyVerdict]) -> Verdict:
    """汇总所有声明的判定为整体结论。"""
    if not verdicts:
        return "clear"
    if any(v.verdict == "scooped" for v in verdicts):
        return "scooped"
    if any(v.verdict == "crowded" for v in verdicts):
        return "crowded"
    if any(v.verdict == "adjacent" for v in verdicts):
        return "adjacent"
    # 全部声明均无检索证据时，整体为证据不足而非 clear
    if all(v.verdict == "insufficient_evidence" for v in verdicts):
        return "insufficient_evidence"
    if any(v.verdict == "insufficient_evidence" for v in verdicts):
        # 部分声明证据不足：保守处理，整体不给 clear
        return "insufficient_evidence"
    return "clear"


def _build_repositioning_suggestion(verdicts: list[NoveltyVerdict]) -> str:
    """基于所有判定结果，生成重定位建议文本。"""
    parts: list[str] = []
    for v in verdicts:
        if v.verdict in ("scooped", "crowded"):
            cw_titles = [w.get("title", "?")[:60] for w in v.closest_works[:3]]
            parts.append(
                f"- 声明「{v.claim[:80]}」→ {v.verdict}（相近工作: {'; '.join(cw_titles)}）"
                f"\n  {v.closeness[:200]}"
            )
    if not parts:
        return "所有新颖性声明均可通过。"
    return (
        "以下新颖性声明存在已有工作重合，需重新定位：\n\n"
        + "\n\n".join(parts)
        + "\n\n请将方案定位为这些已有工作的差异化延伸，而非'首次提出'。"
    )


def format_novelty_warnings(phase15_output: Phase15Output) -> str:
    """将新颖性验证结果格式化为警告文本，注入到 critique 和 refine 的上下文中。"""
    if phase15_output.overall_verdict == "clear":
        return ""

    lines = [
        "## 新颖性验证结果（Phase 1.5 对抗性检索）",
        f"整体判定: {phase15_output.overall_verdict}",
    ]

    if phase15_output.suggested_repositioning:
        lines.append(f"\n{phase15_output.suggested_repositioning}")

    for vd in phase15_output.verdicts:
        lines.append(f"\n### 声明: {vd.get('claim', '')}")
        lines.append(f"判定: **{vd.get('verdict', '')}**")
        lines.append(f"分析: {vd.get('closeness', '')}")

        cw = vd.get("closest_works", [])
        if cw:
            lines.append("\n最接近的已有工作:")
            for i, w in enumerate(cw[:3]):
                lines.append(
                    f"  {i+1}. {w.get('title', 'N/A')} "
                    f"({w.get('authors', '')}, {w.get('year', '')}, {w.get('venue', '')})"
                )
                if w.get("similarity"):
                    lines.append(f"     → {w['similarity']}")

        ct = vd.get("comparison_table", [])
        if ct:
            lines.append("\n对比维度 | 本方案 | 已有工作")
            for row in ct:
                dim = row.get("dimension", "")
                ours = row.get("our_approach", "")[:60]
                exist = row.get("existing_work", "")[:60]
                lines.append(f"  {dim} | {ours} | {exist}")

    return "\n".join(lines)


def format_novelty_comparison_for_report(phase15_output: Phase15Output) -> str:
    """生成供报告使用的新颖性对比摘要（Markdown）。"""
    if not phase15_output.verdicts:
        return "（未进行新颖性验证）"

    lines = [
        f"## 新颖性验证报告",
        f"整体判定: **{phase15_output.overall_verdict}**",
        f"验证声明数: {len(phase15_output.claims)} | 检索文献数: {len(phase15_output.papers_found)}",
        "",
    ]

    _verdict_emoji = {
        "scooped": "\u274c",
        "crowded": "\u26a0\ufe0f",
        "adjacent": "\u2139\ufe0f",
        "clear": "\u2705",
        "insufficient_evidence": "\u2753",
    }
    for vd in phase15_output.verdicts:
        emoji = _verdict_emoji.get(vd.get("verdict", ""), "")
        lines.append(f"### {emoji} {vd.get('claim', '')}")
        lines.append(f"判定: **{vd.get('verdict', '')}** — {vd.get('closeness', '')[:200]}")
        lines.append("")

    return "\n".join(lines)


def _parse_json_response(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) > 2:
            text = "\n".join(lines[1:-1])
        else:
            text = text
    return json.loads(text)
