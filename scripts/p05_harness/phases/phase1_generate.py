from __future__ import annotations

import json
from typing import Any

from shared.core.llm_client import llm_complete
from shared.core.logging_setup import get_logger

from scripts.p05_harness.mcp.search_engine import SearchEngine

from scripts.p05_harness.domain_prompts import get_prompts

logger = get_logger("p05_harness.phase1")

# Deprecated: kept for backward compatibility. Use domain_prompts.get_prompts().generate_system instead.
GENERATE_SYSTEM = get_prompts().generate_system


async def generate_initial_plan(
    candidate: dict[str, Any],
    evidence_cards: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    mcp_context: str = "",
) -> dict[str, Any]:
    """Phase 1: Generate initial research plan with optional MCP search context."""
    candidate_id = candidate.get("topic_id", candidate.get("research_id", candidate.get("id", "")))
    rq = candidate.get("research_question", "")
    dims = candidate.get("dimensions", {})
    scores = candidate.get("scores", {})
    rationale = candidate.get("rationale", "")

    cards_summary = _summarize_evidence_cards(evidence_cards)
    gaps_summary = _summarize_gaps(gaps)
    hyp_summary = _summarize_hypotheses(hypotheses)

    dims_text = json.dumps(dims, ensure_ascii=False, indent=2)
    scores_text = json.dumps(scores, ensure_ascii=False, indent=2)

    prompt = f"""请为以下候选研究方向生成完整的研究方案。

## 研究方向
研究问题: {rq}

## 维度信息
{dims_text}

## 现有评分
{scores_text}

## 已有分析
{rationale}

## 关联证据卡 (从已有文献中提取)
{cards_summary}

## 关联研究缺口
{gaps_summary}

## 关联研究假设
{hyp_summary}

{f"## MCP搜索补充文献{mcp_context}" if mcp_context else ""}

## 输出要求

请输出以下JSON结构的研究方案:

{{
  "candidate_id": "{candidate_id}",
  "summary_zh": "300-500字中文摘要，概述研究问题、方法、预期成果",
  "technical_roadmap": [
    {{
      "step": 1,
      "title": "阶段标题（中文）",
      "desc": "详细描述（200-300字），说明具体做什么",
      "methods": "具体使用的方法/模型/工具（如 scGPT fine-tuning with LoRA, Bayesian hyperparameter optimization via Optuna）",
      "weeks": 4,
      "tools": ["scGPT", "scanpy", "scvi-tools"],
      "expected_output": "该阶段的预期产出"
    }}
  ],
  "data_sources_detail": [
    {{
      "name": "数据集名称",
      "access": "公开/需申请/需合作",
      "format": "h5ad / fastq / csv",
      "size": "样本量和细胞数",
      "url": "GEO/SRA/ArrayExpress accession 或下载链接",
      "note": "预处理说明和数据质量评估"
    }}
  ],
  "feasibility": {{
    "data_accessibility": {{
      "score": 整数0-100,
      "reason": "评估理由（中文，50-100字）"
    }},
    "compute_requirements": {{
      "gpu_hours": "预估GPU小时数",
      "platform": "推荐平台（AWS/GCP/本地集群）",
      "pretrained_available": true/false,
      "reason": "评估理由"
    }},
    "technical_difficulty": {{
      "score": 整数0-100,
      "level": "低/中等/高/极高",
      "reason": "评估理由"
    }},
    "timeline_months": 整数,
    "key_risks": ["具体风险1", "具体风险2", "具体风险3"],
    "mitigation": ["对应缓解措施1", "对应缓解措施2", "对应缓解措施3"]
  }},
  "innovation_points": [
    {{
      "claim": "创新点1的简述（中文，1句）",
      "closest_existing_work": "最接近的已有工作（标题+作者年份），如无可填\"未检索到\"",
      "difference": "与已有工作的具体区别（中文，1-3句）",
      "evidence_refs": ["DOI或引用文献1", "DOI或引用文献2"]
    }},
    {{
      "claim": "创新点2",
      "closest_existing_work": "...",
      "difference": "...",
      "evidence_refs": [...]
    }}
  ],
  "expected_outputs": [
    "预期产出1：如 benchmark dataset, 预训练模型, 评测报告",
    "预期产出2",
    "预期产出3"
  ],
  "target_venues": ["Nature Methods", "Genome Biology", "Cell Systems"]
}}

只输出JSON。"""

    try:
        raw = await llm_complete(prompt, system=get_prompts().generate_system, temperature=0.4, max_tokens=8000)
        plan = _parse_json_response(raw)
        plan = _normalize_innovation_points(plan)
        plan["candidate_id"] = candidate_id
        logger.info(f"[Phase1] Generated plan for {candidate_id}")
        return plan
    except Exception as e:
        logger.error(f"[Phase1] Failed for {candidate_id}: {e}")
        return _fallback_plan(candidate_id, rq)


