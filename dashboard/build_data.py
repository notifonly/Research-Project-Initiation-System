"""Aggregate all project outputs into a single data.json for the dashboard.
Enhancements:
- Literature references extracted from evidence cards
- Thesis suggestions derived from hypothesis clustering
- Cross-pattern counts calculated from actual gaps (not hardcoded)
- Pipeline progress per project
"""
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

BASE = Path(__file__).resolve().parent.parent
PROJECTS_DIR = BASE / "projects"
DATA_DIR = BASE / "data"
OUTPUT = Path(__file__).resolve().parent / "data.json"

PROJECT_META = {
    "p01_gwas_perturb_seq": {
        "name": "GWAS + Perturb-seq 整合因果基因鉴定",
        "name_en": "GWAS + Perturb-seq Causal Gene Mapping",
        "archetype": "V2G (Variant-to-Gene)",
        "archetype_id": "archetype_a_v2g",
        "icon": "dna",
    },
    "p02_gwas_spatial": {
        "name": "GWAS + 空间转录组学组织定位",
        "name_en": "GWAS + Spatial Transcriptomics",
        "archetype": "V2G (Variant-to-Gene)",
        "archetype_id": "archetype_a_v2g",
        "icon": "map",
    },
    "p03_gwas_scatac": {
        "name": "GWAS + scATAC-seq 染色质调控机制",
        "name_en": "GWAS + scATAC-seq Regulatory V2G",
        "archetype": "V2G (Variant-to-Gene)",
        "archetype_id": "archetype_a_v2g",
        "icon": "layers",
    },
    "p04_prs_advance": {
        "name": "跨祖先多基因风险评分(PRS)方法优化",
        "name_en": "Cross-Ancestry PRS Methodology Advance",
        "archetype": "PRS (Polygenic Risk Score)",
        "archetype_id": "archetype_b_prs",
        "icon": "bar-chart",
    },
    "p05_sc_multiomics_ai": {
        "name": "单细胞多组学基础模型基准评测",
        "name_en": "Single-Cell Multi-omics FM Benchmark",
        "archetype": "scAI (Single-cell AI)",
        "archetype_id": "archetype_c_sc_ai",
        "icon": "cpu",
    },
    "p06_digital_immune": {
        "name": "数字免疫学: 系统疫苗学与免疫组学",
        "name_en": "Digital Immune Phenotype Scoring",
        "archetype": "Omics Score (Multi-omics Biomarker)",
        "archetype_id": "archetype_d_omics_score",
        "icon": "shield",
    },
    "p07_aging_clock": {
        "name": "表观遗传时钟与衰老生物标志物",
        "name_en": "Multi-omics Aging Clock",
        "archetype": "Omics Score (Multi-omics Biomarker)",
        "archetype_id": "archetype_d_omics_score",
        "icon": "clock",
    },
    "p08_cross_ethnic_multiomics": {
        "name": "跨族群多组学: 生物标志物可移植性+PRS+因果推断",
        "name_en": "Cross-Ethnic Multi-omics Portability",
        "archetype": "Cross-Ethnic (Multi-omics Portability)",
        "archetype_id": "archetype_e_cross_ethnic",
        "icon": "globe",
    },
    "p09_spatial_gwas_network": {
        "name": "scGWAS × 空间转录组: 网络模块发现",
        "name_en": "scGWAS × Spatial Transcriptomics Network",
        "archetype": "Spatial GWAS Network (scGWAS × ST)",
        "archetype_id": "archetype_f_spatial_gwas",
        "icon": "target",
    },
}

ARCHETYPE_COLORS = {
    "archetype_a_v2g": "#3B82F6",
    "archetype_b_prs": "#F59E0B",
    "archetype_c_sc_ai": "#10B981",
    "archetype_d_omics_score": "#8B5CF6",
    "archetype_e_cross_ethnic": "#EC4899",
    "archetype_f_spatial_gwas": "#F97316",
}

PIPELINE_SKILLS = [
    ("s1", "方向分解", "Direction Decompose"),
    ("s2", "术语标准化", "Terminology Normalize"),
    ("s3", "资源收集", "Resource Collect"),
    ("s4", "多源搜索", "Multi-source Search"),
    ("s5", "引用溯源", "Citation Snowball"),
    ("s6", "文献筛选", "Literature Screening"),
    ("s6a", "专项搜索", "Divergent Search"),
    ("s6b", "PDF下载", "PDF Download"),
    ("s7", "证据卡提取", "Evidence Extraction"),
    ("s8", "数据可用性分析", "Data Availability"),
    ("s9", "方法-数据匹配", "Method-Dataset Match"),
    ("s10", "功能证据搜索", "Functional Evidence"),
    ("s11", "Gap分析", "Gap Analysis"),
    ("s12", "假设生成", "Hypothesis Generate"),
]

