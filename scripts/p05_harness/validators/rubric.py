from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from scripts.p05_harness.domain_prompts import get_prompts

DIMENSION_DESCRIPTIONS = {
    "literature_coverage": {
        "label_zh": "文献覆盖度",
        "score_descriptions": {
            1: "未引用任何相关文献，或仅引用不相关的通用文献",
            2: "引用了1-2篇弱相关文献，但未覆盖核心方法/数据的关键文献",
            3: "引用了3-5篇相关文献，覆盖了主要方法，但缺少对比或最新进展",
            4: "系统梳理了相关文献，引用5+篇，覆盖方法、数据、baseline，但仍有少量缺口",
            5: "全面、系统地梳理了领域文献，包含经典/最新/对比文献，明确指出文献覆盖边界",
        },
    },
    "technical_feasibility": {
        "label_zh": "技术可行性",
        "score_descriptions": {
            1: "技术路线空洞或明显不可行，缺少任何技术细节",
            2: "有粗略路线但缺少具体方法、工具或步骤描述",
            3: "技术路线完整但部分步骤描述模糊，缺少时间估算或替代方案",
            4: "技术路线清晰，包含具体方法/工具/时间，有备选方案",
            5: "技术路线详尽且有说服力，包含具体方法、工具、参数建议、时间估算、风险缓解、备选方案",
        },
    },
    "innovation_clarity": {
        "label_zh": "创新性清晰度",
        "score_descriptions": {
            1: "仅复述研究问题，未提出任何创新点",
            2: "有1-2个模糊的创新声明，但未与现有工作对比",
            3: "提出了2-3个创新点，部分与现有工作有对比，但差异化不够清晰",
            4: "创新点清晰且与现有工作有系统对比，差异化阐述清楚",
            5: "创新点突出，有深刻的 gap analysis 支撑，与现有工作有量化对比，学术价值明确",
        },
    },
    "data_accessibility": {
        "label_zh": "数据可及性",
        "score_descriptions": {
            1: "未提及任何数据来源或提及不可获取的私有数据",
            2: "只提到通用数据集名称，无具体 accession 或获取方式",
            3: "列出了2-3个数据集，有不完整的 accession 信息",
            4: "详细列出数据来源，包含 accession 编号、获取方式、格式、样本量",
            5: "详尽列出所有数据来源，包含 accession、获取方式、预处理说明、备选数据集和许可信息",
        },
    },
    "gap_alignment": {
        "label_zh": "缺口对齐度",
        "score_descriptions": {
            1: "未关联任何研究缺口",
            2: "仅泛泛提及其他缺口，无具体对应关系",
            3: "关联了1个缺口，有对应策略但不深入",
            4: "关联2+缺口，有针对策略，策略有一定深度",
            5: "深度关联2+缺口，每项有具体、可操作的对策，方案设计直接填补缺口",
        },
    },
    "evaluation_rigor": {
        "label_zh": "评估严谨性",
        "score_descriptions": {
            1: "未描述任何评估方案或评估方案完全不合理",
            2: "仅有粗略评估描述，缺少基线、指标、数据划分等关键信息",
            3: "有基本评估方案，但基线不充分（缺少random/oracle/固定模型）、存在数据泄漏风险、或学习信号可用性未论证",
            4: "评估方案完整，包含合理基线、明确指标、数据划分；数据版本/快照有说明",
            5: "评估方案严谨全面，包含oracle上界、随机基线、固定模型、简单启发式全梯度基线；数据泄漏已排除；反馈信号有效性经论证；完整可复现",
        },
    },
}


@dataclass
class BaseRubric:
    rubric_id: str = "default"
    pass_threshold: float = 4.0
    min_dimension: float = 3.0
    novelty_guidance: str = ""

    def __post_init__(self):
        cls = type(self)
        if hasattr(cls, 'dimension_weights') and isinstance(cls.dimension_weights, dict):
            self.dimension_weights = dict(cls.dimension_weights)
        elif not hasattr(self, 'dimension_weights') or not self.dimension_weights:
            self.dimension_weights = {}

    def get_weight(self, dim_key: str) -> float:
        return self.dimension_weights.get(dim_key, 0.0)

    def get_label(self, dim_key: str) -> str:
        return DIMENSION_DESCRIPTIONS.get(dim_key, {}).get("label_zh", dim_key)

    def get_descriptions(self, dim_key: str) -> dict[int, str]:
        return DIMENSION_DESCRIPTIONS.get(dim_key, {}).get("score_descriptions", {})

    @property
    def dimensions(self) -> dict[str, dict[str, Any]]:
        result = {}
        for key, info in DIMENSION_DESCRIPTIONS.items():
            result[key] = {
                "label_zh": info["label_zh"],
                "weight": self.dimension_weights.get(key, 0.0),
                "score_descriptions": info["score_descriptions"],
            }
        return result


