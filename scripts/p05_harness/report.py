from __future__ import annotations

from pathlib import Path

from scripts.p05_harness.domain_prompts import get_prompts
from scripts.p05_harness.loop_runner import HarnessResult
from scripts.p05_harness.validators.rubric import RUBRIC_DIMENSIONS

_VERDICT_LABEL = {
    "scooped": "❌ scooped（被抢先）",
    "crowded": "⚠️ crowded（拥挤）",
    "adjacent": "ℹ️ adjacent（邻近）",
    "clear": "✅ clear（清晰）",
    "insufficient_evidence": "❓ insufficient_evidence（证据不足，非确认新颖）",
}

_SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低"}


def generate_report(result: HarnessResult, output_path: Path) -> None:
    """Generate an acceptance report in Markdown."""

    dim_keys = list(RUBRIC_DIMENSIONS.keys())

    lines = []
    lines.append(get_prompts().report_title_template.format(harness_name=get_prompts().harness_name))
    lines.append("")
    lines.append(f"**验收时间**: {_now()}")
    lines.append(f"**方法**: LLM 生成 + 批判-修正循环 + MCP 文献补充搜索 + 对抗性新颖性验证 + 方法论红队")
    lines.append("")

    # Summary stats
    lines.append("## 总体统计")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 候选方向总数 | {len(result.candidates)} |")
    lines.append(f"| 验收通过 | **{result.passed_count}** |")
    lines.append(f"| 需人工复核 | {result.failed_count} |")
    lines.append(f"| LLM 调用次数 | {result.total_llm_calls} |")
    lines.append(f"| MCP 调用次数 | {result.total_mcp_calls} |")
    lines.append(f"| 总耗时 | {result.total_duration_s:.1f}s |")
    lines.append("")

    # Dimension averages
    if result.dimension_averages:
        lines.append("## 各维度平均分")
        lines.append("")
        lines.append("| 维度 | 权重 | 平均分 |")
        lines.append("|------|------|--------|")
        for dim_key, dim_info in RUBRIC_DIMENSIONS.items():
            avg = result.dimension_averages.get(dim_key, 0)
            bar = _score_bar(avg)
            lines.append(f"| {dim_info['label_zh']} | {dim_info['weight']} | {avg:.1f}/5.0 {bar} |")
        lines.append("")

    # Candidate overview
    lines.append(f"## 深度分析候选方向 ({len(result.candidates)} 个)")
    lines.append("")
    lines.append("| 候选ID | 方法 | 疾病 | 原始分 | 最终分 | 新颖性判定 | 红队发现 | 轮次 | 状态 |")
    lines.append("|--------|------|------|--------|--------|------------|----------|------|------|")

    for cr in result.candidates:
        iterations = len(cr.iterations)
        status = "✅ 通过" if cr.passed else "⚠️ 需复核"
        nv = cr.novelty_verdict or {}
        verdict = nv.get("overall_verdict", "-")
        verdict_short = _VERDICT_LABEL.get(verdict, verdict)
        papers_n = nv.get("papers_found", 0)
        rt = cr.redteam_result or {}
        rt_summary = (
            f"{rt.get('high_count', 0)}H/{rt.get('medium_count', 0)}M/{rt.get('low_count', 0)}L"
            if rt else "-"
        )
        lines.append(
            f"| {cr.candidate_id} | {cr.method} | {cr.disease} | "
            f"{cr.combined_score:.3f} | {cr.final_score:.2f}/5.0 | "
            f"{verdict_short} ({papers_n}篇) | {rt_summary} | {iterations} | {status} |"
        )
    lines.append("")

    # Iteration details for deep analysis candidates
    lines.append("## 迭代详情")
    lines.append("")

    dim_header = " | ".join(RUBRIC_DIMENSIONS[k]["label_zh"] for k in dim_keys)
    dim_sep = "|" + "------|" * (len(dim_keys) + 3)

    for cr in result.candidates:
        if cr.iterations:
            lines.append(f"### {cr.candidate_id} — {cr.method} × {cr.disease}")
            lines.append("")
            lines.append(f"**研究问题**: {cr.research_question}")
            lines.append("")
            lines.append(f"| 轮次 | {dim_header} | 加权分 | 通过 |")
            lines.append(dim_sep)

            for it in cr.iterations:
                scores = it.get("scores", {})
                cells = " | ".join(str(scores.get(k, "-")) for k in dim_keys)
                ws = it.get("weighted_score", 0)
                passed = "✅" if it.get("passed") else "❌"
                lines.append(f"| {it['iteration']} | {cells} | {ws:.2f} | {passed} |")

            lines.append("")

            # ── 新颖性验证结果 ──
            nv = cr.novelty_verdict or {}
            if nv.get("overall_verdict"):
                lines.append(
                    f"**新颖性判定**: {_VERDICT_LABEL.get(nv['overall_verdict'], nv['overall_verdict'])}"
                    f"（检索 {nv.get('papers_found', 0)} 篇）"
                    + (" — *refine 后对最终方案复验*" if nv.get("reverified_post_refine") else "")
                )
                nvi = cr.novelty_verdict_initial or {}
                if nvi.get("overall_verdict") and nvi.get("overall_verdict") != nv.get("overall_verdict"):
                    lines.append(
                        f"  - 初始方案判定: {_VERDICT_LABEL.get(nvi['overall_verdict'], nvi['overall_verdict'])}"
                        f"（refine 前）"
                    )
                for vd in nv.get("verdicts", []):
                    vlabel = _VERDICT_LABEL.get(vd.get("verdict", ""), vd.get("verdict", ""))
                    lines.append(f"  - {vlabel} — {vd.get('claim', '')[:100]}")
                    if vd.get("closeness"):
                        lines.append(f"    - {vd['closeness'][:200]}")
                    for w in (vd.get("closest_works") or [])[:3]:
                        doi = f" (doi:{w['doi']})" if w.get("doi") else ""
                        lines.append(
                            f"    - 📄 {w.get('title', 'N/A')[:80]}"
                            f" ({w.get('authors', '')}, {w.get('year', '')}){doi}"
                        )
                lines.append("")

            # ── 红队评审结果 ──
            rt = cr.redteam_result or {}
            if rt:
                lines.append(
                    f"**红队发现**: {rt.get('high_count', 0)} 高 / {rt.get('medium_count', 0)} 中 / "
                    f"{rt.get('low_count', 0)} 低 | 数据声明: {rt.get('verified_claims', 0)} 核实, "
                    f"{len(rt.get('unverified_claims', []))} 未核实"
                    + (" — *refine 后对最终方案复验*" if rt.get("reverified_post_refine") else "")
                )
                for f in rt.get("findings", []):
                    sev = _SEVERITY_LABEL.get(f.get("severity", ""), f.get("severity", ""))
                    lines.append(f"  - **[{sev}] {f.get('check', '')}**: {f.get('detail', '')[:200]}")
                # 纯规模声明（如"19数据集"）无标识符无法核实，仅展示含具体标识符的数据源声明
                shown_claims = [
                    c for c in rt.get("unverified_claims", [])
                    if c.get("claim_type") == "data_source" or c.get("identifiers")
                ]
                for c in shown_claims[:8]:
                    lines.append(f"  - [待核实] {c.get('claim_text', '')}")
                lines.append("")

            # Gap papers found
            if cr.gap_papers_found > 0:
                lines.append(f"**MCP补充文献**: 发现 {cr.gap_papers_found} 篇")
                lines.append("")

            # Literature coverage
            lc = cr.literature_coverage
            if lc:
                src_note = ""
                if lc.get("evidence_source") == "fallback_pool":
                    src_note = " [无标签证据卡, 已回退到全库证据卡池]"
                lines.append(f"**文献覆盖度**: {lc.get('status', 'N/A')} "
                           f"(引用 {lc.get('cited_paper_count', 0)} 篇, "
                           f"证据卡 {lc.get('evidence_card_count', 0)} 篇, "
                           f"重叠 {lc.get('overlapping_count', 0)}){src_note}")
                lines.append("")

            # Completeness
            comp = cr.completeness
            if comp and comp.get("issues_count", 0) > 0:
                lines.append(f"**结构问题**: {comp.get('issues_count', 0)} 项")
                for mf in comp.get("missing_fields", []):
                    lines.append(f"  - 缺失字段: {mf}")
                for ef in comp.get("empty_fields", []):
                    lines.append(f"  - 空字段: {ef}")
                lines.append("")

    # Citation verification
    lines.append("## 引用验证")
    lines.append("")

    any_citations = False
    for cr in result.candidates:
        if cr.citation_checks:
            any_citations = True
            verified = sum(1 for c in cr.citation_checks if c.get("exists"))
            not_found = sum(1 for c in cr.citation_checks
                          if not c.get("exists") and c.get("status") != "unverifiable")
            unverifiable = sum(1 for c in cr.citation_checks if c.get("status") == "unverifiable")
            total = len(cr.citation_checks)
            status_icon = "✅" if not_found == 0 else "⚠️"
            lines.append(
                f"- {status_icon} **{cr.candidate_id}**: {verified}/{total} 验证通过"
                f"（疑似幻觉 {not_found}，待人工核实 {unverifiable}）"
            )
            for cc in cr.citation_checks:
                disp = cc.get("display") or cc.get("doi") or cc.get("pmid") or cc.get("accession") or "?"
                if cc.get("exists"):
                    continue
                icon = "❓" if cc.get("status") == "unverifiable" else "❌"
                if cc.get("error"):
                    lines.append(f"  - {icon} {disp}: {cc.get('error')}")
    if not any_citations:
        lines.append("（方案中未提取到可验证的引用）")

    lines.append("")

    # Failed candidates requiring manual review
    failed = [cr for cr in result.candidates if not cr.passed]
    if failed:
        lines.append("## 需人工复核的候选方向")
        lines.append("")
        for cr in failed:
            lines.append(f"### {cr.candidate_id}")
            lines.append(f"**研究问题**: {cr.research_question}")
            lines.append(f"**评分**: {cr.final_score:.2f}/5.0")
            if cr.final_critique:
                lines.append(f"**评审意见**: {cr.final_critique.critique_text[:500]}")
            if cr.error:
                lines.append(f"**错误**: {cr.error}")
            lines.append("")

    lines.append("---")
    lines.append("*本报告由 P05 Research Plan Quality Harness 自动生成*")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _score_bar(score: float, max_val: float = 5.0) -> str:
    ratio = min(score / max_val, 1.0)
    filled = int(ratio * 10)
    empty = 10 - filled
    return "█" * filled + "░" * empty


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M")
