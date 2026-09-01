# P05 (scFM) 项目完整架构参考 v2.1

> 单细胞基础模型（Single-Cell Foundation Model）研究开题管线 + 独立质量评估框架
> 
> 版本: v2.1 | 日期: 2026-07-24 | 测试: 140/140 通过

---

## 目录

1. [概述](#1-概述)
2. [文件组织](#2-文件组织)
3. [数据模型](#3-数据模型)
4. [管线流程 (S1→S12)](#4-管线流程-s1s12)
5. [评估框架架构](#5-评估框架架构)
6. [配置体系](#6-配置体系)
7. [仪表板集成](#7-仪表板集成)
8. [质量门控](#8-质量门控)
9. [评审者系统](#9-评审者系统)
10. [证据锚定系统](#10-证据锚定系统)
11. [缓存与并行](#11-缓存与并行)
12. [关系数据库持久化](#12-关系数据库持久化)
13. [关键架构模式](#13-关键架构模式)
14. [v2.1 变更摘要](#14-v21-变更摘要)

---

## 1. 概述

P05 是 AIscience 七个研究开题子项目之一，专注于**单细胞多组学基础模型**（scFM）领域。它包含两个独立的子系统：

| 子系统 | 入口 | 功能 |
|--------|------|------|
| **证据采集管线** | `main.py --only p05_sc_multiomics_ai` | S1→S12 技能链：分解研究方向的证据采集、深读、卡片提取、缺口分析、假设生成 |
| **质量评估框架** | `python scripts/p05_harness/main.py` | 独立的 Phase 0→3 审查-精炼循环：基于证据卡生成研究方案并对其进行评分 |

两个子系统通过文件系统解耦：管线产出证据卡和缺口/假设，评估框架读取这些产物进行独立评估。

### v2 核心升级

| 类别 | 升级项 | 状态 |
|------|--------|------|
| 数据质量 | S11 缺口证据全量保留 + 加权缺口评分 (EvidenceState) | ✓ |
| 数据质量 | Boolean → 6 值 EvidenceState 枚举 | ✓ |
| 数据质量 | CandidateEvidenceLink 证据锚定 | ✓ |
| 数据质量 | GapEvidenceLink 缺口-证据结构化关联 | ✓ |
| 数据质量 | S7 质量门控四重关卡 | ✓ |
| 数据质量 | 原型字符串 → 注册表常量 (ARCHETYPE_SC_FM 等) | ✓ |
| 数据质量 | 仪表板 0.0 回退 → null + 可用性标记 | ✓ |
| 评审系统 | 3 评审者角色分离 (generalist/methodologist/domain_expert) | ✓ |
| 评审系统 | 评审者专属输入上下文 (技术路线/创新点聚焦) | ✓ |
| 性能 | LLM/MCP SQLite 缓存 + 版本化 | ✓ |
| 性能 | 候选级并行 (asyncio.gather + Semaphore) | ✓ |
| 配置 | Pydantic 配置模式 + 清单 | ✓ |

---

## 2. 文件组织

```
P05 项目 (scFM + AI Agent 研究)
│
├── projects/p05_sc_multiomics_ai/          ← 管线入口、项目配置、产出
│   ├── __init__.py
│   ├── AGENTS.md
│   ├── config.yaml                         ← 项目配置：技能序列 + 自定义分解轴 + 收敛规则
│   ├── tool_flow.py                        ← 项目管线类
│   └── output/                             ← 管线产出物
│       ├── evidence_cards.jsonl            ← SCFMEvidenceCard 记录 (JSONL)
│       ├── final_report.json               ← S11+S12 缺口/假设最终报告
│       ├── coverage_map.json               ← 覆盖矩阵
│       └── summary.json                    ← 运行摘要
│
├── archetypes/archetype_c_sc_ai/           ← 原型定义
│   ├── __init__.py                         ← 导出 SCFMEvidenceCard, ARCHETYPE_C_GAP_PATTERNS
│   ├── config.yaml                         ← 原型配置 (卡片类、覆盖轴、缺口模式)
│   ├── evidence_card.py                    ← SCFMEvidenceCard (48 字段, 5 覆盖轴)
│   ├── gap_patterns.py                     ← S11 缺口模式 (C1-C11，含加权配置)
│   └── skills/                             ← 原型专属技能重载 (S3, S7)
│       ├── __init__.py
│       ├── skill_03_fm_resource_collect.py
│       └── skill_07_scfm_card_extract.py   ← scFM 领域感知卡片提取 (双路径)
│
├── scripts/p05_harness/                    ← 质量评估框架 (独立于管线)
│   ├── __init__.py
│   ├── main.py                             ← CLI 入口
│   ├── config.yaml                         ← 评估框架配置 (7 节, 24 键)
│   ├── config_schema.py                    ← 配置验证 (Pydantic HarnessConfig, _CONFIG_MANIFEST)
│   ├── loop_runner.py                      ← Phase 0→3 审查-精炼循环 (并发支持)
│   ├── report.py                           ← 评估报告 JSON 生成 (含 RubricDimension)
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── query_generator.py              ← Phase 0 对抗性查询生成
│   │   └── search_engine.py                ← 多源文献检索 (MCP 缓存感知)
│   ├── phases/
│   │   ├── __init__.py
│   │   ├── phase1_generate.py              ← 初始方案生成 + 对抗性查询
│   │   ├── phase15_novelty_verify.py       ← 新颖性验证 (Phase15Output)
│   │   ├── phase2_critique.py              ← 方案审查 (评审者角色感知)
│   │   └── phase3_refine.py                ← 方案精炼
│   └── validators/
│       ├── __init__.py
│       ├── rubric.py                       ← 评分标准 (6 维, 加权求和)
│       ├── citation_verifier.py            ← 引文核验
│       ├── completeness_check.py           ← 结构完备性
│       ├── literature_check.py             ← 文献覆盖
│       └── methodology_redteam.py          ← 方法学红队 (高/中/低严重性)
│
├── shared/
│   ├── evidence/
│   │   ├── base_card.py                    ← BaseEvidenceCard + EvidenceState 枚举 + 常量
│   │   ├── card_store.py                   ← 卡片持久化
│   │   └── coverage_matrix.py              ← 覆盖矩阵
│   ├── skills/
│   │   ├── skill_01_direction_decompose.py ← S1: 方向分解 (支持自定义轴)
│   │   ├── skill_02_terminology_normalize.py
│   │   ├── skill_04_multi_source_search.py
│   │   ├── skill_05_citation_snowball.py
│   │   ├── skill_06_literature_screening.py
│   │   ├── skill_06b_pdf_download.py
│   │   ├── skill_06c_deep_read.py          ← S6C: 深读 (证据账本, P05 分流步骤)
│   │   ├── skill_07_evidence_card_extract.py ← S7: 通用证据卡片提取
│   │   ├── skill_08_data_availability.py
│   │   ├── skill_09_method_dataset_match.py
│   │   ├── skill_11_gap_analysis.py        ← S11: 缺口分析 (GapEvidenceLink)
│   │   ├── skill_12_hypothesis_generate.py ← S12: 假设生成
│   │   └── deep_read/                      ← S6C 子包
│   │       ├── schemas.py                  ← Facts, Claims, Judgments
│   │       ├── quality_gates.py            ← 程序化质量门控
│   │       └── expression_mapper.py        ← 公式映射器
│   └── core/
│       ├── cache.py                        ← SQLite 缓存层 (v2 新增)
│       ├── config.py                       ← 全局 Settings (pydantic-settings)
│       ├── llm_client.py                   ← LLM 客户端 (litellm 适配, 缓存集成)
│       ├── token_budget.py                 ← 令牌预算管理
│       ├── loop_engine.py                  ← 3 阶段外层循环
│       ├── orchestrator.py                 ← 每项目管线编排
│       ├── harness.py                      ← Harness 适配器
│       └── ...
│
├── dashboard/
│   ├── index.html                          ← 仪表板外壳
│   ├── build_data.py                       ← 数据聚合器 (_build_p05_harness)
│   └── js/
│       ├── app.js                          ← 核心状态 + 路由
│       ├── charts.js                       ← 共享图表 (litLink, litAnchor)
│       └── tabs/
│           └── p05.js                      ← P05 标签页 (分组柱状图 + 候选网格 + 模态框)
│
├── tests/
    ├── test_p05_harness_e2e.py             ← 评估框架 E2E 测试 (15 测试)
    ├── test_novelty_verify.py              ← 新颖性验证测试 (698 行)
    ├── test_scfm_card_extract.py           ← SCFMCardExtract 测试 (286 行)
    ├── test_gap_analysis.py                ← 缺口分析测试
    ├── test_base_card.py                   ← 基础卡片测试
    └── test_loop_engine.py                 ← 循环引擎测试
│
├── data/                                   ← 数据库持久化层 (v2.1 新增)
│   ├── schema.sql                          ← 12 表 + 3 视图 + FTS5 建表脚本
│   ├── validate_schema.py                  ← 模式验证: 自动创建 knowledge.db 并校验表结构
│   ├── backfill_from_jsonl.py              ← 回填脚本: JSONL/JSON → knowledge.db (5 阶段加载)
│   └── knowledge.db                        ← SQLite 数据库 (WAL模式, JSON1+FTS5)
```

---

## 3. 数据模型

### 3.1 核心类型层次

```
BaseEvidenceCard (base_card.py)          ← extra="ignore" 允许跨原型转换
├── card_id: str
├── source_type: SourceType              ← "paper" | "database" | "preprint" | "code_repo" | "dataset"
├── source_paper: SourcePaper            ← doi, pmid, title, authors, year, venue, url
├── source_location: SourceLocation      ← section, excerpt, page, table_or_figure
├── extracted_at: str
├── reliability_flag: str                ← "unverified" | "medium" | "high"
├── key_finding: str
├── method_brief: str
├── limitation_explicit: Optional[str]
├── limitation_implicit: Optional[str]
├── archetype: str                       ← 原型标识符 (ARCHETYPE_SC_FM = "sc_fm")
├── tags: list[str]                      ← 用于 candidate:{id} 标签
│
├── V2GEvidenceCard (原型 A)             ← 35+ 字段: 变异, 性状, GWAS
├── PRSEvidenceCard (原型 B)             ← PRS 评分, 校准, 跨血统
├── SCFMEvidenceCard (原型 C) ← P05 使用  ← 48 字段: 单细胞基础模型
│   ├── 核心分类: task, task_category, modality_omics, modalities_integrated
│   ├── 模型: model_architecture, model_family, pretext_task, downstream_task
│   ├── 规模: n_cells_pretrain, n_cells_finetune, n_features_input, n_parameters, embedding_dim
│   ├── 评估: eval_metric_name, eval_metric_value, baseline_method, baseline_metric_value
│   ├── 证据状态 (8 个 EvidenceState 字段):
│   │   held_out_cell_types, held_out_tissues, batch_correction_evaluated,
│   │   transfer_evaluated, interpretability_assessed,
│   │   code_available, weights_available, dataset_available
│   ├── 资源: raw_data_accession, model_hub
│   └── 深读增强: evidence_status, evidence_strength, deep_read_source
│
├── OmicsScoreEvidenceCard (原型 D)       ← 组学评分, 临床截断值
└── 覆盖轴 (coverage_axes()):
    原型 C → task × modality × tissue × model_architecture × evaluation_setting
```

### 3.2 EvidenceState 枚举 (6 值, v2 扩展)

```python
class EvidenceState(str, Enum):
    CONFIRMED = "confirmed"                    # 论文明确声明存在
    REPORTED_NOT_DONE = "reported_not_done"    # 论文明确声明未做
    NOT_REPORTED = "not_reported"              # 论文未提及
    NOT_EXTRACTED = "not_extracted"            # 字段未被提取 (缺省初始状态, v2 新增)
    CONFLICTING = "conflicting"               # 多源证据矛盾 (v2 新增)
    NOT_APPLICABLE = "not_applicable"         # 字段不适用此卡片 (v2 新增)

EVIDENCE_STATE_WEIGHTS = {
    "reported_not_done": 1.0,     # 明确缺失 → 最强缺口信号
    "not_reported": 0.55,          # 未提及 → 中等信号
    "confirmed": 0.0,              # 存在 → 非缺口
    "not_extracted": 0.0,          # 未提取 → 非缺口 (数据缺口)
    "conflicting": 0.0,            # 矛盾 → 非缺口 (不确定)
    "not_applicable": 0.0,         # 不适用 → 非缺口
}
```

替代了 8 个 `Optional[bool]` 字段。在缺口分析中，`!= CONFIRMED` 同时匹配 `NOT_REPORTED` 和 `REPORTED_NOT_DONE`，但权重不同：明确声明未做的卡片贡献更强的缺口信号 (1.0 vs 0.55)。

### 3.3 缺口与假设模型

```
GapPattern (skill_11_gap_analysis.py)
├── pattern_id: str, name: str, description: str
├── weight_evidence_asymmetry: float = 0.35
├── weight_feasibility: float = 0.25
├── weight_competition: float = 0.20
├── weight_cross_archetype: float = 0.20
│
└──→ IdentifiedGap
     ├── gap_id, pattern_id, axis, description
     ├── score: float                          ← 加权复合分数: 基础分 + 权重 × 证据权重 / 分母
     ├── feasibility, competition, cross_archetype
     ├── supporting_cards: list[str]          ← 前 10 个 (展示用)
     ├── all_supporting_card_ids: list[str]    ← 全部 (v2 全量保留)
     ├── contradicting_card_ids, uncertain_card_ids
     ├── coverage_denominator, coverage_numerator
     ├── gap_confidence: float                ← 覆盖比率置信度 (v2)
     └── evidence_links: list[GapEvidenceLink] ← 结构化证据链接 (v2 新增)

GapEvidenceLink (v2 新增)                    ← 缺口与卡片的结构化关联
├── card_id: str
├── matched_field: str                        ← "held_out_cell_types", "weights_available" 等
├── matched_rule: str                         ← "not_confirmed", "field_missing" 等
├── weight: float                             ← 0.0-1.0 (取决于 EvidenceState)
└── rationale: str                            ← "Card xxx: held_out_cell_types=reported_not_done ..."

Hypothesis (skill_12_hypothesis_generate.py)
├── hypothesis_id: str
├── statement: str                            ← 假设陈述
├── addresses_gap: str                        ← 目标缺口 ID (单缺口)
├── rationale: str                            ← 新颖性论证
├── required_methods: list[str]
├── required_datasets: list[str]              ← 仅限于可用 accession
├── novelty_score: float                      ← 0.0-1.0
├── feasibility_score: float                  ← 0.0-1.0
└── expected_impact: str
```

### 3.4 评估框架结果模型

```
HarnessResult
├── candidates: list[CandidateLoopResult]
├── passed_count, failed_count
├── total_llm_calls, total_mcp_calls
├── total_duration_s
├── dimension_averages: {dim → float|null}        ← null = 无评分数据 (v2)
└── dimension_availability: {dim → "scored"|"no_data"}  ← v2 新增

CandidateLoopResult (每候选) ← loop_runner.py CandidateLoopResult dataclass
├── candidate_id, research_question, method, disease
├── plan: {
│     summary_zh: str
│     technical_roadmap[{step, title, desc, methods, weeks, tools, expected_output}]
│     data_sources_detail[{name, access, format, size, url, note}]
│     feasibility: {data_accessibility, compute_requirements, technical_difficulty,
│                   timeline_months, key_risks, mitigation}
│     innovation_points[{claim, closest_existing_work, difference, evidence_refs}]
│     expected_outputs: [str]
│     target_venues: [str]
│   }
├── iterations[{iteration, scores{dim→float}, weighted_score, passed, literature_gaps}]
├── final_critique: CritiqueResult
│     ├── scores{dim→float}, weighted_score, passed
│     ├── detailed_feedback{dim→str}, critique_text
│     ├── literature_gaps: [str]
│     ├── score_stability: float               ← 评审者间方差 (v2)
│     ├── reviewer_profile: str                ← 使用的评审者角色 (v2)
│     └── raw_response: str                    ← 聚合元数据 JSON (v2)
├── novelty_verdict: Phase15Output
│     ├── overall_verdict: "clear"|"crowded"|"adjacent"|"scooped"
│     ├── verdicts[{claim, verdict, closeness, closest_works, comparison_table}]
│     ├── papers_found: int
│     └── reverified_post_refine: bool
├── redteam_result: RedTeamOutput
│     ├── findings[{check, severity, detail, suggestion}]
│     ├── high_count, medium_count, low_count
│     └── verified_claims, unverified_claims
├── citation_checks[{exists, doi, pmid, access, verified_title, error}]
├── literature_coverage:
│     ├── evidence_card_count, cited_paper_count, overlapping_count
│     └── evidence_source: "tagged"|"fallback_pool"
├── evidence_link:                             ← v2 证据锚定
│     ├── evidence_source: "tagged"|"fallback_pool"
│     ├── linked_card_count: int
│     ├── evidence_pool_size: int
│     ├── linked_card_ids: [str]               ← 前 20 个
│     ├── unique_paper_count: int              ← 去重后 (v2)
│     └── relation_counts: {supports:X, contradicts:Y, ...}  ← v2
├── evidence_links: list[CandidateEvidenceLink] ← v2 新增
│     ├── card_id: str
│     ├── relation: "supports"|"contradicts"|"adjacent"|"prior_work"|"dataset"|"method"
│     ├── relevance_score: float
│     ├── link_method: "pipeline_origin"|"semantic_retrieval"|"citation_graph"|"manual"
│     ├── verification_status: str
│     ├── created_by_stage: str
│     └── paper_id: str
├── completeness: dict
├── gap_papers_found: int
├── repositioning_attempts: int
├── total_llm_calls, total_mcp_calls, duration_s
└── score_stability: float
```

---

## 4. 管线流程 (S1→S12)

### 4.1 技能序列

```
S1 方向分解          ─→ 自定义 2 线分解轴 (scfm_depth × agent_line)
  │                   产出: decompose_pilot_results.json ← candidate 来源
  ▼
S2 术语标准化         ─→ 性状/基因规范化
  ▼
S3 FM 资源收集        ─→ 原型特定: 收集基础模型资源
  ▼
S4 多源检索           ─→ 候选驱动查询重写 (LLM) → 论文搜索
  ▼
S5 引文滚雪球         ─→ 前向/后向引文扩展
  ▼
S6 文献筛选           ─→ 候选范围边界筛选
  ▼
S6b PDF 下载          ─→ 全文获取 (如有)
  ▼
S6c 深读 ★ (分流步骤)  ─→ 证据账本分析: 事实, 声明, 判断, 公式派生
  │                   第 1 层: 事实提取 + 声明审计
  │                   第 2 层: 公式派生 (构造+反驳双重审计) + 批判性评估
  │                   产出: 深读笔记 {paper_id: {facts[], claims[], judgments[]}}
  ▼
S7 证据卡片提取        ─→ 双路径处理:
  │                   ● 深读路径: _extract_from_deep_read() → 每 fact 1 张卡片,
  │                     evidence_status/evidence_strength 继承自深读
  │                   ● 回退路径: _extract_from_paper() → LLM 全文提取
  │                   每卡片标记: tags.append("candidate:{topic_id}")
  │                   产出: evidence_cards.jsonl
  │                   质量门控: 身份关卡 (key_finding 非空), 证据关卡 (60%+ 深读卡片有 evidence_status),
  │                             领域关卡 (>3 论文时 task 填充率 ≥ 40%), 基数关卡 (警告 >10 卡片/论文)
  ▼
S8 数据可用性 / S9 方法-数据集匹配
  ▼
S11 缺口分析           ─→ 规则驱动检测 (C1-C11 针对 sc_fm)
  │                   使用 card.archetype 字符串进行比较 (ARCHETYPE_SC_FM)
  │                   加权缺口评分: 按 6 种 EvidenceState 权重分布调整分数
  │                   GapEvidenceLink: 每张匹配卡片记录触发字段/规则/权重/理由
  │                   缺口描述含明确未做/矛盾计数
  │                   产出: identified_gaps[] → final_report.json
  ▼
S12 假设生成           ─→ LLM 驱动, 原型感知
  │                   提示中注入 sc_fm 上下文 (task/model_family/tissue/arch)
  │                   产出: hypotheses[] → final_report.json
```

### 4.2 内部循环 (候选驱动)

P05 配置: `convergence.candidate_driven: true`, `max_candidates: 3`

```
对每个候选 (topic_id):
  ┌─ LLM 查询重写 ─→ 新检索查询
  ├─ S4 搜索 ─→ 论文
  ├─ S5 引文 ─→ 更多论文
  ├─ S6 筛选 ─→ 保留列表
  ├─ S6c 深读 ─→ 笔记
  └─ S7 提取 ─→ 带有 candidate:{id} 标签的卡片

收敛条件: TOPIC_EXHAUSTED (所有候选已处理) | BUDGET_TOKEN_EXCEEDED
```

### 4.3 外层循环

三个 AND 条件（来自原型 config.yaml）:
1. **覆盖 Jaccard**: 最后 2 轮中所有轴对的 Jaccard ≥ 0.70
2. **缺口产出**: new_gap_ratio < 0.30 或 gap_yield_ratio < 0.30
3. **引文网络**: 引文网络穷尽

---

## 5. 评估框架架构

### 5.1 数据加载 (load_p05_data)

```
输入工件 (在管线完成后读取):
┌──────────────────────────────────────────┐
│ data/decompose_pilot_results.json → 候选 │
│ projects/p05/.../evidence_cards.jsonl → 证据 │
│ projects/p05/.../final_report.json → 缺口 │
│ projects/p05/.../final_report.json → 假设 │
└──────────────────────────────────────────┘
                    │
                    ▼
        证据分组 (按 candidate: 标签):
          对每张卡片, 遍历卡片.tags:
            如果以 "candidate:" 开头:
              提取 cid → evidence_maps[cid].append(card)
          
          一张卡可属于多个候选 (多个 candidate: 标签)
          
          v2 增强:
          - CandidateEvidenceLink: 每张卡分类为 supports/contradicts/adjacent/prior_work/dataset/method
          - Paper-level dedup: 同一篇论文的多张卡片只计一次 unique_paper_count
```

### 5.2 Phase 0→3 评估循环

每个候选独立运行（通过 Semaphore 并发，v2 支持并行）:

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 0: MCP 上下文增强                                          │
│   ├─ 支持性检索 (自有术语) + 对抗性检索 (LLM 生成的替代查询)     │
│   ├─ 去重 → LLM 摘要 → mcp_context 字符串                        │
│   └─ MCP 缓存: SearchEngine.search() 查询结果缓存 (TTL=1h)       │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ Phase 1: 初始方案生成                                            │
│   输入: candidate + tagged_evidence_cards (top 10) + gaps +      │
│         hypotheses + mcp_context                                 │
│   LLM 产出: structured JSON (summary_zh, technical_roadmap,     │
│            data_sources_detail, feasibility, innovation_points,   │
│            expected_outputs, target_venues)                       │
│   系统提示: 禁止"首次提出/首个实现/填补空白"等绝对化表述          │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ Phase 1.5: 新颖性验证 (3 次 LLM 调用)                            │
│   ├─ 声明提取 ─→ 查询生成 ─→ MCP 检索 ─→ 重叠判定 (LLM)        │
│   判定: scooped > crowded > adjacent > clear                     │
│   ├─ scooped → reposition_plan() (重新定位方案, 最多1次)         │
│   └─ 产出: Phase15Output (总体判定, 每声明判定, 最接近工作)      │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ Phase 1.6: 红队方法论审查                                         │
│   ├─ 数据声明提取 (从方案中) → 验证 vs 证据卡/已知事实            │
│   ├─ LLM 红队: data_leakage, feedback_validity, baseline_adequacy │
│   └─ 产出: RedTeamOutput (高/中/低严重性发现, 核验/未核验声明)  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ 审查-精炼循环 (max 3 次):                                        │
│   ├─ Phase 2: 方案审查                                           │
│   │   输入: plan + novelty_verdicts + redteam_findings           │
│   │   评审者: 按角色注入专属输入上下文 (v2)                      │
│   │   rubric scoring: 6 维 1-5 评分 → weighted_score             │
│   │   通过: weighted_score ≥ 4.0 AND min_dim ≥ 3.0              │
│   │   边缘候选 (3.7-4.1): RobustCritique 3 角色中位数聚合         │
│   │   产出: CritiqueResult (分数, 详细反馈, 文献缺口)            │
│   │                                                              │
│   ├─ 缺口搜索: search_gap_literature(critique文献缺口)           │
│   │   产出: 新论文列表 (top 10, MCP 缓存感知)                    │
│   │                                                              │
│   └─ Phase 3: 方案精炼                                          │
│       输入: plan + CritiqueResult + gap_literature               │
│       LLM 逐条回应批评, 整合新论文                                │
│       产出: 精炼后的方案 (相同结构)                               │
│       停止条件: 通过 | 停滞 (连续2轮 <0.05变动) | 达最大次数     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ 后循环:                                                          │
│   ├─ 重新验证新颖性 + 红队 (如果方案有变更)                      │
│   ├─ 最终引文核验                                                │
│   └─ 文献覆盖检查 (方案引文 vs 证据卡重叠比)                     │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 LLM 调用计数

| Phase | 每次候选 LLM 调用 | 备注 |
|-------|-------------------|------|
| Phase 0 (查询) | 1 | 对抗性查询生成 |
| Phase 1 (生成) | 1 | 方案生成 |
| Phase 1.5 (新颖性) | 3 | 声明提取 + 查询生成 + 重叠判定 |
| Phase 1.6 (红队) | 1 | 方法学审查 |
| Phase 2 (审查) | 1-3 | 正常 1 次; 边缘候选 3 角色 |
| Phase 3 (精炼) | 1 | 方案精炼 (每迭代) |
| 总计 (3 迭代) | 10-15 | 取决于边缘/非边缘 |

---

## 6. 配置体系

### 6.1 三层配置层次

```
Layer 1: 项目配置
  projects/p05_sc_multiomics_ai/config.yaml
  ├── archetype_id: archetype_c_sc_ai
  ├── skill_sequence: [s1, s2, s3, s4, s5, s6, s6c_deep_read, s7, s8, s9, s11, s12]
  ├── custom decompose axes: scfm_depth × agent_line
  ├── convergence: candidate_driven=true, max_candidates=3
  ├── parameters: min_pretrain_cells=1M, 3+ benchmarks required
  └── deep_read config: max 5 papers/candidate, max 2 Tier-2

Layer 2: 原型配置
  archetypes/archetype_c_sc_ai/config.yaml
  ├── evidence_card_class: archetypes.archetype_c_sc_ai.evidence_card.SCFMEvidenceCard
  ├── gap_patterns: archetypes.archetype_c_sc_ai.gap_patterns (C1-C11)
  ├── coverage_axes: task × modality × tissue × model_architecture × evaluation_setting
  ├── skill_sequence (原型默认): [s1, s2, s3, s4, s5, s6, s7, s8, s9, s11, s12]
  └── parameters: 资金需求, 基准数据集, 可迁移性/可解释性要求

Layer 3: 评估框架配置
  scripts/p05_harness/config.yaml (58 行, 7 节, Pydantic 验证)
  ├── mcp: search_sources, max_per_source=10, year_range, recent_boost_year=2024
  ├── loop: max_iterations=3, pass_threshold=4.0, min_dimension_score=3.0
  │         stagnation_limit=2, max_concurrent_candidates=3
  ├── novelty_check: enabled=true, max_claims=5, queries_per_claim=4, top_k_papers=15
  ├── rubric: 6 × RubricDimension (各含 weight + label_zh + label_en)
  │           权重和验证: sum(weights) == 1.0 (Pydantic 校验器)
  ├── candidates: deep_analysis_count=10, top_n_by_score
  └── output: dir="data/p05_harness_output"
```

### 6.2 配置治理 (v2 新增)

**`config_schema.py`** 提供 Pydantic 模式验证:

```python
class HarnessConfig(BaseModel):
    mcp: MCPConfig
    loop: LoopConfig
    novelty_check: NoveltyCheckConfig
    rubric: RubricConfig          # @model_validator: sum(weights) == 1.0
    candidates: CandidatesConfig
    output: OutputConfig

# load_harness_config(path) → 在加载时验证 YAML
# get_config_manifest() → 24 键的人类可读参考文档
```

**_CONFIG_MANIFEST** 记录了所有 24 个配置键的类型、范围和描述。

### 6.3 全局 Settings

`shared/core/config.py` (pydantic-settings, env_prefix `AISCIENCE_`):

| 类别 | 关键设置 | 默认值 |
|------|---------|--------|
| LLM | `llm_model` | `"gpt-4o-mini"` |
| 缓存 | `llm_cache_enabled` | `False` |
| 缓存 | `llm_cache_ttl_seconds` | `86400` (24h) |
| 缓存 | `mcp_cache_ttl_seconds` | `3600` (1h) |
| 预算 | `total_token_budget` | `5,000,000` |
| 预算 | `budget_extraction` | `0.45` (45%) |
| 限制 | `max_sub_agents_per_project` | `3` |
| 限制 | `mcp_concurrency` | `10` |
| 循环 | `coverage_jaccard_threshold` | `0.70` |
| 循环 | `gap_yield_threshold` | `0.30` |

---

## 7. 仪表板集成

### 7.1 数据流

```
scripts/p05_harness/main.py → data/p05_harness_output/runs/<run>/checkpoint.json
                                      │
                                      ▼
                          dashboard/build_data.py
                            ├── _load_harness_dimensions()        ← 从 config.yaml 加载评分维度
                            ├── _aggregate_harness_runs()         ← 多运行聚合
                            ├── _parse_harness_candidates()        ← 候选扁平化
                            └── _build_p05_harness()              ← 注入 data.json
                                      │
                                      ▼
                          dashboard/data.json
                            → key: "p05_research_plans"
                                      │
                                      ▼
                          dashboard/index.html → App.DATA.p05_research_plans
                                      │
                                      ▼
                          dashboard/js/tabs/p05.js → P05Tab.render()
```

### 7.2 聚合与空值处理

- `_aggregate_harness_runs()`: 多运行去重, 每候选取最佳迭代 (最高 weighted_score)
- 维度平均值: 如果某维度所有候选均无评分 → 仪表板显示为 `null`, JS 渲染为 "-" + "暂无评分数据"
- `dimension_availability`: `"scored"` vs `"no_data"` — 用于 JS 条件渲染

### 7.3 P05 标签页渲染

| 区域 | 内容 |
|------|------|
| 统计行 | 通过/失败计数, LLM 调用数, MCP 调用数, 总耗时 |
| 维度平均值行 | 6 张卡片, 每维平均值 (null → "-") |
| 分组柱状图 | ECharts grouped bar (stack: undefined, barMaxWidth: 14, max=5) |
| 候选卡片网格 | 通过/失败徽章, 分数, 研究问题, 维度点, 迭代次数, 新颖性/红队/证据徽章 |
| 详情模态框 | 新颖性验证 (初始 vs 精炼后), 红队审查, 技术路线, 数据源, 可行性, 创新点, 迭代历史, 评审文本, 引文核验, 证据锚定 |

---

## 8. 质量门控

### 8.1 S7 证据卡片提取质量关卡

`SCFMCardExtract.quality_gate()` (4 子关卡):

| 关卡 | 条件 | 失败动作 |
|------|------|---------|
| **身份** | 所有卡片 key_finding 非空 | FAIL (技能失败) |
| **证据** | 深读来源卡片 ≥ 60% 有 evidence_status | FAIL |
| **领域** | 如果 paper_count > 3: task/task_category 填充率 ≥ 40% | FAIL |
| **基数** | 平均卡片/论文 > 10 | WARNING (不阻塞) |

### 8.2 评分标准质量关卡

`scripts/p05_harness/validators/rubric.py` — 6 维评分标准:

| 维度 (key) | 中文标签 | 权重 | 1 分描述 | 5 分描述 |
|-----------|---------|------|---------|---------|
| `literature_coverage` | 文献覆盖度 | 0.20 | 未引用相关文献 | 全面系统梳理领域文献 |
| `technical_feasibility` | 技术可行性 | 0.20 | 路线图模糊或缺失 | 详细技术路径+应急方案 |
| `innovation_clarity` | 创新性清晰度 | 0.20 | 未区分已有工作 | 清晰差异化+缺口支撑 |
| `data_accessibility` | 数据可及性 | 0.15 | 无数据源 | 含 accession 的具体数据集 |
| `gap_alignment` | 缺口对齐度 | 0.10 | 未关联缺口 | 深层多缺口关联 |
| `evaluation_rigor` | 评估严谨性 | 0.15 | 无基线或指标 | 完整基准+泄露防护 |

**通过条件**: `weighted_score ≥ 4.0 AND 所有维度 ≥ 3.0`

### 8.3 边缘候选 RobustCritique

```
如果 weighted_score ∈ [3.7, 4.1]:
  → 运行 3 次审查 (每个评审者角色各一次)
  → 聚合: 每维中位数 + 加权分中位数
  → 最接近中位数的结果作为 best
  → 稳定性 = stdev(3个加权分)
  → best.passed = 聚合中位数分数 ≥ 4.0 AND min(聚合维度中位数) ≥ 3.0
```

---

## 9. 评审者系统

### 9.1 三角色配置文件

```python
REVIEWER_PROFILES = {
    "generalist": "你是一个严格的学术评审专家，专门评审单细胞多组学领域的研究方案。...",
    "methodologist": "你是一个方法论专家，专注于技术可行性、评估严谨性和数据可及性。...",
    "domain_expert": "你是一个单细胞多组学领域的资深研究者，专注于文献覆盖深度、创新性区分度和领域缺口契合度。...",
}
```

### 9.2 角色专属输入上下文 (v2 新增)

| 角色 | 聚焦区域 | 额外注入内容 |
|------|---------|------------|
| **generalist** | 所有维度 | 完整方案 + 新颖性上下文 + 红队上下文 |
| **methodologist** | technical_feasibility, evaluation_rigor, data_accessibility | 技术路线摘要, 数据源细节, 可行性评估, 方法论红队发现 |
| **domain_expert** | literature_coverage, innovation_clarity, gap_alignment | 研究摘要, 创新点列表, 预期成果, 新颖性预警 (领域竞争) |

通过 `_format_methodologist_focus()` / `_format_domain_expert_focus()` 从计划中提取并格式化角色专属内容。

### 9.3 维度强调注入

```python
REVIEWER_DIMENSION_EMPHASIS = {
    "generalist": "",
    "methodologist": "请特别关注技术可行性、评估严谨性和数据可及性维度...",
    "domain_expert": "请特别关注文献覆盖度、创新清晰度和领域空白契合度维度...",
}
```

---

## 10. 证据锚定系统 (v2 完整)

### 10.1 CandidateEvidenceLink

每次运行中为每个候选构建:

```
_build_candidate_links(cards, candidate)
  ├─ 按 paper_doi/paper_title 去重 ─→ unique_paper_count
  ├─ 每张卡: _classify_card_relation(card, candidate)
  │   └─→ relation: supports | contradicts | adjacent | prior_work | dataset | method
  └─→ list[CandidateEvidenceLink] + relation_counts
```

**relation_counts** 示例: `{supports: 12, adjacent: 4, prior_work: 3, dataset: 1}`

### 10.2 GapEvidenceLink

每个缺口与每张匹配卡片的关联:

```
GapEvidenceLink (在 _build_gap_evidence_links() 中构建)
  matched_field: "held_out_cell_types"
  matched_rule: "not_confirmed"
  weight: 1.0  (如果 EvidenceState 为 REPORTED_NOT_DONE)
          0.55 (如果 EvidenceState 为 NOT_REPORTED)
          0.0  (其他情况)
  rationale: "Card xxx: held_out_cell_types=reported_not_done (论文明确声明未做)"
```

### 10.3 缺口加权评分

C3/C5/C6/C9 缺口 (EvidenceState 感知缺口) 的评分公式:

```
evidence_weight = Σ(EVIDENCE_STATE_WEIGHTS[state] for each matching card)
gap.score = base + weight × (evidence_weight / effective_denominator)

示例 (C3, 1335 卡):
  假设 800 张 REPORTED_NOT_DONE (1.0), 200 张 NOT_REPORTED (0.55), 78 张 CONFIRMED
  分母 = 1078, 分子加权 = 800×1.0 + 200×0.55 = 910
  gap.score = 0.35 + 0.45 × 910/1078 ≈ 0.73
  gap.gap_confidence = 0.3 + 0.7 × 1078/1335 ≈ 0.87
```

缺口描述包含状态分布信息:
```
"1078/1335 cards lack held-out cell type evaluation (explicit_no=800, unreported=200, confirmed=78)"
```

### 10.4 证据来源回退

```
tagged_cards = evidence_cards_by_candidate[cid]
evidence_fallback = len(tagged_cards) == 0

if evidence_fallback:
    cards = all_cards_pool (所有候选的所有卡片)       ← 黄色 "全库" 徽章
    evidence_source = "fallback_pool"
else:
    cards = tagged_cards                              ← 绿色 "N 卡片" 徽章
    evidence_source = "tagged"
```

---

## 11. 缓存与并行

### 11.1 LLM/MCP 缓存

**shared/core/cache.py** — SQLite 缓存层:

```
ResponseCache (单例, 异步安全)
├── 存储: data/response_cache.db
├── 表: cache(key TEXT PK, namespace TEXT, value TEXT, created_at REAL, expires_at REAL)
├── 索引: expires_at (自动清理过期条目)
├── 命名空间: "llm" (TTL: configurable, 默认 24h), "mcp" (TTL: 1h)
├── 键派生: SHA-256("v1|{model}|{system}|{prompt}|{temperature}|{max_tokens}")
│            ↑ CACHE_VERSION 前缀 → 版本升级时自动失效所有缓存
├── 操作: get(namespace, *key_parts) → str|None
│         set(namespace, value, ttl, *key_parts) → void
│         invalidate(namespace=None) → int
└── 错误处理: 所有缓存操作在失败时静默降级 (不阻塞)
```

### 11.2 候选级并行 (v2 新增)

```
LoopRunner.run():
  candidates → asyncio.Semaphore(max_concurrent_candidates=3)
  ↓
  每个候选 = 独立 SearchEngine 实例 + 独立 MCP 上下文
  
  共享状态保护:
    asyncio.Lock(_result_lock)   → candidate_results, total_llm, total_mcp
    asyncio.Lock(_checkpoint_lock) → 检查点文件 read-modify-write
```

**并行化危害及解决**:

| 共享状态 | 风险 | 保护机制 |
|---------|------|---------|
| 检查点文件 | 读写竞态 (B 丢失) | `_checkpoint_lock` |
| 候选结果列表 | `asyncio.gather` 顺序不确定 | `_result_lock` + order_map 恢复排序 |
| LLM/MCP 计数器 | `+=` 非原子 | `_result_lock` |
| SearchEngine 内部计数器 | delta 计算错误 | 每候选独立实例 |
| 结果文件 | 多次写入覆盖 | 仅主运行器写 (不并行) |

---


## 12. 关系数据库持久化 (v2.1 新增)

### 12.1 架构定位

数据库是**独立于管道的下游持久化层**。管道产出物 (JSONL/JSON) 作为真实数据源，数据库通过 `backfill_from_jsonl.py` 回填脚本消费管道产物。管道不感知数据库的存在，二者完全解耦。

```
管道 (不感知DB)
  ├── evidence_cards.jsonl  ──→ backfill_from_jsonl.py ──→ knowledge.db (evidence_cards)
  ├── final_report.json     ──→                          ──→ knowledge.db (gaps, hypotheses)
  ├── summary.json          ──→                          ──→ knowledge.db (runs)
  └── decompose_pilot_results.json ─→                   ──→ knowledge.db (projects, candidates)
```

### 12.2 双层架构

| 层 | 表 | 生命周期 | 用途 |
|------|-----|------|------|
| **全局知识层** | `sources`, `deep_read_notes`, `evidence_cards`, `card_evidence_states` | 永久, 跨项目 | 论文来源、S6C 深读笔记、S7 证据卡 (DWH) |
| **项目研究层** | `projects`, `candidates`, `runs`, `gaps`, `gap_evidence_links`, `hypotheses` | 按 run 版本化 | 研究进程、缺口检测、假设生成 |

### 12.3 核心表与 Python 模型映射

| 数据库表 | Python 模型 | 关键字段 |
|---------|------------|---------|
| `sources` | `SourcePaper` (base_card.py) | `paper_id` (DOI PK), `title_norm`+`year` (去重回退), FTS5 全文索引 |
| `deep_read_notes` | `DeepReadNote` (deep_read/schemas.py) | `facts`/`claims`/`judgments`/`formulas` (JSON), `reading_depth` (tier1/tier2) |
| `evidence_cards` | `SCFMEvidenceCard` | `archetype` (索引), `payload` JSON (原型特定 35-48 字段), `evidence_status`/`evidence_strength` (深读富集) |
| `card_evidence_states` | `EvidenceState` 枚举 | 每个 `state_field` + `state_value` 独立行, 支持 SQL `WHERE state_value = 'confirmed'` 直接统计 |
| `candidates` | decompose 候选项 | `dimensions` JSON (自定义轴值), `scores` JSON, `research_line` (scfm_depth/agent_line) |
| `card_candidate_links` | 替代 `tags:"candidate:{id}"` | FK 关联, `relevance_score`, `matched_criterion` |
| `runs` | 管道/harness 运行记录 | `converged`, `total_cards`, `duration_s`, timeline |
| `gaps` | `IdentifiedGap` | `pattern_id` (C1-C12, E1-E10, P3/P9/P10), `score`, `gap_confidence` |
| `gap_evidence_links` | `GapEvidenceLink` | `matched_field`, `matched_rule`, `weight`, `rationale` — SQL-native 缺口统计 |
| `hypotheses` | `Hypothesis` | `addresses_gap` FK, `novelty_score`, `feasibility_score`, `expected_impact` |

### 12.4 设计决策

| 决策 | 理由 |
|------|------|
| **SQLite + JSON1 + FTS5** | 与现有 `response_cache.db` 技术栈一致, 零依赖 |
| **原型特定字段入 payload JSON** | 避免宽表 (SCFMEvidenceCard 48 列, V2GEvidenceCard 35+ 列), `schema_version` 保证向后兼容 |
| **EvidenceState 拆分行** | 从 8 个 sparse 列变为行式存储, 可 SQL-native 按状态分组统计, 直接驱动缺口检测 |
| **card_candidate_links 替代 tag 字符串** | tag 方式 (`"candidate:{id}"`) 需解析字符串, 无法使用 FK 约束和 JOIN |
| **DOI unique 索引 + title_norm 回退** | 两阶段去重: DOI 精确匹配 → 标准化标题+年份近匹配 |
| **每次运行版本化 (run_id FK)** | gaps/hypotheses/deep_read_notes 均通过 run_id 关联, 支持同一个 project 多次运行的结果共存和对比 |

### 12.5 全文搜索 (FTS5)

```sql
-- 在标题和摘要中搜索 "colocalization" 相关论文
SELECT s.title, s.year, s.doi
FROM sources_fts f
JOIN sources s ON f.rowid = s.rowid
WHERE sources_fts MATCH 'colocalization OR coloc OR GWAS'
ORDER BY rank;
```

FTS5 通过触发器与 `sources` 表保持同步 (INSERT/UPDATE/DELETE 自动更新索引)。

### 12.6 数据完整性验证

```bash
python data/validate_schema.py        # 创建 knowledge.db 并校验 12 表 + 3 视图 + FTS5 结构
python data/backfill_from_jsonl.py    # 从管道产物回填数据 (--project p05 单项目, --fresh 重建)
```

### 12.7 与 LLM 缓存数据库的区别

| 特性 | `data/knowledge.db` | `data/response_cache.db` |
|------|-------------------|--------------------------|
| **用途** | 文献/知识管理持久化 | LLM API 响应缓存 |
| **表数** | 12 表 + 3 视图 + FTS5 | 1 表 (`cache`) |
| **键** | 业务主键 (DOI, card_id, hypothesis_id) | SHA-256 哈希 (prompt+model) |
| **生命周期** | 永久 (管道回填追加) | 按 TTL 过期 (LLM=24h, MCP=1h) |
| **写入口** | `backfill_from_jsonl.py` | `shared/core/cache.py` ResponseCache |
| **查询方式** | 业务 SQL + FTS5 全文搜索 | KV 查找 (key + namespace) |

---

## 13. 关键架构模式

### 13.1 标签基准证据链接

```
S7 卡片提取: tags.append("candidate:{topic_id}")
评估框架: card.tags 中匹配 "candidate:" → evidence_maps[cid].append(card)
一张卡可属于多个候选 (多个标签)
```

### 13.2 原型常量 (Phase 1.6)

```python
# base_card.py
ARCHETYPE_V2G = "v2g"
ARCHETYPE_PRS = "prs"
ARCHETYPE_SC_FM = "sc_fm"           ← P05 使用
ARCHETYPE_OMICS_SCORE = "omics_score"
ARCHETYPE_CROSS_ETHNIC = "cross_ethnic_multiomics"  ← v2.1 新增
ARCHETYPE_BASE = "base"
VALID_ARCHETYPES = frozenset(...)

# 在 S11 和 S12 中使用 (而非字符串字面量)
def _has_sc_fm_fields(cards): return any(getattr(c, "archetype", "") == ARCHETYPE_SC_FM for c in cards)
```

### 13.3 双路径 S7 提取

```
S7 (Archetype C):
  ├── 有深读笔记? → _extract_from_deep_read()
  │   ├── 启发式枚举匹配 (task/modality/architecture/model_family/tissue)
  │   ├── 缺失关键字段 → 轻量级 LLM 补充
  │   └── 每事实 1 张卡片 + evidence_status/strength 继承
  │
  └── 无深读笔记? → _extract_from_paper() (LLM 全文提取)
```

### 13.4 单模型 LLM 调用 (可升级)

所有 LLM 调用统一使用 `litellm.acompletion()`, 模型可按调用方覆盖 (`llm_complete(model=...)`)。当前默认: `gpt-4o-mini` (可通过 `AISCIENCE_LLM_MODEL` 环境变量配置)。

### 13.5 评审者角色分离 (Phase 2.1)

```
普通审查: 1 次调用, generalist 角色
边缘候选: 3 次调用 (generalist → methodologist → domain_expert), RobustCritique.aggregate()
         → 每维中位数, 选最接近中位数的结果作为 best
```

### 13.6 配置治理 (Phase 3.3)

```
YAML → load_harness_config() → Pydantic HarnessConfig 验证 → model_dump() 用于向后兼容
验证: 类型检查 + 范围检查 + 权重和必须等于 1.0
_CONFIG_MANIFEST: 供程序化访问的 24 键人类可读参考
```

### 13.7 无用卡片静默丢弃 (extra="ignore")

所有基础卡片类使用 `model_config = {"extra": "ignore"}`, 允许跨原型的 `model_validate()` 转换 —— 额外字段被丢弃, 新字段获得默认值。

### 13.8 EvidenceState 生命周期

```
NOT_EXTRACTED (初始值) → CONFIRMED | REPORTED_NOT_DONE | NOT_REPORTED
                            ↑ 明确提取         ↑ 明确提取         ↑ 未提及
                          
多源冲突 → CONFLICTING (需要人工审查)
字段不适用 → NOT_APPLICABLE (排除在缺口分析之外)
```

---

## 14. v2.1 变更摘要

### 从 v2.0 新增

| 区域 | 变更 |
|------|------|
| **数据模型** | 新增关系数据库持久化层 (knowledge.db, 12 表 + 3 视图 + FTS5) |
| **数据模型** | 全局知识层: sources (论文去重), deep_read_notes (S6C 深读笔记), evidence_cards (原型特定字段入 payload JSON), card_evidence_states (EvidenceState 拆分行) |
| **数据模型** | 项目研究层: projects, candidates, runs, gaps, gap_evidence_links, hypotheses — 均按 run_id 版本化 |
| **数据模型** | card_candidate_links 替代 tag 字符串匹配, 使用 FK 约束 |
| **数据集成** | backfill_from_jsonl.py: 5 阶段回填 (decompose → summary → cards → gaps → harness) |
| **数据库** | schema.sql: SQLite WAL 模式, JSON1 扩展, FTS5 全文搜索 (title+abstract) |
| **数据库** | 3 视图: v_confirmed_states, v_gap_summary, v_hypothesis_list |
| **架构** | 数据库为下游持久化层, 管道不感知其存在, 通过文件系统解耦 |
| **配置** | GWAS 集成: C12 缺口 (no_gwas_integration), SCFMEvidenceCard 5 个 GWAS 字段, decompose 截断修复 |

### v2.0 变更摘要 (保留)

### 从 v1 新增

| 区域 | 变更 |
|------|------|
| **数据模型** | EvidenceState: 3 → 6 值 (NOT_EXTRACTED, CONFLICTING, NOT_APPLICABLE) |
| **数据模型** | GapEvidenceLink 模型 (card_id, matched_field, matched_rule, weight, rationale) |
| **数据模型** | CandidateEvidenceLink 模型 (relation, relevance_score, link_method, paper_id) |
| **数据模型** | CandidateLoopResult: evidence_links, evidence_link.unique_paper_count, relation_counts |
| **S7 质量门控** | 身份/证据/领域/基数 4 关卡 |
| **S11 缺口** | 加权缺口评分 (按 EvidenceState 权重分布) |
| **S11 缺口** | GapEvidenceLink: 每张匹配卡片的触发字段/规则/权重/理由 |
| **S11 缺口** | 缺口描述含明确未做/矛盾计数 |
| **评估框架** | 3 评审者角色 + 角色专属输入上下文 (methodologist 技术路线, domain_expert 创新点) |
| **评估框架** | RobustCritique: 角色轮换 (generalist→methodologist→domain_expert), raw_response 含 profiles_used |
| **评估框架** | CritiqueResult: reviewer_profile 字段, score_stability 记录 |
| **性能** | LLM 缓存 (SQLite, SHA-256, TTL) → 仅在 llm_cache_enabled=true 时激活 |
| **性能** | MCP 缓存 (SearchEngine.search, TTL=1h) |
| **性能** | 缓存版本化 (CACHE_VERSION="v1" 前缀 → 升级即失效) |
| **性能** | 候选级并行 (asyncio.gather + Semaphore + 锁保护) |
| **配置** | Pydantic 配置模式 (HarnessConfig 7 子模型) |
| **配置** | _CONFIG_MANIFEST (24 键文档) |
| **配置** | load_harness_config() 验证替代 yaml.safe_load |
| **仪表板** | dimension_availability: "scored"/"no_data" — 0.0 空值变为 null |
| **仪表板** | 证据锚定徽章 ("N 卡片" 绿色, "全库" 黄色) |
| **仪表板** | 详情模态框 → 证据锚定区块 (卡片数/池比率/回退警告) |

### 测试覆盖

140 个测试, 分布于:

| 测试文件 | 测试数 | 覆盖领域 |
|---------|--------|---------|
| `test_p05_harness_e2e.py` | 15 | E2E 评估框架, 边界案例, 新颖性+红队 |
| `test_novelty_verify.py` | 40+ | 新颖性验证器回归测试 |
| `test_scfm_card_extract.py` | 27 | SCFMCardExtract: 字段默认值, 质量关卡, 无关性过滤, 枚举匹配, 深读 |
| `test_gap_analysis.py` | 10+ | GapPattern, IdentifiedGap, 原型检测, 缺口执行 |
| `test_base_card.py` | 10+ | BaseEvidenceCard, V2GEvidenceCard, EvidenceState |
| `test_loop_engine.py` | 8 | 循环引擎枚举 |
| 其他 | ~30 | 覆盖矩阵, 原型实例化 |

---

> **文档维护**: 当添加新评估框架阶段或新原型字段时更新本文档。变更摘要应追踪每个版本在该文件中的新增/修改内容。