class DefaultRubric(BaseRubric):
    rubric_id = "default"
    dimension_weights = {
        "literature_coverage": 0.20,
        "technical_feasibility": 0.20,
        "innovation_clarity": 0.20,
        "data_accessibility": 0.15,
        "gap_alignment": 0.10,
        "evaluation_rigor": 0.15,
    }


class CrossDomainRubric(BaseRubric):
    rubric_id: str = "cross_domain"
    dimension_weights = {
        "literature_coverage": 0.10,
        "technical_feasibility": 0.18,
        "innovation_clarity": 0.27,
        "data_accessibility": 0.18,
        "gap_alignment": 0.12,
        "evaluation_rigor": 0.15,
    }

    def __post_init__(self):
        super().__post_init__()
        self.rubric_id = "cross_domain"
    novelty_guidance = """
## 跨学科创新方向评审指引

此方向属于跨学科新兴领域，评审时请注意：
- **技术可行性评分时区分两类缺口**:
  (a) "可修复缺口" — 组合已有方法/工具的可行性问题（如缺少具体数据集名称、benchmark 设计不完整）→ 应指出并要求补充
  (b) "不可修复缺口" — 需要全新方法发明的问题（如需要开发新的理论框架）→ 应认可其探索价值，在反馈中说明"这属于开放研究问题"而非反复扣分
- **文献覆盖度**: 跨学科领域的文献缺失不必过度惩罚——文献少恰恰说明交叉方向新。评估引用的"相关性"而非"数量"
- **创新清晰度**作为首要维度：跨学科方向的特点就是创新性强，请重点关注创新点是否阐述清晰、对比基准是否合理
- **数据可及性**: 跨学科方向更需要具体的数据支撑，评估数据来源是否真实可获取
"""


RUBRIC_REGISTRY: dict[str, type[BaseRubric]] = {
    "default": DefaultRubric,
    "cross_domain": CrossDomainRubric,
}

# Backward-compatible alias
RUBRIC_DIMENSIONS = DefaultRubric().dimensions


def get_rubric(candidate: dict | None = None) -> BaseRubric:
    rubric_id = "default"
    if candidate:
        rubric_id = candidate.get("rubric", "default")
    rubric_cls = RUBRIC_REGISTRY.get(rubric_id, DefaultRubric)
    rubric = rubric_cls()

    _apply_smooth_novelty_weights(rubric, candidate)
    return rubric


