# AIscience OpenCode Instructions

## Project Overview

AIscience is a Chinese-language AI agent for bioinformatics research topic selection (开题). It runs 9 research sub-projects across 6 archetypes through a 12-skill pipeline.

**Language**: Python 3.11+ / HTML+CSS+JS / YAML configs
**Code comments**: Chinese for business logic, English for identifiers
**LLM**: litellm adapter (default `gpt-4o-mini`)

## Common Commands

```bash
# Run all 9 projects (requires LLM API)
python main.py

# Run single project
python main.py --only p01_gwas_perturb_seq

# Rebuild dashboard data (includes standalone HTML)
python dashboard/build_data.py

# Generate coverage maps (offline, no LLM)
python scripts/generate_coverage_maps.py

# Re-run S11+S12 for p04 (LLM for S12)
python scripts/rerun_p04_gap.py

# Re-run p05/p06/p07 schema conversion + S11+S12 (LLM for S12)
python scripts/rerun_p05_p06_p07.py

# Decompose research directions (standard 5-axis or per-project custom axes from config.yaml)
python scripts/decompose_directions.py --projects p01,p05,p06

# Run p05 research plan quality harness (critique-refine loop)
python scripts/p05_harness/main.py --max-candidates 10

# Run harness on specific candidates with named run
python scripts/p05_harness/main.py --candidates p05_sc_multiomics_ai_T015,p05_sc_multiomics_ai_T019 --run-name run_gwas_1

# Merge harness runs into dashboard
python scripts/p05_harness/main.py --merge

# Run p08 research plan quality harness (cross-ethnic multi-omics critique-refine loop)
python scripts/p08_harness/main.py --max-candidates 10

# Run p08 harness on specific candidates with named run
python scripts/p08_harness/main.py --candidates p08_cross_ethnic_multiomics_T000,p08_cross_ethnic_multiomics_T005 --run-name run_cross_ethnic_1

# Merge p08 harness runs into dashboard
python scripts/p08_harness/main.py --merge

# Run p09 research plan quality harness (scGWAS × spatial transcriptomics critique-refine loop)
python scripts/p09_harness/main.py --run-name run_v1

# Merge p09 harness runs into dashboard
python scripts/p09_harness/main.py --merge

# Validate harness consistency (dimensions across config/rubric/JS)
python scripts/validate_p05_consistency.py --all
```


## Key Conventions

1. **Archetypes resolve card class from config**: `archetypes/{id}/config.yaml` → `evidence_card_class: archetypes.X.evidence_card.CardClass`
2. **S11 MUST have gap blocks for all archetypes**: Detection uses `c.archetype` string, not field values. See `shared/skills/skill_11_gap_analysis.py` for pattern.
3. **Card schema conversion**: When converting cards between archetypes, use `model_validate()` — extra fields are ignored, new fields get defaults.
4. **Dashboard is modular JS**: `js/app.js` is core state + routing; tab modules in `js/tabs/`; shared charts in `js/charts.js`.
5. **Data flows**: `build_data.py` (project outputs → data.json) → `index.html` (data.json → ECharts viz).
6. **S6C deep-read notes → S7 enriched cards**: Tier 1 papers get fact extraction+claim audit;
   Tier 2 additionally gets formula derivation (construct+refute double audit) and critical assessment.
   S7 `_extract_from_deep_read()` maps notes.facts into cards with `evidence_status`/`evidence_strength` fields.
   Notes are produced per-candidate during the inner loop, stored in accumulated data as `notes`.

## Data Storage

### Directory Structure
```
data/
├── decompose_pilot_results.json   # 全项目方向分解 (9 项目 × ~40 候选)
├── p05_agent_candidates.json      # p05 Agent 候选 (预注入论文)
├── response_cache.db              # LLM 响应缓存 (SQLite, ns=mcp)
├── run_all_report.json            # 全项目运行报告聚合
├── learning_report.md             # 人类可读学习报告 (自动生成)
├── cross_archetype_gap_scan.json  # 跨原型缺口扫描
├── l0_cold/{project}/             # 冷存储: L2 快照 + provenance + sub-agents
│   ├── l2_snapshots/final.json    # 管道完整状态快照
│   ├── sub_agents/                # 每技能子代理输出
│   └── provenance_report.json     # 卡片级溯源审计
├── l1_warm/{project}/             # 温存储: 输出 + 检查点
│   ├── cards.jsonl                # 证据卡副本 (JSONL, 每行一卡)
│   ├── checkpoints/               # 每轮/每候选检查点文件
│   └── __manifest/                # Delta-rs manifest
├── p08_harness_output/            # p08 测评套件输出
│   ├── harness_result.json        # 聚合测评结果
│   ├── latest_run.txt             # 最新运行目录列表
│   └── runs/{run_name}/           # 每次运行
└── p09_harness_output/            # p09 测评套件输出
    ├── harness_result.json        # 聚合测评结果
    ├── latest_run.txt             # 最新运行目录列表
    └── runs/{run_name}/           # 每次运行
└── p05_harness_output/            # p05 测评套件输出
    ├── harness_result.json        # 聚合测评结果
    ├── latest_run.txt             # 最新运行目录列表
    └── runs/{run_name}/           # 每次运行:
        ├── checkpoint.json        # 候选状态+迭代历史
        ├── harness_result.json    # 该次运行结果
        ├── p05_final_enriched.json # 仪表盘就绪最终方案
        └── acceptance_report.md   # Markdown 验收报告
```

