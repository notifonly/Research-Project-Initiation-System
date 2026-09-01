from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REQUIRED_FIELDS = {
    "summary_zh": "中文摘要",
    "technical_roadmap": "技术路线",
    "data_sources_detail": "数据来源详情",
    "feasibility": "可行性评估",
    "innovation_points": "创新点",
    "expected_outputs": "预期产出",
}

FEASIBILITY_SUB_FIELDS = {
    "data_accessibility": "数据可及性",
    "compute_requirements": "计算需求",
    "technical_difficulty": "技术难度",
    "timeline_months": "预估周期",
    "key_risks": "关键风险",
    "mitigation": "缓解措施",
}

ROADMAP_STEP_FIELDS = {"title", "desc", "methods"}


@dataclass
class CompletenessResult:
    missing_fields: list[str] = field(default_factory=list)
    empty_fields: list[str] = field(default_factory=list)
    feasibility_issues: list[str] = field(default_factory=list)
    roadmap_issues: list[str] = field(default_factory=list)
    is_complete: bool = True
    issues_count: int = 0


def check_completeness(plan: dict[str, Any]) -> CompletenessResult:
    """Non-LLM structural validation: all required fields present and non-empty."""
    result = CompletenessResult()

    for field, label in REQUIRED_FIELDS.items():
        if field not in plan:
            result.missing_fields.append(f"{field}({label})")
            result.is_complete = False
        elif not plan[field]:
            result.empty_fields.append(f"{field}({label})")
            result.is_complete = False

    if "feasibility" in plan and isinstance(plan["feasibility"], dict):
        feas = plan["feasibility"]
        for sub_field, label in FEASIBILITY_SUB_FIELDS.items():
            if sub_field not in feas or not feas[sub_field]:
                result.feasibility_issues.append(f"feasibility.{sub_field}({label})缺少")

    if "technical_roadmap" in plan:
        roadmap = plan["technical_roadmap"]
        if isinstance(roadmap, list):
            if len(roadmap) == 0:
                result.roadmap_issues.append("技术路线为空")
            for i, step in enumerate(roadmap):
                if not isinstance(step, dict):
                    result.roadmap_issues.append(f"Step {i+1} 不是有效对象")
                    continue
                for sf in ROADMAP_STEP_FIELDS:
                    if sf not in step or not step[sf]:
                        result.roadmap_issues.append(f"Step {i+1} 缺少 {sf}")
        else:
            result.roadmap_issues.append("技术路线不是列表格式")

    result.issues_count = (
        len(result.missing_fields)
        + len(result.empty_fields)
        + len(result.feasibility_issues)
        + len(result.roadmap_issues)
    )

    if result.issues_count > 0:
        result.is_complete = False

    return result