def _apply_smooth_novelty_weights(rubric: BaseRubric, candidate: dict | None) -> None:
    """标记低竞争方向需要深度新颖性验证，而非放宽文献审查。

    低竞争方向（competitiveness < 0.10）可能表示：
    (a) 方向确实新颖 → 需要 anti-bias 指引，确保评审不过度惩罚文献缺失
    (b) 初步检索未能命中相近工作 → 需要触发 Phase 1.5 对抗性搜索来确认真实新颖性

    不再降低 literature_coverage 权重（旧行为的反常激励：低竞争反而放宽文献审查）。
    """
    if candidate is None:
        return
    scores = candidate.get("scores", {})
    if not isinstance(scores, dict):
        return
    competitiveness = scores.get("competitiveness")
    if competitiveness is None:
        return
    try:
        comp = float(competitiveness)
    except (TypeError, ValueError):
        return

    if comp >= 0.10:
        return

    # 低竞争方向：不降低任何维度的权重，只追加评审指引
    # novelty_unverified 标志由 Phase 1.5 根据对抗性检索结果更新为 clear/crowded/scooped
    if rubric.rubric_id == "default":
        rubric.novelty_guidance = """
## 低竞争方向评审指引（竞争力<0.10）

此方向初步检索未发现大量相近工作。请在评审时注意：
- **文献覆盖度**: 文献少可能因方向新，但也可能因初步检索未命中（如论文使用了不同术语）。评审应保持标准严格，如果方案中缺乏与已有工作的系统对比，应标记为\"文献覆盖不足\"并要求补充
- **技术可行性评分时区分两类缺口**:
  (a) \"可修复缺口\" — 组合已有方法/工具的可行性问题（如缺少具体数据集名称、benchmark 设计不完整）→ 应指出并要求补充
  (b) \"不可修复缺口\" — 需要全新方法发明的问题（如需要开发新的理论框架）→ 应认可其探索价值，在反馈中说明\"这属于开放研究问题\"而非反复扣分
- **创新清晰度**: 低竞争方向需要更清晰的差异化定位——因为没有大量文献可以\"自然对比\"，方案应主动列举最接近的已有工作并说明边界
- **评估严谨性**: 低竞争方向通常缺少现成benchmark，评估方案设计更加重要
"""

    elif rubric.rubric_id == "cross_domain":
        rubric.novelty_guidance = """
## 跨学科创新方向评审指引

此方向属于跨学科新兴领域，评审时请注意：
- **技术可行性评分时区分两类缺口**:
  (a) \"可修复缺口\" — 组合已有方法/工具的可行性问题（如缺少具体数据集名称、benchmark 设计不完整）→ 应指出并要求补充
  (b) \"不可修复缺口\" — 需要全新方法发明的问题（如需要开发新的理论框架）→ 应认可其探索价值，在反馈中说明\"这属于开放研究问题\"而非反复扣分
- **文献覆盖度**: 跨学科领域的文献缺失可能因领域交叉新。但方案应明确引用各自源头领域的代表性工作并提供交叉对比。文献少不代表可以豁免系统对比
- **创新清晰度作为首要维度**：跨学科方向的特点就是创新性强，请重点关注创新点是否阐述清晰、对比基准是否合理
- **数据可及性**: 跨学科方向更需要具体的数据支撑，评估数据来源是否真实可获取
- **评估严谨性**: 跨学科方向需要明确从各领域沿用或新设计的评估方法，数据泄漏风险需特别关注
"""


@dataclass
class CritiqueResult:
    candidate_id: str
    iteration: int
    scores: dict[str, float] = field(default_factory=dict)
    weighted_score: float = 0.0
    passed: bool = False
    critique_text: str = ""
    detailed_feedback: dict[str, str] = field(default_factory=dict)
    literature_gaps: list[str] = field(default_factory=list)
    raw_response: str = ""
    score_stability: float = -1.0
    novelty_verdicts: list[dict[str, Any]] = field(default_factory=list)
    redteam_findings: list[dict[str, Any]] = field(default_factory=list)
    reviewer_profile: str = "generalist"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "iteration": self.iteration,
            "scores": self.scores,
            "weighted_score": self.weighted_score,
            "passed": self.passed,
            "critique_text": self.critique_text,
            "detailed_feedback": self.detailed_feedback,
            "literature_gaps": self.literature_gaps,
            "score_stability": self.score_stability,
            "novelty_verdicts": self.novelty_verdicts,
            "redteam_findings": self.redteam_findings,
            "reviewer_profile": self.reviewer_profile,
        }

    @classmethod
    def from_llm_response(
        cls,
        candidate_id: str,
        iteration: int,
        raw: str,
        pass_threshold: float = 4.0,
        candidate: dict | None = None,
        rubric: BaseRubric | None = None,
        reviewer_profile: str = "generalist",
    ) -> CritiqueResult:
        import json

        result = CritiqueResult(candidate_id=candidate_id, iteration=iteration, raw_response=raw, reviewer_profile=reviewer_profile)
        if rubric is None:
            rubric = get_rubric(candidate)
        try:
            data = _parse_json_from_llm(raw)
            dims = rubric.dimensions
            scores: dict[str, float] = {}
            feedback: dict[str, str] = {}

            scores_raw = data.get("scores", data.get("评分", {}))
            for dim_key, dim_info in dims.items():
                label = dim_info["label_zh"]
                raw_val = scores_raw.get(dim_key) or scores_raw.get(label)
                if raw_val is None:
                    from shared.core.logging_setup import get_logger
                    _l = get_logger("p05_harness.rubric")
                    _l.warning(f"Critique missing dimension '{dim_key}' ('{label}'), defaulting to 2.0")
                    raw_val = 2.0
                scores[dim_key] = float(raw_val)

            for dim_key, dim_info in dims.items():
                label = dim_info["label_zh"]
                fb = data.get("feedback", data.get("详细反馈", {}))
                dim_fb = fb.get(dim_key) or fb.get(label) or ""
                feedback[dim_key] = str(dim_fb)

            result.scores = scores
            result.detailed_feedback = feedback
            result.critique_text = data.get("summary", data.get("总评", ""))
            result.literature_gaps = data.get("literature_gaps", data.get("文献缺口", [])) or []

            weights = rubric.dimension_weights
            weighted = sum(scores.get(k, 2.0) * weights.get(k, 0.0) for k in dims)
            result.weighted_score = round(weighted, 2)

            min_dim = min(scores.values()) if scores else 2.0
            result.passed = result.weighted_score >= pass_threshold and min_dim >= rubric.min_dimension
        except Exception:
            result.weighted_score = -1.0
            result.passed = False

        return result


