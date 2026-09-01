"""Generate a human-readable Markdown learning report from AIscience run results.

The report aggregates all 7 project outputs into a single document suitable for
literature review, thesis topic exploration, and research direction comparison.

Usage:
    python scripts/generate_learning_report.py [--report-dir data]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_NAMES: dict[str, str] = {
    "p01_gwas_perturb_seq": "01 — GWAS + Perturb-seq 整合因果基因鉴定",
    "p02_gwas_spatial": "02 — GWAS + Spatial Transcriptomics 组织定位",
    "p03_gwas_scatac": "03 — GWAS + scATAC-seq 染色质调控机制",
    "p04_prs_advance": "04 — 跨祖先多基因风险评分(PRS)方法优化",
    "p05_sc_multiomics_ai": "05 — 单细胞多组学基础模型基准评测",
    "p06_digital_immune": "06 — 数字免疫学: 系统疫苗学与免疫组学",
    "p07_aging_clock": "07 — 表观遗传时钟与衰老生物标志物",
    "p09_spatial_gwas_network": "09 — scGWAS × 空间转录组网络模块发现",
}

ARCHETYPE_NAMES: dict[str, str] = {
    "archetype_a_v2g": "V2G (Variant-to-Gene)",
    "archetype_b_prs": "PRS (Polygenic Risk Score)",
    "archetype_c_sc_ai": "scAI (Single-cell AI)",
    "archetype_d_omics_score": "Omics Score (Multi-omics Biomarker)",
    "archetype_e_cross_ethnic": "Cross-Ethnic (Multi-omics Portability)",
    "archetype_f_spatial_gwas": "Spatial GWAS Network (scGWAS × ST)",
}

GAP_PATTERN_DESCRIPTIONS: dict[str, str] = {
    "P1": "缺失公共数据引用",
    "P2": "单模态证据不足，缺乏三角验证",
    "P3": "覆盖矩阵空缺 (trait×locus×modality×celltype×ancestry)",
    "P4": "基因调控网络未构建",
    "P5": "缺乏精细定位 (fine-mapping)",
    "P6": "缺乏共定位分析 (colocalization)",
    "P7": "缺少团队/方法命名",
    "P8": "缺乏独立复制队列验证",
    "P9": "缺乏公共数据编号引用",
    "P10": "跨领域桥接未探索",
}

THEME_COLORS = {
    "v2g": ("#1f77b4", "GWAS → 基因"),
    "prs": ("#ff7f0e", "PRS 方法"),
    "sc_ai": ("#2ca02c", "单细胞 AI"),
    "omics_score": ("#d62728", "多组学评分"),
}


def load_project_report(project_id: str, projects_dir: Path) -> dict[str, Any]:
    path = projects_dir / project_id / "output" / "final_report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def format_score(val: float, label: str = "score") -> str:
    if val >= 0.8:
        emoji = "🟢"
    elif val >= 0.6:
        emoji = "🟡"
    elif val >= 0.4:
        emoji = "🟠"
    else:
        emoji = "🔴"
    return f"{emoji} **{val:.2f}** ({label})"


def format_impact(val: str) -> str:
    m = {"high": "🔴 High", "medium": "🟡 Medium", "low": "🟢 Low",
         "transformative": "🔥 Transformative"}
    for k, v in m.items():
        if k in val.lower():
            return v
    return val


def build_gaps_section(gaps: list[dict[str, Any]]) -> str:
    if not gaps:
        return "*(无 gaps 识别)*\n"

    lines: list[str] = []
    lines.append("| # | Gap ID | Pattern | 描述 | 分数 | 可行性 | 竞争度 | 跨领域 |")
    lines.append("|---|--------|---------|------|------|--------|--------|--------|")
    for i, g in enumerate(gaps, 1):
        pat = g.get("pattern_id", "")
        desc = g.get("description", "")
        pat_label = GAP_PATTERN_DESCRIPTIONS.get(pat, pat)
        lines.append(
            f"| {i} | `{g.get('gap_id','')}` | {pat_label} "
            f"| {desc} "
            f"| {g.get('score',0):.2f} "
            f"| {g.get('feasibility',0):.2f} "
            f"| {g.get('competition',0):.2f} "
            f"| {g.get('cross_archetype',0):.1f} |"
        )
    return "\n".join(lines)


def build_hypotheses_section(hypotheses: list[dict[str, Any]]) -> str:
    if not hypotheses:
        return "*(无 hypotheses 生成)*\n"

    lines: list[str] = []
    for h in hypotheses:
        hid = h.get("hypothesis_id", "?")
        statement = h.get("statement", "")
        rationale = h.get("rationale", "")
        methods = h.get("required_methods", [])
        datasets = h.get("required_datasets", [])
        novelty = h.get("novelty_score", 0)
        feasibility = h.get("feasibility_score", 0)
        impact = h.get("expected_impact", "")
        addresses = h.get("addresses_gap", "")

        lines.append(f"<details>\n<summary><strong>{hid}</strong>: {statement[:120]}…</summary>\n\n")
        lines.append(f"**完整陈述**: {statement}\n")
        lines.append(f"**针对 Gap**: `{addresses}`\n")
        lines.append(f"**理论依据**: {rationale}\n")
        lines.append("**所需方法**:\n")
        for m in methods:
            lines.append(f"- `{m}`\n")
        lines.append("**所需数据集**:\n")
        for d in datasets:
            lines.append(f"- {d}\n")
        lines.append(f"**创新性**: `{novelty:.2f}` | **可行性**: `{feasibility:.2f}` | **预期影响**: {format_impact(impact)}\n")
        lines.append("</details>\n\n")

    return "".join(lines)


def build_evidence_cards_table(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return ""
    # deduplicate by pmid
    seen: set[str] = set()
    unique_cards: list[dict[str, Any]] = []
    for c in cards:
        pmid = c.get("paper_pmid", "")
        if pmid and pmid not in seen:
            seen.add(pmid)
            unique_cards.append(c)
        elif not pmid:
            unique_cards.append(c)

    lines: list[str] = []
    lines.append("| 文献 | 年份 | 关键发现 | 方法 | PMID/DOI |\n")
    lines.append("|------|------|----------|------|----------|\n")
    for c in unique_cards[:20]:
        title = c.get("paper_title", "?")[:60]
        year = c.get("paper_year", "?")
        finding = c.get("key_finding", "")[:100]
        method = c.get("method_brief", "")[:60]
        pmid = c.get("paper_pmid", "")
        doi = c.get("paper_doi", "")
        ref = f"PMID:{pmid}" if pmid else f"DOI:{doi}" if doi else "—"
        lines.append(f"| {title} | {year} | {finding} | {method} | {ref} |\n")
    return "".join(lines)


def build_cross_archetype_section(scan: dict[str, Any]) -> str:
    lines: list[str] = []
    bridges = scan.get("cross_archetype_bridge_gaps", [])
    if bridges:
        lines.append("### 🌉 跨领域桥接 Gap 模式\n\n")
        lines.append("这些 Gap 同时出现在多个项目中，是交叉学科研究的最佳切入点：\n\n")
        lines.append("| Pattern | 描述 | 出现项目 | 频次 |\n")
        lines.append("|---------|------|----------|------|\n")
        for b in sorted(bridges, key=lambda x: -x.get("count", 0)):
            pat = b.get("pattern_id", "")
            desc = GAP_PATTERN_DESCRIPTIONS.get(pat, pat)
            projs = b.get("appears_in_projects", [])
            proj_names = ", ".join(str(PROJECT_NAMES.get(p, p)).split("—")[0].strip() for p in projs)
            lines.append(f"| {pat} | {desc} | {proj_names} | {b.get('count',0)} |\n")

        lines.append("\n**跨领域桥接分数解读**:\n\n")
        lines.append("| Pattern | 含义 | 选题建议 |\n")
        lines.append("|---------|------|----------|\n")
        lines.append("| **P10** 跨领域桥接 | 7个项目全部未探索跨领域融合 | 🔥 最佳选题方向: PRS + 单细胞AI + GWAS\n")
        lines.append("| **P9** 公共数据引用 | 所有项目都缺失数据编号引用 | 数据科学/可重复性方向\n")
        lines.append("| **P6** 共定位分析 | 大部分GWAS相关项目缺乏colocalization | 方法学改进方向\n")
        lines.append("| **P5** 精细定位 | 大部分GWAS项目缺乏fine-mapping | 统计遗传学方向\n")
        lines.append("| **P8** 复制验证 | 所有项目都缺乏独立复制 | 验证性研究\n")
        lines.append("| **P3** 覆盖空缺 | 组合维度的覆盖矩阵有大量空缺 | 数据生成方向\n")
        lines.append("| **P2** 单模态验证不足 | 特定locus仅单模态证据 | 深度验证方向\n\n")
    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate learning report from AIscience results")
    parser.add_argument("--report-dir", default="data", help="report output directory")
    parser.add_argument("--output", default="learning_report.md", help="output filename")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    report_dir = base_dir / args.report_dir
    projects_dir = base_dir / "projects"

    # Load combined report
    combined_path = report_dir / "run_all_report.json"
    combined: dict[str, Any] = {}
    if combined_path.exists():
        combined = json.loads(combined_path.read_text(encoding="utf-8"))

    # Load cross-archetype scan
    scan_path = report_dir / "cross_archetype_gap_scan.json"
    scan: dict[str, Any] = {}
    if scan_path.exists():
        scan = json.loads(scan_path.read_text(encoding="utf-8"))

    # Determine which projects were run
    result_projects: list[str] = []
    for r in combined.get("results", []):
        pid = r.get("project_id", "")
        if pid:
            result_projects.append(pid)

    if not result_projects:
        # fallback: try all known projects
        result_projects = list(PROJECT_NAMES.keys())

    # Load individual project reports
    project_data: dict[str, dict[str, Any]] = {}
    for pid in result_projects:
        project_data[pid] = load_project_report(pid, projects_dir)

    # Build markdown
    md: list[str] = []

    md.append(f"# AIscience 开题学习报告\n\n")
    md.append(f"> 生成时间: 由 AIscience 系统自动生成\n\n")

    # ── 1. Overview ──
    md.append("## 📊 总览\n\n")
    if combined:
        md.append(f"- **运行项目数**: {combined.get('projects_run', '?')}")
        md.append(f"- **成功项目数**: {combined.get('projects_succeeded', '?')}")
        md.append(f"- **总 Evidence Cards**: {combined.get('total_cards', '?')}")
        md.append(f"- **总 Gaps**: {combined.get('total_gaps', '?')}")
        md.append(f"- **总 Hypotheses**: {combined.get('total_hypotheses', '?')}")
        md.append(f"- **总耗时**: {combined.get('total_duration_s', '?'):.1f}s\n\n")

    # ── 2. Project Summary Table ──
    md.append("## 📋 项目一览\n\n")
    md.append("| 项目 | Archetype | Cards | Gaps | Hyps | 状态 |\n")
    md.append("|------|-----------|-------|------|------|------|\n")
    for r in combined.get("results", []):
        pid = r.get("project_id", "")
        name = PROJECT_NAMES.get(pid, pid)
        arch = ARCHETYPE_NAMES.get(r.get("archetype_id", ""), r.get("archetype_id", ""))
        ok = "✅" if r.get("success") else "❌"
        md.append(f"| {name} | {arch} | {r.get('total_cards','?')} | {r.get('gap_count','?')} | {r.get('hypothesis_count','?')} | {ok} |\n")
    md.append("\n")

    # ── 3. Detailed per-project sections ──
    md.append("---\n\n")
    md.append("## 🔬 各研究方向详细分析\n\n")

    for r in combined.get("results", []):
        pid = r.get("project_id", "")
        name = PROJECT_NAMES.get(pid, pid)
        arch = ARCHETYPE_NAMES.get(r.get("archetype_id", ""), r.get("archetype_id", ""))

        # Get detailed data from individual report
        detail = project_data.get(pid, {})
        research_dir = detail.get("research_direction", "").strip()
        gaps = detail.get("gaps", [])
        hypotheses = detail.get("hypotheses", [])
        evidence_path = projects_dir / pid / "output" / "evidence_cards.jsonl"

        md.append(f"### {name}\n\n")
        md.append(f"**Archetype**: `{arch}` | **Project ID**: `{pid}`\n\n")

        if research_dir:
            md.append(f"**研究方向描述**:\n\n> {research_dir}\n\n")

        md.append(f"**统计**: Cards={r.get('total_cards','?')}, Gaps={len(gaps)}, Hypotheses={len(hypotheses)}\n\n")

        # Gaps
        md.append(f"#### 🕳️ 识别的 Gaps ({len(gaps)})\n\n")
        md.append(build_gaps_section(gaps))
        md.append("\n\n")

        # Hypotheses
        md.append(f"#### 💡 生成的研究假设 ({len(hypotheses)})\n\n")
        md.append(build_hypotheses_section(hypotheses))
        md.append("\n\n")

        # Evidence Cards
        if evidence_path.exists():
            cards: list[dict[str, Any]] = []
            with evidence_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        cards.append(json.loads(line))
            if cards:
                md.append(f"#### 📄 关键文献 ({len(cards)} 篇)\n\n")
                md.append(build_evidence_cards_table(cards))
                md.append("\n\n")

        md.append("---\n\n")

    # ── 4. Cross-archetype analysis ──
    if scan:
        md.append(build_cross_archetype_section(scan))
        md.append("\n---\n\n")

    # ── 5. Thesis topic suggestions ──
    md.append("## 🎯 开题方向建议\n\n")
    md.append("基于上述分析，以下是最值得考虑的选题方向（按推荐优先级排序）：\n\n")

    md.append("### 🥇 Tier 1: 跨领域融合（最高创新性）\n\n")
    md.append("| 选题方向 | 涉及项目 | 创新性 | 可行性 | 理由 |\n")
    md.append("|----------|----------|--------|--------|------|\n")
    md.append("| PRS + 单细胞AI融合 | P04 + P05 | 🔥 高 | 🟡 中 | 两个领域独立发展但几乎无交叉，P10跨领域桥接gap\n")
    md.append("| 空间转录组 + scATAC 联合分析 | P02 + P03 | 🔥 高 | 🟡 中 | 空间组织 + 染色质调控，机制理解突破\n")
    md.append("| 多模态衰老时钟 | P06 + P07 | 🔥 高 | 🟢 高 | 免疫 + 表观遗传，临床转化潜力大\n\n")

    md.append("### 🥈 Tier 2: 方法学创新\n\n")
    md.append("| 选题方向 | 适合领域 | 创新性 | 可行性 | 理由 |\n")
    md.append("|----------|----------|--------|--------|------|\n")
    md.append("| 大规模colocalization方法学 | 统计遗传学 | 🟢 高 | 🟢 高 | P6 gap在所有GWAS项目中存在，但方法成熟\n")
    md.append("| 跨祖先fine-mapping | 群体遗传学 | 🟡 中 | 🟡 中 | P5 gap普遍，PRS-CSx等方法但数据限制\n")
    md.append("| 单细胞基础模型泛化性评测 | 计算生物学 | 🟢 高 | 🟢 高 | P10+P3 gap，可做benchmark\n\n")

    md.append("### 🥉 Tier 3: 深度挖掘\n\n")
    md.append("| 选题方向 | 适合领域 | 创新性 | 可行性 | 理由 |\n")
    md.append("|----------|----------|--------|--------|------|\n")
    md.append("| IL2RA等locus深度机制研究 | 分子生物学 | 🟡 中 | 🟢 高 | P2 gap揭示了locus层面的验证不足\n")
    md.append("| 免疫衰老多组学标志物 | 免疫组学 | 🟢 高 | 🟡 中 | P06+P07的结合点\n")
    md.append("| 疫苗应答的多模态预测模型 | 系统疫苗学 | 🟡 中 | 🟡 中 | 数字免疫学方向的核心gap\n\n")

    # ── Write ──
    output_path = report_dir / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(md), encoding="utf-8")
    print(f"[OK] 学习报告已生成: {output_path}")
    print(f"   总字数: {len(''.join(md))} 字符")


if __name__ == "__main__":
    main()