### Project Output Structure (`projects/{p}/output/`)
| File | Purpose |
|------|---------|
| `evidence_cards.jsonl` | 所有证据卡 (JSONL, 每行一个 JSON 对象) |
| `final_report.json` | 完整最终报告 (gaps, hypotheses, cards, coverage) |
| `coverage_map.json` | 覆盖矩阵 |
| `summary.json` | 快速摘要 (project_id, converged, card/gap/hypothesis 计数) |

### Evidence Cards Format
- 存储为 JSONL（非 JSON 数组），每行一个 `SCFMEvidenceCard`（archetype C）或其他原型卡片
- 每张卡片包含 `source_paper` 嵌入字段（DOI/PMID/title/authors/year/venue）
- 深读富集字段：`evidence_status` (directly_stated/inferred/author_claim/unresolved)、`evidence_strength`、`deep_read_source`
- p05 卡片额外含 GWAS 字段：`gwas_trait`、`gwas_locus`、`coloc_method`、`coloc_score`、`gwas_dataset`

## Dashboard Development Conventions

### Literature Links
- ALL literature references MUST use `litLink(l)` / `litAnchor(l, maxLen)` helpers from `charts.js`
- Link priority: `paper_url` → `doi` (→ `https://doi.org/`) → `pmid` (→ `https://pubmed.ncbi.nlm.nih.gov/`)
- Applies to: evidence table titles, project card representative papers, modal literature lists

### Chart Legends
- Multi-series charts (≥5 series) MUST have `legend: { type: 'scroll' }` and `grid.bottom` ≥ 55px
- Single-series charts MUST NOT have a redundant legend (omit or `show: false`)
- Legend labels MUST use `p.name_en` (English short name), NOT `p.name` (Chinese long name 15-20 chars)

### Table Responsiveness
- EVERY table MUST be wrapped in `<div class="table-wrap">` for `overflow-x: auto` on small screens
- Long scrollable tables (e.g. literature list) MUST use `.sticky-table` CSS class for fixed headers

### Dark Mode
- Border colors MUST be at least `#475569` on `#0f172a`/`#1e293b` backgrounds (minimum 3:1 contrast)

### Mobile Breakpoint
- Always include `@media (max-width: 480px)` in `styles.css` alongside the existing 768px breakpoint

### Truncation
- Text truncation MUST include ellipsis (`...`) AND `title` attribute for full text display
- Never use bare `.slice(0, N)` without those two elements

### Multi-Dimension Score Charts
- Multi-dimension comparison charts MUST use **grouped bars** (`stack: undefined`, `barMaxWidth: 14`) or **radar chart**
- NEVER use `stack: 'total'` for semantically independent dimensions (total is meaningless)
- `yAxis.max` MUST equal the per-dimension max (typically 5 for rubric scoring), not the stack sum
- When adding a new rubric dimension, update BOTH `DIM_KEYS`/`DIM_LABELS` in the tab JS AND the dimension list in report.py — preferably driven from a single source (rubric config)

### JS Helper Functions in Tab Modules
- Helper functions (`esc`, `truncate`, etc.) MUST be defined **self-containedly in the tab module**, not imported from cross-module dependencies
- Inline escaping: `.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')` — avoids `esc is not defined` errors due to script load order in standalone HTML
- When rendering nested objects (e.g. `innovation_points: [{claim, closest_existing_work, ...}]`), MUST extract the display field explicitly: `typeof obj === 'string' ? obj : obj.claim || JSON.stringify(obj)` — never interpolate the raw object
- `build_data.py` `_parse_*` functions MUST pass through ALL source fields (not silently drop unknown fields); add new fields via `+=` rather than constructing a whitelist-only dict