def _normalize_innovation_points(plan: dict[str, Any]) -> dict[str, Any]:
    """向后兼容：将字符串 innovation_points 转为结构化对象。"""
    points = plan.get("innovation_points", [])
    if not points:
        return plan
    normalized: list[dict[str, Any]] = []
    for p in points:
        if isinstance(p, str):
            normalized.append({
                "claim": p,
                "closest_existing_work": "",
                "difference": "",
                "evidence_refs": [],
            })
        elif isinstance(p, dict):
            normalized.append({
                "claim": p.get("claim", str(p)),
                "closest_existing_work": p.get("closest_existing_work", ""),
                "difference": p.get("difference", ""),
                "evidence_refs": p.get("evidence_refs", []),
            })
    plan["innovation_points"] = normalized
    return plan


ADVERSARIAL_PHASE0_SYSTEM = """你是一个严谨的学术评审专家。你的任务是为候选研究方向生成"挑战性"检索查询。

这些查询的目标是找出可能破坏该研究方向新颖性的已有工作——用不同术语描述的同一概念、或更早发表的类似方法。
查询应当使用英文学术检索词，适合PubMed/Semantic Scholar/bioRxiv。"""


async def enrich_context_with_mcp(
    candidate: dict[str, Any],
    search_engine: SearchEngine,
) -> str:
    """Phase 0: 支持性检索 + 对抗性检索 + LLM 总结。

    支持性检索：用候选方向自身的术语检索
    对抗性检索：用范式级同义词和上位概念检索可能挑战新颖性的已有工作
    合并去重后，LLM 总结文献（区分支持性 vs 挑战性）。
    """
    search_query = candidate.get("search_query", "")
    rq = candidate.get("research_question", "")
    method = candidate.get("dimensions", {}).get("method", "")
    disease = candidate.get("dimensions", {}).get("disease", "") or candidate.get(
        "dimensions", {}
    ).get("disease_phenotype", "")
    if isinstance(disease, dict):
        disease = disease.get("name", str(disease))

    supportive_queries = [q for q in [search_query, rq] if q]
    if not supportive_queries:
        return ""

    try:
        supportive_papers = await search_engine.search_multi(supportive_queries, max_per_source=5)

        # 对抗性检索：生成挑战性 query 并检索
        adversarial_papers: list[dict[str, Any]] = []
        try:
            adv_queries = await _generate_adversarial_phase0_queries(candidate, 4)
            if adv_queries:
                adversarial_papers = await search_engine.search_multi(adv_queries, max_per_source=5)
        except Exception as e:
            logger.debug(f"[Phase0] Adversarial query generation skipped: {e}")

        # 合并去重（Title 去重，优先保留引用数高的）
        all_papers = _merge_dedup_papers(supportive_papers, adversarial_papers)
        if not all_papers:
            return ""

        papers_text = ""
        for i, p in enumerate(all_papers[:8]):
            papers_text += f"""
{i+1}. **{p.get('title', 'N/A')}**
   作者: {', '.join((p.get('authors') or [])[:3])}
   年份: {p.get('year', 'N/A')} | 期刊: {p.get('venue', 'N/A')}
   摘要: {(p.get('abstract') or 'N/A')[:300]}
   DOI: {p.get('doi', 'N/A')} | PMID: {p.get('pmid', 'N/A')} | 引用数: {p.get('citation_count', 'N/A')}
"""

        summary_prompt = f"""请用200字中文简要总结以下论文的核心发现及其与该研究方向的竞争关系。

候选方向: {rq}
方法: {method}
疾病/表型: {disease}

文献列表:
{papers_text}

请按以下结构输出：
1. **支持性文献**: 哪些论文的方法/数据/结论可支撑或补充本方案
2. **挑战/竞争性文献**: 哪些论文提出了与本方案相近的方法或概念（如有）
3. **对方案设计的建议**（可选）：基于文献分析，本方案在设计时应如何定位或调整

如果某篇论文既是支撑又是挑战（例如用了相同方法但不同疾病场景），请在对应分类中分别提及。
只输出中文总结文字。"""

        raw = await llm_complete(summary_prompt, temperature=0.2, max_tokens=1200)
        return f"\n\n### 补充文献（MCP搜索 + 对抗性检索）\n{raw.strip()}"
    except Exception as e:
        logger.warning(f"[Phase0] MCP context enrichment failed: {e}")
        return ""