def _parse_json_from_llm(raw: str) -> dict[str, Any]:
    import json

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    return json.loads(text)


REVIEWER_PROFILES: dict[str, str] = get_prompts().reviewer_profiles

REVIEWER_PROFILE_ORDER: list[str] = get_prompts().reviewer_profile_order

REVIEWER_DIMENSION_EMPHASIS: dict[str, str] = get_prompts().reviewer_dimension_emphasis

CRITIQUE_SYSTEM_PROMPT = get_prompts().reviewer_profiles.get("generalist", "")


def build_critique_prompt(
    plan_json: str,
    candidate_info: str,
    candidate: dict | None = None,
    rubric: BaseRubric | None = None,
    novelty_verdicts: list[dict[str, Any]] | None = None,
    redteam_findings: list[dict[str, Any]] | None = None,
    reviewer_profile: str = "generalist",
    plan: dict[str, Any] | None = None,
) -> str:
    if rubric is None:
        rubric = get_rubric(candidate)

    dim_lines = []
    for key in rubric.dimension_weights:
        info = rubric.dimensions.get(key, {})
        descs = info.get("score_descriptions", {})
        desc_text = "\n".join(f"    {s}分: {d}" for s, d in sorted(descs.items()))
        dim_lines.append(f"  {info.get('label_zh', key)} (权重{info.get('weight', 0)}):\n{desc_text}")

    dims_text = "\n".join(dim_lines)

    novelty_guidance = rubric.novelty_guidance

    profile_emphasis = REVIEWER_DIMENSION_EMPHASIS.get(reviewer_profile, "")

    novelty_section = _format_novelty_context(novelty_verdicts)
    redteam_section = _format_redteam_context(redteam_findings)

    profile_header = f"\n{profile_emphasis}\n" if profile_emphasis else ""

    focused_section = ""
    if reviewer_profile == "methodologist":
        focused_section = _format_methodologist_focus(plan, redteam_findings)
    elif reviewer_profile == "domain_expert":
        focused_section = _format_domain_expert_focus(plan, novelty_verdicts)

    domain_name = get_prompts().domain_name
    prompt = f"""请评审以下{domain_name}研究方案。
{novelty_guidance}{profile_header}
候选方向信息:
{candidate_info}
{novelty_section}{redteam_section}{focused_section}
研究方案:
{plan_json}

## 评审维度

{dims_text}

## 评审要求

1. 对每个维度给出1-5的整数评分
2. 每个维度的评分必须附上具体的修改建议
3. 给出总体评价 (200字以内)
4. 列出方案中的文献缺口主题 (如果有)
5. 缺口的列举要具体，例如 "缺少 scGPT 在跨组织迁移学习方面的文献" 而非 "文献不够"

输出JSON:
{{
  "scores": {{
    "literature_coverage": 整数1-5,
    "technical_feasibility": 整数1-5,
    "innovation_clarity": 整数1-5,
    "data_accessibility": 整数1-5,
    "gap_alignment": 整数1-5,
    "evaluation_rigor": 整数1-5
  }},
  "feedback": {{
    "literature_coverage": "具体建议",
    "technical_feasibility": "具体建议",
    "innovation_clarity": "具体建议",
    "data_accessibility": "具体建议",
    "gap_alignment": "具体建议",
    "evaluation_rigor": "具体建议"
  }},
  "summary": "总体评价200字",
  "literature_gaps": ["缺口主题1", "缺口主题2"]
}}

只输出JSON。"""

    return prompt


