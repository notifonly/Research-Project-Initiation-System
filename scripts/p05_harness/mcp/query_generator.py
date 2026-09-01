from __future__ import annotations

import json
from typing import Any

from shared.core.llm_client import llm_complete
from shared.core.logging_setup import get_logger

from scripts.p05_harness.domain_prompts import get_prompts

logger = get_logger("p05_harness.mcp.query_gen")


def _get_qg_system() -> str:
    return get_prompts().query_generator_system


async def generate_search_queries(critique_text: str, research_question: str, method: str, disease: str) -> list[dict[str, Any]]:
    """Generate MCP search queries from critique-identified literature gaps.

    Returns list of [{"gap": "gap description", "queries": ["q1", "q2"]}]
    """
    domain = get_prompts().domain_name
    prompt = f"""以下是一个{domain}研究方案的评审意见。评审指出了文献覆盖的不足。

研究问题: {research_question}
相关方法: {method}
相关疾病/表型: {disease}

评审意见:
{critique_text}

请分析评审意见，对每个文献缺口生成2-3个精确的学术搜索查询。如果评审未指出文献缺口，返回空数组。

输出JSON:
[
  {{
    "gap": "评审指出的具体缺口（中文，简短描述）",
    "gap_en": "gap description in English",
    "queries": ["search query 1", "search query 2", "search query 3"]
  }}
]

只输出JSON数组。"""

    try:
        raw = await llm_complete(prompt, system=_get_qg_system(), temperature=0.3, max_tokens=2000)
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
        result = json.loads(raw)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.warning(f"Query generation failed: {e}")
        return []