async def _generate_adversarial_phase0_queries(
    candidate: dict[str, Any],
    max_queries: int = 4,
) -> list[str]:
    """为 Phase 0 生成挑战性检索查询（轻量级，单次 LLM 调用）。"""
    rq = candidate.get("research_question", "")
    method = candidate.get("dimensions", {}).get("method", "")
    disease = candidate.get("dimensions", {}).get("disease", "") or candidate.get(
        "dimensions", {}
    ).get("disease_phenotype", "")
    if isinstance(disease, dict):
        disease = disease.get("name", str(disease))

    prompt = f"""针对以下候选研究方向，生成{max_queries}个"挑战性"检索查询。

这些查询应使用与候选方向不同的术语来表达相同/相近的概念，以找出可能已被已有工作实现的方案。

研究方向: {rq}
方法: {method}
疾病/表型: {disease}

输出JSON数组:
["查询1", "查询2", "查询3", "查询4"]

每个查询5-10个英文词，使用范式级上位概念和不同方法学派的术语。
只输出JSON数组。"""

    try:
        raw = await llm_complete(prompt, system=ADVERSARIAL_PHASE0_SYSTEM, temperature=0.3, max_tokens=500)
        data = json.loads(raw.strip())
        if isinstance(data, list):
            queries = [str(q) for q in data[:max_queries] if isinstance(q, str) and len(q) > 3]
            return queries
        return []
    except Exception as e:
        logger.debug(f"[Phase0] Adversarial query generation failed: {e}")
        return []


def _merge_dedup_papers(
    supportive: list[dict[str, Any]],
    adversarial: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Title-based dedup: 优先保留引用数高、year 新的版本。"""
    merged: dict[str, dict[str, Any]] = {}
    for p in supportive + adversarial:
        title = (p.get("title") or "").strip().lower()
        if not title:
            continue
        key = title
        if key in merged:
            existing = merged[key]
            if (p.get("citation_count") or 0) > (existing.get("citation_count") or 0):
                merged[key] = p
            if (p.get("year") or 0) > (existing.get("year") or 0):
                merged[key]["year"] = p.get("year")
        else:
            merged[key] = p
    papers = list(merged.values())
    papers.sort(key=lambda p: (p.get("citation_count") or 0), reverse=True)
    return papers


def _summarize_evidence_cards(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "无相关证据卡"
    lines = []
    for i, card in enumerate(cards[:10]):
        title = card.get("paper_title", "N/A")
        finding = card.get("key_finding", "")
        method = card.get("method_brief", "")
        doi = card.get("paper_doi", "")
        year = card.get("paper_year", "")
        lines.append(f"{i+1}. [{year}] {title}")
        if finding:
            lines.append(f"   发现: {finding[:150]}")
        if method:
            lines.append(f"   方法: {method[:100]}")
        if doi:
            lines.append(f"   DOI: {doi}")
    return "\n".join(lines)


def _summarize_gaps(gaps: list[dict[str, Any]]) -> str:
    if not gaps:
        return "无关联缺口"
    lines = []
    for g in gaps:
        gid = g.get("gap_id", "")
        desc = g.get("description", "") or g.get("gap_description", "")
        score = g.get("score", "") or g.get("gap_score", "")
        lines.append(f"- {gid} (score={score}): {desc[:200]}")
    return "\n".join(lines)


def _summarize_hypotheses(hyps: list[dict[str, Any]]) -> str:
    if not hyps:
        return "无关联假设"
    lines = []
    for h in hyps:
        hid = h.get("hypothesis_id", "")
        stmt = h.get("statement", "") or h.get("description", "")
        lines.append(f"- {hid}: {stmt[:300]}")
    return "\n".join(lines)


def _parse_json_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    return json.loads(text)


def _fallback_plan(candidate_id: str, rq: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "summary_zh": f"研究方案生成失败，原始研究问题: {rq[:200]}",
        "technical_roadmap": [],
        "data_sources_detail": [],
        "feasibility": {
            "data_accessibility": {"score": 0, "reason": "LLM生成失败"},
            "compute_requirements": {"gpu_hours": "", "platform": "", "pretrained_available": False, "reason": ""},
            "technical_difficulty": {"score": 0, "level": "", "reason": "LLM生成失败"},
            "timeline_months": 0,
            "key_risks": ["LLM生成失败"],
            "mitigation": ["重新运行"],
        },
        "innovation_points": [],
        "expected_outputs": [],
        "target_venues": [],
    }