### Adding New Dashboard Tabs
- Create `js/tabs/{name}.js` with `const XxxTab = { render(el) {...} }` pattern
- Register in `app.js`: add to `TABS` array + add `case` in `renderTab()` switch
- Add to `build_data.py` `_build_standalone_html()` `js_files` list (between existing tabs and `app.js`)
- Run `python dashboard/build_data.py` to regenerate `index_standalone.html`
- Tab accesses data via `App.DATA` (already loaded before tab render)

### Checkpoint System for Progress Tracking
- S1-S3 and S11-S12 have individual checkpoint files per round
- S4-S10 inner-loop skills only have aggregate `rN_inner_loop.json` — no individual checkpoints
- `compute_pipeline_progress()` in `build_data.py` MUST check for `*inner_loop*` checkpoints to correctly mark inner-loop skills as completed

## File Locator

| What | Where |
|------|-------|
| Pipeline entry | `main.py` |
| Per-project orchestrator | `shared/core/orchestrator.py` |
| 3-phase loop | `shared/core/loop_engine.py` |
| LLM client | `shared/core/llm_client.py` |
| Skill base class | `shared/skills/base_skill.py` |
| S7 card extraction | `shared/skills/skill_07_evidence_card_extract.py` |
| S7 card extract (archetype C) | `archetypes/archetype_c_sc_ai/skills/skill_07_scfm_card_extract.py` |
| S6C deep read skill | `shared/skills/skill_06c_deep_read.py` |
| S6C schemas (facts, claims, judgments) | `shared/skills/deep_read/schemas.py` |
| S6C quality gates | `shared/skills/deep_read/quality_gates.py` |
| S6C expression mapper | `shared/skills/deep_read/expression_mapper.py` |
| S1 direction decompose | `shared/skills/skill_01_direction_decompose.py` |
| S11 gap analysis | `shared/skills/skill_11_gap_analysis.py` |
| S12 hypothesis generation | `shared/skills/skill_12_hypothesis_generate.py` |
| Evidence card schemas | `shared/evidence/base_card.py` + `archetypes/*/evidence_card.py` |
| Gap patterns (60 total) | `archetypes/*/gap_patterns.py` + `shared/skills/skill_11_gap_analysis.py` |
| p05 C12 GWAS gap detection | `archetypes/archetype_c_sc_ai/gap_patterns.py` + S11 L648-680 |
| p05 GWAS evidence fields | `archetypes/archetype_c_sc_ai/evidence_card.py` (gwas_trait/locus/coloc_method/score/dataset) |
| Direction decomposition (supports per-project custom axes) | `scripts/decompose_directions.py` |
| p05 research plan harness | `scripts/p05_harness/main.py` + `phases/` + `validators/` |
| Harness rubric config | `scripts/p05_harness/config.yaml` |
| Harness acceptance report | `scripts/p05_harness/report.py` |
| p05 harness output | `data/p05_harness_output/` (harness_result.json + runs/) |
| p05 project-level AGENTS.md | `projects/p05_sc_multiomics_ai/AGENTS.md` |
| p09 research plan harness | `scripts/p09_harness/main.py` (reuses p05 core, domain_prompts.py for spatial GWAS) |
| p09 harness rubric config | `scripts/p09_harness/config.yaml` |
| p09 harness acceptance report | `scripts/p05_harness/report.py` |
| p09 harness output | `data/p09_harness_output/` (harness_result.json + runs/) |
| LLM response cache | `data/response_cache.db` (SQLite, table: cache) |
| Direction decomposition (supports per-project custom axes) | `scripts/decompose_directions.py` |
| Decompose data | `data/decompose_pilot_results.json` |
| Dashboard HTML shell | `dashboard/index.html` |
| Dashboard core JS | `dashboard/js/app.js` |
| Dashboard tab modules | `dashboard/js/tabs/*.js` |
| Data aggregator | `dashboard/build_data.py` |
| Coverage map generator | `scripts/generate_coverage_maps.py` |
| Config | `.env` (AISCIENCE_* vars) |
| User docs | `docs/使用手册.md` |
| Troubleshooting | `docs/TROUBLESHOOTING.md` |
| Skill dev guide | `docs/SKILL_DEVELOPMENT_GUIDE.md` |
| Architecture | `docs/ARCHITECTURE.md` |
| Changelog | `docs/CHANGELOG.md` |

## 知识库联动（j-ssl）

本仓库是 AIscience 代码、pipeline、dashboard 和运行产出所在地；研究笔记、文献卡、概念卡统一放在 Obsidian 知识库。

- 知识库根目录：`D:\ssl\j-ssl`
- 项目索引页：[AIscience 项目索引](file:///D:/ssl/j-ssl/项目索引/AIscience.md)
- 推荐关联：`wiki/vision_driven_ST.md`、`wiki/GWAS.md`、`文献索引/资料/Benchmarking AI scientists for omics data–driven biological discovery.md`