"""Deterministic evidence-status → wording-strength mapper.

Every judgment's allowed_wording is determined by a rule engine, not by LLM.
This prevents LLM from overclaiming when evidence is weak.
"""
from __future__ import annotations

from typing import Tuple

# (verdict, confidence) → allowed_wording in Chinese
EXPRESSION_RULES: dict[Tuple[str, str], str] = {
    ("fully_supported", "high"): "证据充分支持该主张",
    ("fully_supported", "medium"): "证据较为充分地支持该主张",
    ("fully_supported", "low"): "现有证据支持该主张，但证据质量存在局限",
    ("partially_supported", "high"): "证据部分支持该主张，关键替代解释已控制",
    ("partially_supported", "medium"): "证据部分支持该主张，但存在未控制的替代解释",
    ("partially_supported", "low"): "结果与该解释一致，但不能确认因果关系",
    ("insufficient", "high"): "现有结果仅提供有限支持，需要进一步验证",
    ("insufficient", "medium"): "现有结果仅提供有限支持",
    ("insufficient", "low"): "现有材料不足以判断该主张",
    ("no_evidence", "high"): "论文未提供支持该主张的直接证据",
    ("no_evidence", "medium"): "论文尚未证明该主张",
    ("no_evidence", "low"): "该主张在当前论文中缺乏实验支持",
    ("conflicting", "high"): "证据存在明显冲突，需要进一步研究",
    ("conflicting", "medium"): "当前材料不足以确认该主张，存在矛盾证据",
    ("conflicting", "low"): "证据方向不一致，该主张的可靠性存疑",
}


def get_allowed_wording(verdict: str, confidence: str) -> str:
    """Get the allowed wording for a given verdict and confidence level.

    Falls back to a conservative default if the combination is not found.
    """
    key = (verdict, confidence)
    if key in EXPRESSION_RULES:
        return EXPRESSION_RULES[key]
    # Fallback: use the lowest-confidence entry for this verdict
    highest_confidence = list(EXPRESSION_RULES.values())[-1] if EXPRESSION_RULES else "需要进一步验证"
    for (v, c), wording in EXPRESSION_RULES.items():
        if v == verdict:
            return wording
    return "当前材料不足以确认该主张"