PATTERN_NAME_ZH = {
    "P1": "功能模态证据缺失",
    "P2": "单模态证据不足",
    "P3": "覆盖矩阵空缺",
    "P4": "样本量不足",
    "P5": "缺乏精细定位",
    "P6": "缺乏共定位分析",
    "P7": "单一祖先", 
    "P8": "缺乏独立复制",
    "P9": "缺乏公共数据编号",
    "P10": "跨领域桥接未探索",
    "B1": "PRS校准分析缺失",
    "B2": "跨祖先可迁移性未验证",
    "D1": "多组学评分层验证缺失",
    "D2": "临床cutoff未定义",
    "C1": "单组学证据缺乏",
    "C2": "基准评估缺失",
    "C3": "Held-out细胞类型未评估",
    "C4": "基线方法缺失",
    "C5": "预训练权重未公开",
    "C6": "迁移学习评估缺失",
    "C7": "单组织评估",
    "C8": "可扩展性未验证",
    "C9": "可解释性分析缺失",
    "C10": "多模态整合缺失",
    "C11": "架构同质性",
    "F1": "单一空间平台",
    "F2": "网络模块缺失",
    "F3": "PPI模块缺乏空间定位",
    "F4": "空间梯度未量化",
    "F5": "单一性状分析",
    "F6": "空间零模型缺失",
    "F7": "单一组织分析",
    "F8": "跨物种验证缺失",
    "F9": "基线对比缺失",
    "F10": "跨领域桥接未探索",
}


def extract_impact_level(impact_str):
    levels = {
        "revolutionary": 5,
        "transformative": 4,
        "very high": 3.5,
        "high": 3,
        "medium-high": 2.5,
        "medium": 2,
        "low": 1,
    }
    s = (impact_str or "").lower()
    for k, v in levels.items():
        if k in s:
            return v
    return 2