def _format_novelty_context(novelty_verdicts: list[dict[str, Any]] | None) -> str:
    if not novelty_verdicts:
        return ""
    lines = [
        "",
        "## 新颖性验证上下文（对抗性检索结果）",
        "以下是由 Phase 1.5 对抗性检索验证的新颖性判定，请在评审创新性和文献覆盖时参考：",
        "",
    ]
    for i, vd in enumerate(novelty_verdicts):
        lines.append(f"### 声明 {i+1}: {vd.get('claim', '')}")
        lines.append(f"判定: **{vd.get('verdict', '')}** — {vd.get('closeness', '')}")
        cw = vd.get("closest_works", [])
        if cw:
            lines.append("最接近的已有工作:")
            for j, w in enumerate(cw[:3]):
                title = w.get("title", "N/A")
                authors = w.get("authors", "")
                year = w.get("year", "")
                venue = w.get("venue", "")
                similarity = w.get("similarity", "")
                lines.append(f"  {j+1}. **{title}** ({authors}, {year}, {venue})")
                if similarity:
                    lines.append(f"     重合: {similarity}")
        ct = vd.get("comparison_table", [])
        if ct:
            lines.append("对比维度:")
            for row in ct[:5]:
                lines.append(f"  - {row.get('dimension', '?')}: 已有[{row.get('existing_work', '')}], 本方案[{row.get('our_approach', '')}]")
        lines.append("")
    return "\n".join(lines)


def _format_redteam_context(redteam_findings: list[dict[str, Any]] | None) -> str:
    if not redteam_findings:
        return ""
    lines = [
        "",
        "## 红队评审上下文（方法论严谨性检查）",
        "以下是由 Phase 1.6 方法论红队发现的问题，请在评审技术可行性和评估严谨性时参考：",
        "",
    ]
    for i, f in enumerate(redteam_findings):
        severity = f.get("severity", "low")
        check = f.get("check", "?")
        detail = f.get("detail", "")
        suggestion = f.get("suggestion", "")
        severity_mark = {"high": "[高风险]", "medium": "[中风险]", "low": "[低风险]"}.get(severity, "")
        lines.append(f"### {severity_mark} {check}")
        lines.append(f"问题: {detail}")
        if suggestion:
            lines.append(f"建议: {suggestion}")
        lines.append("")
    return "\n".join(lines)


def _format_methodologist_focus(
    plan: dict[str, Any] | None,
    redteam_findings: list[dict[str, Any]] | None,
) -> str:
    if not plan:
        return ""
    lines = [
        "",
        "## 重点评审区: 技术实现细节",
        "请着重从以下方面评估技术可行性和评估严谨性：",
        "",
    ]
    roadmap = plan.get("technical_roadmap", [])
    if isinstance(roadmap, list) and roadmap:
        lines.append("### 技术路线")
        for step in roadmap[:5]:
            if isinstance(step, dict):
                title = step.get("title", step.get("step", ""))
                methods = step.get("methods", "")
                tools = step.get("tools", "")
                weeks = step.get("weeks", "")
                lines.append(f"- **{title}** ({weeks}周): 方法={methods}, 工具={tools}")
            else:
                lines.append(f"- {step}")
        lines.append("")

    data_sources = plan.get("data_sources_detail", [])
    if isinstance(data_sources, list) and data_sources:
        lines.append("### 数据源")
        for ds in data_sources[:3]:
            if isinstance(ds, dict):
                lines.append(f"- {ds.get('name', '?')}: {ds.get('access', '?')} | 格式={ds.get('format', '?')} | 大小={ds.get('size', '?')}")
        lines.append("")

    feasibility = plan.get("feasibility", {})
    if isinstance(feasibility, dict):
        lines.append("### 可行性评估")
        compute = feasibility.get("compute_requirements", {})
        if isinstance(compute, dict):
            lines.append(f"- GPU: {compute.get('gpu_hours', '?')}小时, 平台: {compute.get('platform', '?')}")
            lines.append(f"- 预训练模型可用: {compute.get('pretrained_available', '?')}")
        timeline = feasibility.get("timeline_months", "")
        if timeline:
            lines.append(f"- 预计周期: {timeline}个月")
        risks = feasibility.get("key_risks", [])
        if risks:
            lines.append(f"- 关键风险: {', '.join(str(r) for r in risks[:3])}")
        lines.append("")

    method_redteam = [
        f for f in (redteam_findings or [])
        if isinstance(f, dict) and f.get("check", "").lower() in (
            "data_leakage", "feedback_validity", "baseline_adequacy",
            "reproducibility", "compute_estimation", "methodology",
        )
    ]
    if method_redteam:
        lines.append("### 方法论红队发现 (需重点关注)")
        for f in method_redteam[:5]:
            lines.append(f"- [{f.get('severity', '?')}] {f.get('check', '?')}: {f.get('detail', '')[:120]}")
        lines.append("")

    return "\n".join(lines)


