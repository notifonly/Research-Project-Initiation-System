"""S6C Deep-Read Skill: automated paper deep-reading with evidence-ledger architecture.

Embeds the human paper-reading methodology into the pipeline as an automated skill.
Produces structured deep-read notes (facts, claims, judgments, formulas, experiments)
that feed into S7 evidence card extraction for enriched, evidence-audited cards.

Architecture (6 internal stages):
  Stage 1: Paper identity & source registration
  Stage 2+3: Fact extraction + claim-evidence audit (combined LLM call)
  Stage 6: Programmatic quality gates
  Stage 4: Deep analysis (formula + experiment + positioning) [Tier 2 only]
  Stage 5: Critical assessment [Tier 2 only]

Tier 1 (all papers): Stages 1, 2+3, 6
Tier 2 (top 2 papers): All stages, including formula construct+refute double audit
"""
from __future__ import annotations

import asyncio
import json as _json
from typing import Any

from pydantic import Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext
from shared.skills.deep_read.expression_mapper import get_allowed_wording
from shared.skills.deep_read.quality_gates import validate_deep_read_note
from shared.skills.deep_read.schemas import (
    DeepReadSkillInput,
    DeepReadSkillOutput,
)

logger = get_logger("skill.s6c_deep_read")

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

STAGE23_SYSTEM = """你是一个论文事实抽取与证据审计Agent。你的任务是：
1. 从论文文本中抽取**可验证的事实**（绑定原文定位）
2. 提取**作者主张**（与事实分离）
3. 对每项主张进行**证据审计**：检查主张是否有实验/推导支持，生成判据

核心约束：
- 事实必须绑定 section/page/table/equation 定位信息
- 作者主张不能混入事实卡——Abstract中的"优于""有效""高效"首先是 author_claim
- 每个判断的 allowed_wording 必须匹配证据强度
- 不确定的信息标记为 unresolved，不得补全
- 输出严格的JSON格式，不带markdown代码块标记"""

STAGE4_FORMULA_SYSTEM = """你是一个论文公式审计Agent。你的任务是分析指定公式的计算角色、变量、依赖关系和推导链。

对于每个公式：
1. 说明公式计算什么
2. 列出变量及其含义
3. 构建内部依赖（论文内其他公式/定义）
4. 构建外部来源链（如果论文引用了外部工作）
5. 补全最少必要推导步骤
6. 标记每一步是严格推导(strict)、近似(approximate)、启发式(heuristic)还是未解决(unresolved)
7. 列出成立的假设
8. 评估置信度 (0.0-1.0)

禁止：根据常识虚构来源、把可能来源写成最早来源、把经验项写成数学必然。

输出严格的JSON格式，不带markdown代码块标记。"""

STAGE4_FORMULA_REFUTE_SYSTEM = """你是一个论文公式反驳Agent。你的任务是专门寻找已分析公式中的**缺陷**：

1. 检查等号是否应为近似号
2. 检查归一化是否正确
3. 检查省略项是否影响最优解
4. 检查隐式假设
5. 检查边界条件
6. 检查理论与代码实现的可能不一致
7. 标记无法确认的步骤为 unresolved

输出严格的JSON格式，不带markdown代码块标记。"""

STAGE5_SYSTEM = """你是一个论文批判性评估Agent。基于已完成的事实抽取、主张审计和公式分析，
对论文进行整体评估。

评估维度：
1. 方法论可信度 (credibility: high/medium/low)
2. 方法论问题 (methodology_issues)
3. 可复现性关注 (reproducibility_concerns)
4. 贡献层级 (contribution_level: breakthrough/significant/incremental/minor)
5. 开放问题 (open_problems)

原则：
- 不引入外部知识做判断
- 判断强度不能超过已有证据强度
- 不确定处使用"可能""尚未明确"等措辞

输出严格的JSON格式，不带markdown代码块标记。"""


# ---------------------------------------------------------------------------
# Text extraction helper
# ---------------------------------------------------------------------------

def _get_paper_text(paper: dict[str, Any], max_chars: int = 24000) -> str:
    """Extract the best available text from a paper dict. Prefers full_text > abstract."""
    text = paper.get("full_text") or paper.get("abstract") or paper.get("title") or ""
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[text truncated]"
    return text


def _get_paper_id(paper: dict[str, Any]) -> str:
    return paper.get("paper_id") or paper.get("paperId") or paper.get("pmid") or ""


def _get_paper_title(paper: dict[str, Any]) -> str:
    return paper.get("title") or paper.get("paperTitle") or ""