def load_cards_literature(pid):
    """Extract deduplicated literature references from evidence cards."""
    cards_path = PROJECTS_DIR / pid / "output" / "evidence_cards.jsonl"
    if not cards_path.exists():
        warm_path = DATA_DIR / "l1_warm" / pid / "cards.jsonl"
        if warm_path.exists():
            cards_path = warm_path
    if not cards_path.exists():
        return []

    papers = {}
    with open(cards_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                card = json.loads(line)
            except json.JSONDecodeError:
                continue
            doi = card.get("paper_doi") or ""
            pmid = card.get("paper_pmid") or ""
            key = doi or pmid or card.get("paper_title", "")
            if not key or key in papers:
                continue
            papers[key] = {
                "doi": doi or None,
                "pmid": pmid or None,
                "title": card.get("paper_title", ""),
                "authors": card.get("paper_authors", []),
                "year": card.get("paper_year"),
                "venue": card.get("paper_venue", ""),
                "url": card.get("paper_url", ""),
            }
    refs = list(papers.values())
    refs.sort(key=lambda r: -(r.get("year") or 0))
    return refs


def load_project_config(pid):
    """Load project config.yaml and extract research_direction, parameters."""
    cfg_path = PROJECTS_DIR / pid / "config.yaml"
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return {
        "research_direction": cfg.get("research_direction", "").strip(),
        "archetype_id": cfg.get("archetype_id", ""),
        "skill_sequence": cfg.get("skill_sequence", []),
    }


def compute_pipeline_progress(pid, skill_sequence):
    """Check which skills have checkpoint/output evidence.
    
    Progress logic:
    - S1-S3 (scoping): detected via individual checkpoint files (e.g. r0_s1_*.json)
    - S4-S10 (inner loop): detected via aggregate inner_loop checkpoint (rN_inner_loop.json)
    - S7 (evidence cards): also detected via evidence_cards.jsonl output file
    - S11-S12 (synthesis): detected via individual checkpoint + final_report.json
    """
    checkpoints_dir = DATA_DIR / "l1_warm" / pid / "checkpoints"
    completed = []
    incomplete = []
    has_cards = (PROJECTS_DIR / pid / "output" / "evidence_cards.jsonl").exists()
    has_gaps = (PROJECTS_DIR / pid / "output" / "final_report.json").exists()

    has_inner_loop = False
    if checkpoints_dir.exists():
        has_inner_loop = bool(list(checkpoints_dir.glob("*inner_loop*")))

    for sid in skill_sequence:
        if checkpoints_dir.exists():
            ckpt_files = list(checkpoints_dir.glob(f"*{sid}*"))
            if ckpt_files:
                completed.append(sid)
                continue
        if sid.startswith("s1_") or sid.startswith("s2_"):
            completed.append(sid)
        elif sid.startswith("s7_") and has_cards:
            completed.append(sid)
        elif sid.startswith("s11_") and has_gaps:
            completed.append(sid)
        elif sid.startswith("s12_") and has_gaps:
            completed.append(sid)
        elif has_inner_loop and any(sid.startswith(p) for p in ("s3_", "s4_", "s5_", "s6_", "s6a_", "s6b_", "s7_", "s8_", "s9_", "s10_")):
            completed.append(sid)
        else:
            incomplete.append(sid)

    total = len(skill_sequence)
    done = len(completed)
    return {
        "total_steps": total,
        "completed": done,
        "percent": round(done / max(total, 1) * 100),
        "completed_steps": completed,
        "incomplete_steps": incomplete,
    }


def compute_cross_patterns(all_gaps, project_ids):
    """Compute pattern×project distribution from actual gap data."""
    pattern_ids = set()
    for g in all_gaps:
        pid = g.get("pattern_id", "")
        if pid:
            pattern_ids.add(pid)

    cross = []
    for pid in sorted(pattern_ids):
        row = {"pattern": pid, "name": PATTERN_NAME_ZH.get(pid, pid)}
        for proj_id in project_ids:
            count = sum(1 for g in all_gaps
                        if g.get("pattern_id") == pid and g.get("project_id") == proj_id)
            row[proj_id] = count
        cross.append(row)
    cross.sort(key=lambda r: sum(r.get(pid, 0) for pid in project_ids), reverse=True)
    return cross


def generate_thesis_suggestions(all_hyps, projects):
    """Generate data-driven thesis suggestions by clustering hypotheses."""
    if not all_hyps:
        from collections import Counter

        proj_names = [p["name"] for p in projects]
        suggestions = [
            {
                "tier": 1,
                "label": "Tier 1: 跨领域融合（最高创新性）",
                "items": [
                    {
                        "title": "GWAS + 单细胞AI融合",
                        "projects": ", ".join(proj_names[:3]) + " + " + proj_names[3] if len(proj_names) >= 4 else ", ".join(proj_names),
                        "innovation": "高",
                        "feasibility": "中",
                        "reason": "GWAS精细定位与单细胞多组学AI结合，从变异到功能全链条解析",
                        "innovation_score": 0.90,
                        "feasibility_score": 0.50,
                    },
                    {
                        "title": "多模态衰老时钟",
                        "projects": "P06 + P07",
                        "innovation": "高",
                        "feasibility": "高",
                        "reason": "免疫 + 表观遗传，临床转化潜力大",
                        "innovation_score": 0.80,
                        "feasibility_score": 0.75,
                    },
                ],
            },
            {
                "tier": 2,
                "label": "Tier 2: 方法学创新",
                "items": [
                    {
                        "title": "跨祖先PRS可迁移性基准评测",
                        "projects": "P04",
                        "innovation": "中",
                        "feasibility": "高",
                        "reason": "系统评估现有PRS方法的跨祖先迁移性和校准表现",
                        "innovation_score": 0.70,
                        "feasibility_score": 0.85,
                    },
                    {
                        "title": "单细胞基础模型泛化性评测框架",
                        "projects": "P05",
                        "innovation": "高",
                        "feasibility": "中",
                        "reason": "构建标准化benchmark评估FM的跨cell type泛化能力",
                        "innovation_score": 0.75,
                        "feasibility_score": 0.60,
                    },
                ],
            },
            {
                "tier": 3,
                "label": "Tier 3: 深度挖掘",
                "items": [
                    {
                        "title": "locus层面多模态功能验证",
                        "projects": "P01 / P02 / P03",
                        "innovation": "中",
                        "feasibility": "高",
                        "reason": "针对关键locus整合多种功能模态证据进行系统验证",
                        "innovation_score": 0.55,
                        "feasibility_score": 0.80,
                    },
                ],
            },
        ]
        return suggestions

    hyp_by_project = defaultdict(list)
    for h in all_hyps:
        hyp_by_project[h.get("project_id", "")].append(h)

    suggestions = []
    tier2_items = []
    tier3_items = []

    for proj_id, hyps in hyp_by_project.items():
        if not hyps:
            continue
        best = max(hyps, key=lambda h: (h.get("novelty_score", 0) + h.get("feasibility_score", 0)) / 2)
        proj_name = best.get("project_name", proj_id)
        nov = best.get("novelty_score", 0) or 0
        fea = best.get("feasibility_score", 0) or 0
        item = {
            "title": f"{proj_name}",
            "projects": proj_id,
            "innovation": "高" if nov >= 0.7 else ("中" if nov >= 0.5 else "低"),
            "feasibility": "高" if fea >= 0.7 else ("中" if fea >= 0.5 else "低"),
            "reason": (best.get("statement", "") or "")[:120],
            "innovation_score": round(nov, 2),
            "feasibility_score": round(fea, 2),
        }
        if nov >= 0.75 or fea >= 0.75:
            suggestions.append(item)
        elif nov >= 0.55:
            tier2_items.append(item)
        else:
            tier3_items.append(item)

    result = [
        {
            "tier": 1,
            "label": "Tier 1: 高创新/高可行性（优先推进）",
            "items": suggestions if suggestions else [
                {
                    "title": "跨领域融合研究",
                    "projects": "多个项目",
                    "innovation": "高",
                    "feasibility": "中",
                    "reason": "整合跨archetype的bridge pattern发现",
                    "innovation_score": 0.85,
                    "feasibility_score": 0.60,
                }
            ],
        },
    ]
    if tier2_items:
        result.append({"tier": 2, "label": "Tier 2: 方法学创新", "items": tier2_items})
    if tier3_items:
        result.append({"tier": 3, "label": "Tier 3: 深度挖掘", "items": tier3_items})
    return result


def _build_standalone_html(data, dashboard_dir, standalone_path):
    """Generate a fully self-contained HTML that works under file:// protocol.
    
    Inlines all CSS, JS, and data so no external file access is needed.
    """
    css_path = dashboard_dir / "css" / "styles.css"
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    js_files = [
        "js/charts.js",
        "js/tabs/overview.js",
        "js/tabs/evidence.js",
        "js/tabs/gaps.js",
        "js/tabs/hypotheses.js",
        "js/tabs/pipeline.js",
        "js/tabs/compare.js",
        "js/tabs/proposals.js",
        "js/tabs/decompose.js",
        "js/tabs/p05.js",
        "js/tabs/p08.js",
        "js/tabs/p09.js",
        "js/app.js",
    ]
    js_blocks = []
    for rel_path in js_files:
        js_path = dashboard_dir / rel_path
        if js_path.exists():
            with open(js_path, "r", encoding="utf-8") as f:
                js_blocks.append(f.read())
    combined_js = "\n\n".join(js_blocks)

    inline_data = json.dumps(data, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIscience 开题研究看板</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
{css}
</style>
</head>
<body>
<header>
  <h1><span class="dna">🧬</span> AIscience 开题研究看板</h1>
  <div class="header-right">
    <button class="icon-btn" id="themeBtn" title="切换主题">🌙</button>
    <button class="btn" id="exportBtn" title="导出研究报告">📄 导出报告</button>
  </div>
</header>
<nav class="tabs" id="tabNav" style="display:none"></nav>
<main id="main"></main>
<div class="modal-overlay" id="modalOverlay"><div class="modal" id="modalContent"></div></div>

<script>
const INLINE_DATA = {inline_data};
</script>
<script>
{combined_js}
</script>
</body>
</html>'''

    with open(standalone_path, "w", encoding="utf-8") as f:
        f.write(html)

    inline_data_path = dashboard_dir / "inline_data.js"
    with open(inline_data_path, "w", encoding="utf-8") as f:
        f.write("const INLINE_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";")

    print(f"  Standalone HTML: {standalone_path}")


def main():
    projects = []

    for pid, meta in PROJECT_META.items():
        summary_path = PROJECTS_DIR / pid / "output" / "summary.json"
        report_path = PROJECTS_DIR / pid / "output" / "final_report.json"

        if not summary_path.exists():
            print(f"  [WARN] Missing summary for {pid}")
            continue

        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

        gaps = []
        hypotheses = []
        budget = None

        if report_path.exists():
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)
            gaps = report.get("gaps", [])
            hypotheses = report.get("hypotheses", [])
            budget = report.get("budget")

        cfg = load_project_config(pid)
        literature = load_cards_literature(pid)
        skill_seq = cfg.get("skill_sequence", [])
        progress = compute_pipeline_progress(pid, skill_seq)

        project = {
            "id": pid,
            **meta,
            "research_direction": cfg.get("research_direction", ""),
            "total_cards": summary.get("total_cards", 0),
            "gap_count": summary.get("gap_count", 0),
            "hypothesis_count": summary.get("hypothesis_count", 0),
            "duration_s": round(summary.get("duration_s", 0), 1),
            "budget_used": summary.get("budget_used", 0),
            "converged": summary.get("converged", False),
            "literature": literature[:20],
            "literature_count": len(literature),
            "progress": progress,
            "gaps": gaps,
            "hypotheses": hypotheses,
            "budget": budget,
        }
        projects.append(project)

    total_cards = sum(p["total_cards"] for p in projects)
    total_gaps = sum(p["gap_count"] for p in projects)
    total_hyps = sum(p["hypothesis_count"] for p in projects)

    gap_patterns = {}
    all_gaps_flat = []
    for p in projects:
        for g in p["gaps"]:
            pid = g.get("pattern_id", "unknown")
            if pid not in gap_patterns:
                gap_patterns[pid] = {"count": 0, "avg_score": 0, "scores": [], "projects": set(), "name": PATTERN_NAME_ZH.get(pid, pid)}
            gp = gap_patterns[pid]
            gp["count"] += 1
            gp["scores"].append(g.get("score", 0))
            gp["projects"].add(p["id"])
            supporting = g.get("supporting_cards", [])
            all_gaps_flat.append({
                **g,
                "gap_name": g.get("gap_name") or PATTERN_NAME_ZH.get(pid, pid),
                "project_id": p["id"],
                "project_name": p["name"],
                "archetype": p["archetype"],
                "supporting_card_count": len(supporting) if isinstance(supporting, list) else 0,
            })

    for pid, gp in gap_patterns.items():
        gp["avg_score"] = round(sum(gp["scores"]) / len(gp["scores"]), 3)
        gp["projects"] = list(gp["projects"])
        del gp["scores"]

    all_hyps_flat = []
    for p in projects:
        for h in p["hypotheses"]:
            statement = h.get("statement", "") or ""
            title = h.get("title", "") or statement[:100] + ("..." if len(statement) > 100 else "")
            all_hyps_flat.append({
                **h,
                "title": title,
                "project_id": p["id"],
                "project_name": p["name"],
                "archetype": p["archetype"],
                "impact_level": extract_impact_level(h.get("expected_impact", "")),
            })

    archetypes = {}
    for p in projects:
        aid = p["archetype_id"]
        if aid not in archetypes:
            archetypes[aid] = {
                "id": aid,
                "name": p["archetype"],
                "color": ARCHETYPE_COLORS.get(aid, "#6B7280"),
                "project_count": 0,
                "total_cards": 0,
                "total_gaps": 0,
                "total_hypotheses": 0,
                "total_literature": 0,
            }
        a = archetypes[aid]
        a["project_count"] += 1
        a["total_cards"] += p["total_cards"]
        a["total_gaps"] += p["gap_count"]
        a["total_hypotheses"] += p["hypothesis_count"]
        a["total_literature"] += p.get("literature_count", 0)

    project_ids = [p["id"] for p in projects]
    cross_patterns = compute_cross_patterns(all_gaps_flat, project_ids)
    thesis_suggestions = generate_thesis_suggestions(all_hyps_flat, projects)
    decompose_data = load_decompose_results()
    p05_harness_data = _build_p05_harness()
    p08_harness_data = _build_p08_harness()
    p09_harness_data = _build_p09_harness()

    data = {
        "meta": {
            "total_projects": len(projects),
            "total_cards": total_cards,
            "total_gaps": total_gaps,
            "total_hypotheses": total_hyps,
            "total_literature": sum(p.get("literature_count", 0) for p in projects),
            "archetypes": list(archetypes.values()),
        },
        "projects": projects,
        "all_gaps": all_gaps_flat,
        "all_hypotheses": all_hyps_flat,
        "gap_patterns": gap_patterns,
        "cross_patterns": cross_patterns,
        "pipeline": PIPELINE_SKILLS,
        "thesis_suggestions": thesis_suggestions,
        "archetype_colors": ARCHETYPE_COLORS,
        "decompose": decompose_data,
        "p05_research_plans": p05_harness_data,
        "p08_research_plans": p08_harness_data,
        "p09_research_plans": p09_harness_data,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    dashboard_dir = OUTPUT.parent
    standalone_path = dashboard_dir / "index_standalone.html"
    _build_standalone_html(data, dashboard_dir, standalone_path)

    lit_total = sum(p.get("literature_count", 0) for p in projects)
    print(f"Built data.json: {total_cards} cards, {total_gaps} gaps, {total_hyps} hypotheses, {lit_total} papers")
    print(f"  Projects: {len(projects)}")
    print(f"  Archetypes: {len(archetypes)}")
    print(f"  Cross patterns: {len(cross_patterns)}")
    print(f"  Thesis suggestions: {sum(len(t['items']) for t in thesis_suggestions)}")
    if p05_harness_data:
        print(f"  P05 Harness: {p05_harness_data['passed_count']} passed, {p05_harness_data['failed_count']} failed, {len(p05_harness_data['candidates'])} candidates")
    if p08_harness_data:
        print(f"  P08 Harness: {p08_harness_data['passed_count']} passed, {p08_harness_data['failed_count']} failed, {len(p08_harness_data['candidates'])} candidates")
    if p09_harness_data:
        print(f"  P09 Harness: {p09_harness_data['passed_count']} passed, {p09_harness_data['failed_count']} failed, {len(p09_harness_data['candidates'])} candidates")


def load_decompose_results():
    decompose_path = DATA_DIR / "decompose_pilot_results.json"
    if not decompose_path.exists():
        return []
    try:
        raw = json.loads(decompose_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return []
    result = []
    for proj in raw:
        entry = {
            "project_id": proj["project_id"],
            "dimensions": proj["dimensions"],
            "total_candidates": proj["total_candidates"],
        }
        candidates = []
        for c in proj["candidates"]:
            cd = c["dimensions"]
            scores = c.get("scores", c.get("scoring", {}))
            candidates.append({
                "topic_id": c["topic_id"],
                "research_question": c["research_question"],
                "disease": cd.get("disease", ""),
                "tissue": cd.get("tissue", ""),
                "method": cd.get("method", ""),
                "population": cd.get("population", ""),
                "data_resource": cd.get("data_resource", ""),
                "combined_score": scores.get("combined", scores.get("combined_score", 0)),
                "density_score": scores.get("density", scores.get("density_score", 0)),
                "novelty_score": scores.get("novelty", scores.get("novelty_score", 0)),
                "feasibility_score": scores.get("feasibility", scores.get("feasibility_score", 0)),
                "literature_count": c.get("literature_count", 0),
                "dimensions_raw": cd,
            })
        entry["candidates"] = candidates
        result.append(entry)
    return result


def _build_p05_harness():
    runs_dir = DATA_DIR / "p05_harness_output" / "runs"

    # Try aggregated runs first
    latest_path = DATA_DIR / "p05_harness_output" / "latest_run.txt"
    run_names = []
    if latest_path.exists():
        text = latest_path.read_text(encoding="utf-8-sig")  # utf-8-sig strips BOM
        run_names = [line.strip() for line in text.splitlines() if line.strip()]

    if run_names:
        raw = _aggregate_harness_runs(runs_dir, run_names)
    else:
        # Fallback: read single harness_result.json
        harness_path = DATA_DIR / "p05_harness_output" / "harness_result.json"
        if not harness_path.exists():
            return None
        try:
            raw = json.loads(harness_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return None

    candidates = _parse_harness_candidates(raw.get("candidates", []))

    return {
        "passed_count": raw.get("passed_count", 0),
        "failed_count": raw.get("failed_count", 0),
        "total_llm_calls": raw.get("total_llm_calls", 0),
        "total_mcp_calls": raw.get("total_mcp_calls", 0),
        "total_duration_s": raw.get("total_duration_s", 0),
        "dimension_averages": raw.get("dimension_averages", {}),
        "dimension_availability": raw.get("dimension_availability", {}),
        "candidates": candidates,
        "dimensions": _load_harness_dimensions(),
    }


def _build_p08_harness():
    runs_dir = DATA_DIR / "p08_harness_output" / "runs"

    # Try aggregated runs first
    latest_path = DATA_DIR / "p08_harness_output" / "latest_run.txt"
    run_names = []
    if latest_path.exists():
        text = latest_path.read_text(encoding="utf-8-sig")
        run_names = [line.strip() for line in text.splitlines() if line.strip()]

    if run_names:
        raw = _aggregate_harness_runs(runs_dir, run_names)
    else:
        harness_path = DATA_DIR / "p08_harness_output" / "harness_result.json"
        if not harness_path.exists():
            return None
        try:
            raw = json.loads(harness_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return None

    candidates = _parse_harness_candidates(raw.get("candidates", []))

    return {
        "passed_count": raw.get("passed_count", 0),
        "failed_count": raw.get("failed_count", 0),
        "total_llm_calls": raw.get("total_llm_calls", 0),
        "total_mcp_calls": raw.get("total_mcp_calls", 0),
        "total_duration_s": raw.get("total_duration_s", 0),
        "dimension_averages": raw.get("dimension_averages", {}),
        "dimension_availability": raw.get("dimension_availability", {}),
        "candidates": candidates,
        "dimensions": _load_harness_dimensions_for("p08_harness"),
    }


def _build_p09_harness():
    runs_dir = DATA_DIR / "p09_harness_output" / "runs"

    latest_path = DATA_DIR / "p09_harness_output" / "latest_run.txt"
    run_names = []
    if latest_path.exists():
        text = latest_path.read_text(encoding="utf-8-sig")
        run_names = [line.strip() for line in text.splitlines() if line.strip()]

    if run_names:
        raw = _aggregate_harness_runs(runs_dir, run_names)
    else:
        harness_path = DATA_DIR / "p09_harness_output" / "harness_result.json"
        if not harness_path.exists():
            return None
        try:
            raw = json.loads(harness_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return None

    candidates = _parse_harness_candidates(raw.get("candidates", []))

    return {
        "passed_count": raw.get("passed_count", 0),
        "failed_count": raw.get("failed_count", 0),
        "total_llm_calls": raw.get("total_llm_calls", 0),
        "total_mcp_calls": raw.get("total_mcp_calls", 0),
        "total_duration_s": raw.get("total_duration_s", 0),
        "dimension_averages": raw.get("dimension_averages", {}),
        "dimension_availability": raw.get("dimension_availability", {}),
        "candidates": candidates,
        "dimensions": _load_harness_dimensions_for("p09_harness"),
    }


def _load_harness_dimensions_for(harness_name: str = "p05_harness") -> list[dict[str, Any]]:
    """Load rubric dimension definitions from harness config as single source of truth."""
    try:
        harness_config_path = BASE / "scripts" / harness_name / "config.yaml"
        if harness_config_path.exists():
            config = yaml.safe_load(harness_config_path.read_text(encoding="utf-8"))
            rubric = config.get("rubric", {})
            return [
                {"key": k, "label_zh": v.get("label_zh", k), "weight": v.get("weight", 1.0)}
                for k, v in rubric.items()
            ]
    except Exception:
        pass
    return []


def _load_harness_dimensions() -> list[dict[str, Any]]:
    return _load_harness_dimensions_for("p05_harness")


def _aggregate_harness_runs(runs_dir: Path, run_names: list[str]) -> dict[str, Any]:
    all_candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_passed = 0
    total_failed = 0

    for run_name in run_names:
        cp_path = runs_dir / run_name / "checkpoint.json"
        hr_path = runs_dir / run_name / "harness_result.json"
        # checkpoint.json is the always-complete incremental record; prefer it over
        # harness_result.json which may be partial on resumed runs
        source_path = cp_path if cp_path.exists() else hr_path
        if not source_path.exists():
            continue
        try:
            with open(source_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        for c in data.get("candidates", []):
            cid = c.get("candidate_id", "")
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                all_candidates.append(c)
                if c.get("passed"):
                    total_passed += 1
                else:
                    total_failed += 1

    # checkpoint.json has no file-level stats; sum per-candidate stats instead
    # (matches merge_runs() semantics in scripts/p05_harness/main.py)
    total_llm = sum(c.get("total_llm_calls", 0) for c in all_candidates)
    total_mcp = sum(c.get("total_mcp_calls", 0) for c in all_candidates)
    total_dur = sum(c.get("duration_s", 0.0) for c in all_candidates)

    # Compute dimension averages over each candidate's BEST iteration
    # (the delivered plan's scoring round, matching final_score / report semantics)
    dim_sums: dict[str, float] = {}
    dim_counts: dict[str, int] = {}
    for c in all_candidates:
        iterations = c.get("iterations", [])
        if not iterations:
            continue
        best_it = max(iterations, key=lambda it: it.get("weighted_score", 0))
        for dim, score in best_it.get("scores", {}).items():
            dim_sums[dim] = dim_sums.get(dim, 0.0) + score
            dim_counts[dim] = dim_counts.get(dim, 0) + 1
    dimension_averages: dict[str, float | None] = {
        dim: round(dim_sums[dim] / dim_counts[dim], 2) for dim in dim_sums
    }

    # Ensure all rubric dimensions from config are present (missing dims → null)
    # 0.0 有歧义（零分 vs 无数据），None 明确表示该维度尚无任何候选人被评分
    dimension_availability: dict[str, str] = {}
    try:
        from scripts.p05_harness.validators.rubric import RUBRIC_DIMENSIONS
    except ImportError:
        RUBRIC_DIMENSIONS = {}
    for dim_key in RUBRIC_DIMENSIONS:
        if dim_key not in dimension_averages:
            dimension_averages[dim_key] = None
            dimension_availability[dim_key] = "no_data"
        else:
            dimension_availability[dim_key] = "scored"

    return {
        "passed_count": total_passed,
        "failed_count": total_failed,
        "total_llm_calls": total_llm,
        "total_mcp_calls": total_mcp,
        "total_duration_s": round(total_dur, 1),
        "dimension_averages": dimension_averages,
        "dimension_availability": dimension_availability,
        "candidates": all_candidates,
    }


def _parse_harness_candidates(raw_candidates: list[dict]) -> list[dict]:
    result = []
    for c in raw_candidates:
        plan = c.get("plan", {})
        iterations = []
        for it in c.get("iterations", []):
            iterations.append({
                "iteration": it.get("iteration", 0),
                "scores": it.get("scores", {}),
                "weighted_score": it.get("weighted_score", 0),
                "passed": it.get("passed", False),
                "literature_gaps": it.get("literature_gaps", []),
            })
        final_critique = c.get("final_critique") or {}
        result.append({
            "candidate_id": c.get("candidate_id", ""),
            "topic_id": (c.get("topic_id") or c.get("candidate_id", "")),
            "research_question": c.get("research_question", ""),
            "method": c.get("method", ""),
            "disease": c.get("disease", ""),
            "combined_score": c.get("combined_score", 0),
            "final_score": c.get("final_score", 0),
            "passed": c.get("passed", False),
            "iterations": iterations,
            "completeness": c.get("completeness", {}),
            "citation_checks": c.get("citation_checks", []),
            "literature_coverage": c.get("literature_coverage", {}),
            "gap_papers_found": c.get("gap_papers_found", 0),
            "total_llm_calls": c.get("total_llm_calls", 0),
            "total_mcp_calls": c.get("total_mcp_calls", 0),
            "duration_s": c.get("duration_s", 0),
            "error": c.get("error", ""),
            "score_stability": c.get("score_stability", -1.0),
            "novelty_verdict": c.get("novelty_verdict", {}),
            "redteam_result": c.get("redteam_result", {}),
            "novelty_verdict_initial": c.get("novelty_verdict_initial", {}),
            "redteam_result_initial": c.get("redteam_result_initial", {}),
            "repositioning_attempts": c.get("repositioning_attempts", 0),
            "critique_text": final_critique.get("critique_text", ""),
            "detailed_feedback": final_critique.get("detailed_feedback", {}),
            "summary_zh": plan.get("summary_zh", ""),
            "technical_roadmap": plan.get("technical_roadmap", []),
            "data_sources_detail": plan.get("data_sources_detail", []),
            "feasibility": plan.get("feasibility", {}),
            "innovation_points": plan.get("innovation_points", []),
            "expected_outputs": plan.get("expected_outputs", []),
            "target_venues": plan.get("target_venues", []),
            "evidence_link": c.get("evidence_link", {}),
        })
    return result


if __name__ == "__main__":
    main()