def _format_domain_expert_focus(
    plan: dict[str, Any] | None,
    novelty_verdicts: list[dict[str, Any]] | None,
) -> str:
    if not plan:
        return ""
    lines = [
        "",
        "## 重点评审区: 创新性与领域定位",
        "请着重从以下方面评估创新清晰度和领域缺口对齐：",
        "",
    ]
    summary = plan.get("summary_zh", "")
    if summary:
        lines.append(f"### 研究摘要\n{summary[:300]}\n")

    innovation = plan.get("innovation_points", [])
    if isinstance(innovation, list) and innovation:
        lines.append("### 创新点")
        for i, ip in enumerate(innovation[:5]):
            if isinstance(ip, dict):
                claim = ip.get("claim", "")
                closest = ip.get("closest_existing_work", "")
                diff = ip.get("difference", "")
                lines.append(f"{i+1}. **{claim}**")
                if closest:
                    lines.append(f"   已有工作: {closest}")
                if diff:
                    lines.append(f"   差异: {diff}")
            else:
                lines.append(f"{i+1}. {ip}")
        lines.append("")

    expected = plan.get("expected_outputs", [])
    if isinstance(expected, list) and expected:
        lines.append(f"### 预期成果\n" + "\n".join(f"- {o}" for o in expected[:4]))
        lines.append("")

    domain_novelty = [
        v for v in (novelty_verdicts or [])
        if isinstance(v, dict) and v.get("verdict", "") in ("scooped", "crowded")
    ]
    if domain_novelty:
        lines.append("### 新颖性预警 (需重点关注)")
        for v in domain_novelty[:3]:
            lines.append(f"- 声明: {v.get('claim', '')[:100]}")
            lines.append(f"  判定: {v.get('verdict', '')} | 重合: {v.get('closeness', '')}")
        lines.append("")

    return "\n".join(lines)


class RobustCritique:
    EDGE_LOWER = 3.7
    EDGE_UPPER = 4.1
    N_REPEATS = 3

    @classmethod
    def is_edge_candidate(cls, score: float) -> bool:
        return cls.EDGE_LOWER <= score <= cls.EDGE_UPPER

    @classmethod
    def aggregate(cls, results: list[CritiqueResult], pass_threshold: float = 4.0) -> tuple[CritiqueResult, float]:
        import statistics

        if len(results) == 1:
            return results[0], -1.0

        weighted_scores = [r.weighted_score for r in results]
        median_score = statistics.median(weighted_scores)
        stability = round(statistics.stdev(weighted_scores), 3) if len(weighted_scores) > 1 else 0.0

        # Pick the result closest to median
        best = min(results, key=lambda r: abs(r.weighted_score - median_score))

        # For each dimension, take median of this dimension's scores across repeats
        all_dims = set()
        for r in results:
            all_dims.update(r.scores.keys())
        median_scores: dict[str, float] = {}
        for dim in sorted(all_dims):
            dim_scores = [r.scores.get(dim, 3.0) for r in results]
            median_scores[dim] = round(statistics.median(dim_scores), 1)

        # Update the best result with median scores and stability
        best.scores = median_scores
        best.weighted_score = round(median_score, 2)
        best.score_stability = stability

        min_dim = min(median_scores.values()) if median_scores else 3.0
        best.passed = best.weighted_score >= pass_threshold and min_dim >= 3.0
        if not best.critique_text:
            best.critique_text = results[0].critique_text

        profiles_used = list(dict.fromkeys(r.reviewer_profile for r in results))
        best.score_stability = stability
        best.raw_response = json.dumps({
            "aggregation": "median",
            "num_reviewers": len(results),
            "profiles": profiles_used,
            "stability": stability,
            "individual_scores": {r.reviewer_profile: r.weighted_score for r in results},
        }, ensure_ascii=False)

        return best, stability


# Keep backward compatibility shims
def _get_competitiveness(candidate: dict | None) -> float | None:
    if candidate is None:
        return None
    scores = candidate.get("scores", {})
    if not isinstance(scores, dict):
        return None
    comp = scores.get("competitiveness")
    if comp is None:
        return None
    try:
        return float(comp)
    except (TypeError, ValueError):
        return None