# ---------------------------------------------------------------------------
# Main skill
# ---------------------------------------------------------------------------

class DeepReadSkill(BaseSkill):
    """S6C: Automated paper deep-reading with evidence-ledger architecture."""

    name: str = "s6c_deep_read"
    description: str = "Deep-read selected papers to produce structured evidence-ledger notes for enriched card extraction"
    uses_llm: bool = True
    budget_phase: BudgetPhase = BudgetPhase.EXTRACTION

    input_schema = DeepReadSkillInput
    output_schema = DeepReadSkillOutput

    def __init__(self) -> None:
        super().__init__()
        self._metrics: dict[str, Any] = {}

    async def pre_check(self, inp, ctx: SkillContext) -> bool:
        if not getattr(inp, "papers", None):
            self.logger.info("S6C: no papers to deep-read, skipping")
            return False
        return True

    async def execute(self, inp, ctx: SkillContext) -> DeepReadSkillOutput:
        self._ctx = ctx  # store for use in internal stage methods
        papers: list[dict[str, Any]] = getattr(inp, "papers", [])
        max_papers: int = getattr(inp, "max_papers", 5)
        max_tier2: int = getattr(inp, "max_tier2_papers", 2)
        papers = papers[: max_papers]
        self.logger.info(f"S6C: deep-reading {len(papers)} papers (max tier2: {max_tier2})")

        notes: list[dict[str, Any]] = []
        tier2_count = 0
        human_review_count = 0

        for i, paper in enumerate(papers):
            is_tier2 = i < max_tier2
            try:
                note = await self._deep_read_one(paper, is_tier2)
                notes.append(note)
                if is_tier2 and note.get("reading_depth") == "tier2":
                    tier2_count += 1
                if note.get("needs_human_review"):
                    human_review_count += 1
            except Exception as e:
                self.logger.error(f"S6C: failed to deep-read paper {_get_paper_id(paper)}: {e}")
                notes.append(self._error_note(paper, str(e)))

        self._metrics["papers_processed"] = len(notes)
        self._metrics["papers_tier2"] = tier2_count
        self._metrics["papers_needing_human_review"] = human_review_count

        return DeepReadSkillOutput(
            notes=notes,
            papers_processed=len(notes),
            papers_tier2=tier2_count,
            papers_needing_human_review=human_review_count,
        )

    # ------------------------------------------------------------------
    # Per-paper deep-read pipeline
    # ------------------------------------------------------------------

    async def _deep_read_one(self, paper: dict[str, Any], is_tier2: bool) -> dict[str, Any]:
        paper_id = _get_paper_id(paper)
        paper_title = _get_paper_title(paper)
        text = _get_paper_text(paper)

        note: dict[str, Any] = {
            "paper_id": paper_id,
            "paper_title": paper_title,
            "reading_depth": "tier2" if is_tier2 else "tier1",
            "facts": [],
            "claims": [],
            "judgments": [],
            "formulas": [],
            "experiments": [],
            "critical_assessment": None,
            "quality_gate": {},
            "needs_human_review": False,
            "human_review_items": [],
        }

        if len(text) < 100:
            note["needs_human_review"] = True
            note["human_review_items"].append("insufficient_text")
            return note

        # --- Stage 2+3: Fact extraction + claim-evidence audit (combined) ---
        stage23_result = await self._run_stage23(text)
        if stage23_result:
            note["facts"] = stage23_result.get("facts", [])
            note["claims"] = stage23_result.get("claims", [])
            note["judgments"] = self._build_judgments(stage23_result.get("claims", []))

        # --- Stage 6: Programmatic quality gates ---
        note["quality_gate"] = validate_deep_read_note(note).__dict__

        # --- Tier 2: Deep analysis ---
        if is_tier2 and note["claims"]:
            stage4_result = await self._run_stage4(text, note["claims"])
            if stage4_result:
                note["formulas"] = stage4_result.get("formulas", [])
                note["experiments"] = stage4_result.get("experiments", [])

                # Formula refutation (double audit)
                for formula in note["formulas"]:
                    if formula.get("confidence", 1.0) < 0.85:
                        refute_result = await self._run_stage4_refute(text, formula)
                        if refute_result and refute_result.get("issues"):
                            formula["refute_issues"] = refute_result["issues"]
                            formula["requires_human_review"] = True

            stage5_result = await self._run_stage5(text, note)
            if stage5_result:
                note["critical_assessment"] = stage5_result

        # --- Human review triggers ---
        triggers: list[str] = []
        qg = note.get("quality_gate", {})
        if isinstance(qg, dict) and qg.get("human_review_triggers"):
            triggers.extend(qg["human_review_triggers"])
        for f in note.get("formulas", []):
            if isinstance(f, dict) and f.get("requires_human_review"):
                triggers.append(f"formula_needs_review:{f.get('formula_id', '?')}")
            if isinstance(f, dict) and f.get("confidence", 1.0) < 0.85:
                triggers.append(f"low_formula_confidence:{f.get('formula_id', '?')}")
        if triggers:
            note["needs_human_review"] = True
            note["human_review_items"] = triggers

        return note

    # ------------------------------------------------------------------
    # Stage 2+3: Fact extraction + claim-evidence audit (combined)
    # ------------------------------------------------------------------

    async def _run_stage23(self, text: str) -> dict[str, Any] | None:
        prompt = f"""请从以下论文文本中抽取结构化信息。输出以下JSON结构：

{{
  "facts": [
    {{
      "fact_id": "F-001",
      "category": "method",
      "statement": "模型在第3.2节使用了transformer编码器处理基因表达矩阵...",
      "source_locator": {{ "section": "3.2", "page": 5, "table_or_figure": null, "equation": "4" }},
      "evidence_status": "directly_stated"
    }}
  ],
  "claims": [
    {{
      "claim_id": "C-001",
      "text": "scGPT在细胞类型注释任务上超越了所有基线方法",
      "claim_origin": "author",
      "source_locator": {{ "section": "Abstract", "page": 1 }}
    }}
  ]
}}

要求：
- 抽取8-15条事实(facts)，覆盖方法、实验、结果、局限性
- 抽取3-6条作者主张(claims)，与事实严格分离
- 每条事实的evidence_status必须是以下之一：directly_stated, strictly_derived, inferred, author_claim, unresolved
- 每条事实必须绑定source_locator（至少包含section）
- fact_id使用F-001, F-002...格式，claim_id使用C-001, C-002...格式

论文文本：
{text}

只输出JSON。"""
        try:
            raw = await self._llm(prompt, self._ctx, system=STAGE23_SYSTEM)
            return _parse_json(raw)
        except Exception as e:
            self.logger.warning(f"S6C stage23 failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Build judgments from claims (deterministic + LLM)
    # ------------------------------------------------------------------

    def _build_judgments(self, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """For now, build minimal judgment stubs that the quality gate can validate.
        Full claim-evidence audit requires a second LLM pass which we defer to
        a future enhancement — the structured facts+claims from Stage 2+3 already
        provide the separation needed for enriched card extraction.
        """
        judgments: list[dict[str, Any]] = []
        for i, claim in enumerate(claims):
            cid = claim.get("claim_id", f"C-{i+1:03d}")
            judgments.append({
                "judgment_id": f"J-{i+1:03d}",
                "claim_id": cid,
                "subject": claim.get("text", "")[:80],
                "verdict": "insufficient",
                "confidence": "low",
                "supporting_evidence": [],
                "counter_evidence": [],
                "alternative_explanations": [],
                "missing_controls": ["deep_read_audit_pending"],
                "allowed_wording": get_allowed_wording("insufficient", "low"),
                "forbidden_wording": "该主张已被充分验证",
                "human_review_required": True,
            })
        return judgments

    # ------------------------------------------------------------------
    # Stage 4: Deep analysis (formula + experiment) [Tier 2 only]
    # ------------------------------------------------------------------

    async def _run_stage4(self, text: str, claims: list[dict[str, Any]]) -> dict[str, Any] | None:
        claim_summary = "\n".join(
            f"- {c.get('claim_id', '?')}: {c.get('text', '')[:120]}"
            for c in claims[:3]
        )
        prompt = f"""请对以下论文的核心公式和实验进行深度分析。

核心主张：
{claim_summary}

请输出以下JSON结构：
{{
  "formulas": [
    {{
      "formula_id": "EQ-001",
      "expression_latex": "L = ...",
      "role": "training_objective",
      "variables": ["x", "y", "z"],
      "internal_parents": ["EQ-003"],
      "derivation_steps": [
        {{
          "step": 1,
          "operation": "substitute_definition",
          "from_expression": "...",
          "to_expression": "...",
          "assumptions": ["..."],
          "derivation_type": "strict"
        }}
      ],
      "assumptions": ["...假设..."],
      "provenance_class": "strict",
      "confidence": 0.85
    }}
  ],
  "experiments": [
    {{
      "experiment_id": "EXP-001",
      "claim_ids": ["C-001"],
      "dataset": "CELLxGENE",
      "metric": "macro_F1",
      "method_value": 0.85,
      "baseline_value": 0.82,
      "absolute_delta": 0.03,
      "interpretation_limits": ["未报告方差"]
    }}
  ]
}}

- 提取0-3个公式（只提取有实质数学内容的公式）
- 对每个公式标注角色(role)：training_objective, inference, architecture, loss, regularization, other
- derivation_type必须是: strict, approximate, heuristic, unresolved
- provenance_class必须是: strict, approximate, heuristic, theory_plus_heuristic, unresolved
- 提取0-3个实验（只提取与核心主张相关的关键实验）
- 如果论文没有公式或关键实验，返回空列表

论文文本：
{text}

只输出JSON。"""
        try:
            raw = await self._llm(prompt, self._ctx, system=STAGE4_FORMULA_SYSTEM)
            return _parse_json(raw)
        except Exception as e:
            self.logger.warning(f"S6C stage4 failed: {e}")
            return None

    async def _run_stage4_refute(self, text: str, formula: dict[str, Any]) -> dict[str, Any] | None:
        """Refutation pass: find issues in the constructed formula derivation."""
        formula_json = _json.dumps(formula, ensure_ascii=False, indent=2)
        prompt = f"""请审计以下公式分析，专门寻找**缺陷**和**问题**：

公式分析：
{formula_json}

请输出：
{{
  "issues": [
    {{
      "type": "equality_should_be_approximation",
      "description": "...具体问题...",
      "severity": "high"
    }}
  ],
  "overall_assessment": "公式推导中存在的问题总结（1-2句）"
}}

检查项：
1. 等号是否应为近似号
2. 归一化是否正确
3. 省略项是否影响最优解
4. 存在哪些隐式假设
5. 边界条件是否满足
6. 理论与实现的可能不一致

论文原文（参考）：
{text[:8000]}

只输出JSON。"""
        try:
            raw = await self._llm(prompt, self._ctx, system=STAGE4_FORMULA_REFUTE_SYSTEM)
            return _parse_json(raw)
        except Exception as e:
            self.logger.warning(f"S6C stage4 refute failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Stage 5: Critical assessment [Tier 2 only]
    # ------------------------------------------------------------------

    async def _run_stage5(self, text: str, note: dict[str, Any]) -> dict[str, Any] | None:
        claim_texts = "\n".join(
            f"- {c.get('text', '')[:100]}" for c in note.get("claims", [])[:3]
        )
        formula_count = len(note.get("formulas", []))
        experiment_count = len(note.get("experiments", []))
        fact_count = len(note.get("facts", []))

        prompt = f"""请基于以下信息对论文进行批判性评估。

论文信息：
- 抽取事实数: {fact_count}
- 核心主张: 
{claim_texts}
- 分析公式数: {formula_count}
- 分析实验数: {experiment_count}

请输出：
{{
  "credibility": "medium",
  "methodology_issues": ["问题1", "问题2"],
  "reproducibility_concerns": ["关注点1"],
  "contribution_level": "incremental",
  "open_problems": ["开放问题1"],
  "overall_strength": "论文的方法论...(1-2句总结)"
}}

credibility: high / medium / low
contribution_level: breakthrough / significant / incremental / minor

论文文本（最后8000字符）：
{text[-8000:]}

只输出JSON。"""
        try:
            raw = await self._llm(prompt, self._ctx, system=STAGE5_SYSTEM)
            return _parse_json(raw)
        except Exception as e:
            self.logger.warning(f"S6C stage5 failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _select_tier2_papers(self, papers: list[dict[str, Any]], max_count: int) -> set[str]:
        """Select top-N papers for Tier 2 deep analysis. Currently just first N."""
        return {_get_paper_id(p) for p in papers[:max_count]}

    @staticmethod
    def _error_note(paper: dict[str, Any], error: str) -> dict[str, Any]:
        return {
            "paper_id": _get_paper_id(paper),
            "paper_title": _get_paper_title(paper),
            "reading_depth": "tier1",
            "facts": [],
            "claims": [],
            "judgments": [],
            "formulas": [],
            "experiments": [],
            "critical_assessment": None,
            "quality_gate": {"passed": False, "error": error},
            "needs_human_review": True,
            "human_review_items": [f"extraction_error:{error[:100]}"],
        }


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> dict[str, Any]:
    """Parse LLM response, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    text = text.strip()
    if not text:
        return {}
    return _json.loads(text)
