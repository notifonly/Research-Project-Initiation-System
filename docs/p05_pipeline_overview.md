# P05 项目架构与管线

> 版本: v1 · 日期: 2026-07-22
> 适用项目: p05_sc_multiomics_ai (archetype_c_sc_ai)
> 研究方向: 单细胞基础模型架构评估 + AI Agent 自适应基准

---

## 概览

P05 有**两条独立管线**:

| 管线 | 入口 | 用途 | LLM 调用 |
|---|---|---|---|
| **管线 A — 主研究** | `python main.py --only p05_sc_multiomics_ai` | 12-skill 论文挖掘 + 证据卡 + 缺口 + 假设 | 是 (S1/S2/S4/S5/S6C/S7/S9/S11/S12) |
| **管线 B — 质量评估** | `python scripts/p05_harness/main.py` | 研究计划生成→评审→优化→验收 | 是 (独立 LLM 调用) |

两条管线通过 `candidate:topic_id` 标签在 evidence_cards 上关联，但评估管线使用**独立的 LLM + MCP 调用**。

---

## 管线 A — 主研究管线

### 调用链

```
main.py --only p05_sc_multiomics_ai
  │
  └─ projects/__init__.py._p05()
        └─ projects/p05_sc_multiomics_ai/tool_flow.py.run_project()
              │
              └─ Orchestrator(archetype_id="archetype_c_sc_ai")
                    │  合并 archetype 模板 + project config (后者覆盖前者)
                    │  注入 EXTRA_SKILLS:
                    │    s7_evidence_card_extract  → SCFMCardExtract (700行, 覆盖共享S7)
                    │    s6a_scfm_search           → SCFMSearchSkill (备用, 当前 skill_sequence 中未启用)
                    │
                    └─ LoopEngine (候选驱动内循环)
                          │  convergence.candidate_driven: true
                          │  convergence.candidate_source: decompose_pilot_results
                          │  convergence.max_candidates: 3
                          │  convergence.max_outer_rounds: 8
                          │
                          ├─ Phase 1: _run_scoping()    → S1, S2, S3
                          ├─ Phase 2: _run_inner_loop()  → S4-S10 (候选轮转)
                          └─ Phase 3: _run_synthesis()   → S11, S12
```

### 12-Skill 序列

```
S1  方向分解 ─── 自定义分解轴 (见下方)
S2  术语规范化
S3  资源收集 ─── skill_03_fm_resource_collect.py (archetype C 特定)
     │
S4  多源搜索 ─── 13个MCP源: semantic_scholar, pubmed, huggingface, github... (见config.yaml mcp_priorities)
S5  引用滚雪球
S6  文献筛选
     │
S6C 深度阅读 ─── ★ 分叉步骤 (divergent_step)
     │  每候选最多5篇论文, 其中2篇Tier-2
     │  6阶段:
     │    Stage 1:    论文身份注册
     │    Stage 2+3:  事实提取 + 声明-证据审计 (合并LLM调用)
     │    Stage 4:    公式推导链 + 实验分析 (仅Tier-2)
     │    Stage 4B:   公式反驳双审计 构造→反驳 (仅Tier-2)
     │    Stage 5:    批判性评估 (仅Tier-2)
     │    Stage 6:    程序化质量门 (5 gates, 所有论文)
     │  输出: deep_read_notes[].facts/claims/judgments
     │
     ├── deep_read_notes 传递到 S7
     │
S7  证据卡提取 ─── ★ 自定义覆盖 (SCFMCardExtract)
     │  双路径:
     │    A. _extract_from_deep_read():     启发式同义词映射 → 填充枚举字段
     │       若启发式失败 → _llm_extract_missing_fields() 轻量LLM补充
     │    B. _extract_from_paper():          全LLM提取 (回退路径)
     │  quality_gate:
     │    0 findings → 拒绝 (False)
     │    fill_rate < 15% 且 paper_count > 3 → 拒绝
     │  输出: SCFMEvidenceCard (archetype="sc_fm", 50+字段)
     │
S8  数据可用性
S9  方法-数据集匹配
     │
S11 缺口分析 ─── 11个 C 模式 (C1-C11)
     │  检测: card.archetype == "sc_fm" (字符串检测, 不用字段值)
     │  supporting_cards: 过滤列表前10张卡
     │  评分: weight_evidence_asymmetry(0.35) + feasibility(0.25)
     │        + (1-competition)(0.20) + cross_archetype(0.20)
     │  top_gaps: 前5个缺口
     │
S12 假设生成 ─── archetype感知格式化 + CRITICAL约束防疾病漂移
     │  sc_fm 卡格式: task|model_family|tissue (替代V2G的trait_label|locus|modality)
```

### 自定义分解轴

不同于默认 `disease×tissue×method×data×population`，p05 使用**两个自定义轴组**:

```
scfm_depth (5轴):
  architecture_family × modality_combination × training_paradigm
  × pretraining_corpus × evaluation_paradigm

agent_line (2轴):
  agent_paradigm × capability
  (种子: GitHub awesome-list → "AI Agents & Platforms" 章节)
```

### 覆盖轴

```
task × modality × tissue × model_architecture × evaluation_setting

modality 折叠规则:
  modalities_integrated 非空 → "multi"
  modality_omics 有值    → modality_omics
  否则                     → "single"

model_architecture 回退:
  model_architecture → model_family → "unknown"

evaluation_setting:
  held_out_cell_types 有值  → "held_out_celltype"
  held_out_tissues 有值     → "held_out_tissue"
  否则                       → "standard"
```

### 收敛条件

```
内循环 OR (任一满足):
  query_exhausted    | citation_closed | reflection_confirmed | budget_token_exceeded

外循环 AND (全部满足):
  coverage_jaccard_gt_0.95_k2
  gap_yield_lt_20pct_new
  citation_network_closed

兜底: budget_failsafe: always_active
```

### 证据卡: SCFMEvidenceCard

```
SCFMEvidenceCard(BaseEvidenceCard)  archetype="sc_fm"
  ├─ 基础字段 (继承): card_id, source_paper, source_location, key_finding, method_brief...
  ├─ 覆盖轴字段: task, task_category, modality_omics, modalities_integrated, tissue,
  │               cell_type, model_architecture, model_family, evaluation_setting
  ├─ 模型细节:    pretext_task, pretext_objective, downstream_task,
  │               n_cells_pretrain, n_cells_finetune, n_parameters, embedding_dim
  ├─ 评估指标:    eval_metric_name, eval_metric_value, baseline_method, baseline_metric_value,
  │               improvement_over_baseline
  ├─ 布尔标志:    held_out_cell_types, held_out_tissues, batch_correction_evaluated,
  │               transfer_evaluated, interpretability_assessed,
  │               code_available, weights_available, dataset_available
  └─ 深度阅读富化: evidence_status, evidence_strength, deep_read_source
```

### 缺口模式: C1-C11

| ID | 名称 | 描述 | 权重特征 |
|----|------|------|----------|
| C1 | single_omics_only | 仅在单一组学模态训练 | 默认 |
| C2 | no_benchmark | 无标准化基准 | 默认 |
| C3 | no_celltype_heldout | 分布内评估, 无保留细胞类型 | 默认 |
| C4 | weak_baseline | 弱基线 (PCA/logistic) | evidence 0.30, feasibility 0.30 |
| C5 | weights_unavailable | 预训练权重未发布 | evidence 0.25, feasibility 0.40 |
| C6 | no_transfer_eval | 跨组织/跨疾病迁移未评估 | evidence 0.30, feasibility 0.30 |
| C7 | single_tissue | 仅在单一组织上预训练 | evidence 0.30, competition 0.25 |
| C8 | scalability_untested | 未测试 >10M 细胞规模 | evidence 0.25, feasibility 0.30 |
| C9 | interpretability_missing | 无可解释性分析 | evidence 0.25, feasibility 0.35 |
| C10 | no_multimodal_integration | 仅单模态 | evidence 0.30, feasibility 0.35 |
| C11 | architecture_homogeneity | 仅Transformer架构 | 默认 |

### 产出文件

```
projects/p05_sc_multiomics_ai/output/
  ├─ evidence_cards.jsonl    # 扁平化卡 (1172张, source_paper/source_location 展开为点分隔键)
  ├─ coverage_map.json       # 覆盖矩阵 (67 cells, 5轴)
  ├─ final_report.json       # 汇总: 卡/缺口/假设/收敛状态
  └─ summary.json            # 轻量摘要
```

---

## 管线 B — 质量评估管线

### 调用链

```
python scripts/p05_harness/main.py [--deep-only] [--merge run1,run2] [--candidates-file ...]
  │
  └─ LoopRunner (评审-优化循环)
        │  config: scripts/p05_harness/config.yaml
        │  pass_threshold: 4.0/5.0, min_dimension_score: 3.0
        │  max_iterations: 3, stagnation_limit: 2
        │
        │  候选来源:
        │    decompose_pilot_results.json → scFM 候选 (topic_id 格式)
        │    p05_agent_candidates.json     → Agent 候选 (candidate_id 格式)
        │
        │  evidence_cards:
        │    优先: 标注 candidate:topic_id 的卡
        │    回退: 全局卡片池 (1172张, 仪表盘标记)[回退全库证据卡]
        │
        └─ 每候选:
              │
              ├─ Phase 0: MCP上下文丰富化
              │    对抗查询生成 → 多源搜索 (semantic_scholar, pubmed, biorxiv, arxiv)
              │
              ├─ Phase 1: 初步研究计划生成 (LLM)
              │    含: summary_zh, technical_roadmap, data_sources_detail,
              │         feasibility, innovation_points, expected_outputs
              │
              ├─ Phase 1.5: 对抗性新颖性验证
              │    claims提取 (LLM) → 对抗查询 (LLM) → MCP搜索 → 重叠判定 (LLM)
              │    判定: scooped | crowded | adjacent | clear | insufficient_evidence
              │    scooped → reposition_attempts: 1 (重新定位后再次验证)
              │
              ├─ Phase 1.6: 方法论红队评审 (LLM)
              │    风险发现 (H/M/L) + 数据声称验证 (MCP)
              │
              ├─ Phase 2: 多维评审 (6维度评分量表)
              │    build_critique_prompt() → LLM → CritiqueResult.from_llm_response()
              │    维度缺项 → 默认 2.0
              │    边缘分数 (3.7-4.1) → RobustCritique (3次重复取中位数)
              │    缺口文献搜索: search_gap_literature() → MCP补充
              │
              ├─ Phase 3: 计划优化 (LLM)
              │    基于评审 + 缺口文献重写计划
              │    优化后: 若计划变化 → 重新验证 新颖性 + 红队
              │
              └─ 循环后:
                    引用验证 (DOI/PMID/作者-年份 按类型上限验证)
                    文献覆盖检查
                    最优迭代选定 (按 weighted_score)
```

### 评审评分量表

```
维度               权重    标签              分数描述等级
─────────────────────────────────────────────────────
literature_coverage  0.20  文献覆盖度         1-5 (盲点→全面)
technical_feasibility 0.20  技术可行性         1-5 (不可行→稳健)
innovation_clarity   0.20  创新性清晰度        1-5 (模糊→清晰独特)
data_accessibility   0.15  数据可及性          1-5 (不可用→公开就绪)
gap_alignment       0.10  缺口对齐度          1-5 (无关→完美对齐)
evaluation_rigor    0.15  评估严谨性          1-5 (随意→系统严格)

weighted_score = Σ(score_i × weight_i)           权重和 = 1.00
pass = weighted_score ≥ 4.0 AND min(scores) ≥ 3.0
```

### 产出文件

```
data/p05_harness_output/
  ├─ harness_result.json      # 最终聚合产物
  │   passed_count, failed_count
  │   total_llm_calls, total_mcp_calls, total_duration_s
  │   dimension_averages (6维)
  │   candidates[].iterations[].scores/weighted_score/passed/critique_text...
  │
  ├─ latest_run.txt           # 参与聚合的运行名列表
  │
  └─ runs/{name}/
      ├─ checkpoint.json      # 增量检查点 (每候选完成后写入)
      └─ harness_result.json  # 单次运行产物
```

---

## 目录结构

```
projects/p05_sc_multiomics_ai/
├─ config.yaml                    # 139行 - 自定义分解轴 + deep_read参数 + Agent发现
├─ tool_flow.py                   # 173行 - Orchestrator入口 + EXTRA_SKILLS注入
└─ output/                        # 主管线产出
    ├─ evidence_cards.jsonl
    ├─ coverage_map.json
    ├─ final_report.json
    └─ summary.json

archetypes/archetype_c_sc_ai/
├─ config.yaml                    # 证据卡类 + gap模式 + 覆盖轴 + 技能序列
├─ evidence_card.py               # SCFMEvidenceCard (74行, archetype="sc_fm", 50+字段)
├─ gap_patterns.py                # 11个C模式 (C1-C11)
└─ skills/
    ├─ skill_03_fm_resource_collect.py    # S3 - 资源收集
    └─ skill_07_scfm_card_extract.py      # S7 - 自定义提取 (700行)
        ├─ SCFM_DOMAIN_PROMPT
        ├─ _is_irrelevant()               # 不相关论文预过滤
        ├─ _extract_from_deep_read()      # 深度阅读启发式路径
        ├─ _extract_from_paper()          # 全LLM回退路径
        ├─ _llm_extract_missing_fields()   # LLM枚举补充
        ├─ _extract_fields_from_facts()    # 同义词启发式映射
        ├─ _match_enum()                  # 枚举值+同义词匹配
        └─ quality_gate()                 # 填充率门控

scripts/p05_harness/               # 14个模块, ~75KB
├─ config.yaml                    # 评估配置 (MCP源, 循环参数, 评审量表, 新颖性)
├─ main.py                        # 入口 (431行) - CLI + run_harness
├─ loop_runner.py                 # 核心评审-优化循环 (666行)
├─ report.py                      # Markdown验收报告 (242行) - RUBRIC_DIMENSIONS驱动
├─ phases/
│   ├─ phase1_generate.py         # 计划生成 + _fallback_plan() stub
│   ├─ phase15_novelty_verify.py  # 新颖性: claims→queries→MCP→judge
│   ├─ phase2_critique.py         # 多维评审 + search_gap_literature()
│   └─ phase3_refine.py            # 基于评审+缺口文献的计划优化
├─ mcp/
│   ├─ search_engine.py           # 跨源MCP搜索 (return_exceptions=True)
│   └─ query_generator.py         # LLM查询生成
└─ validators/
    ├─ rubric.py                  # 6维评分量表 + CritiqueResult + RobustCritique
    ├─ citation_verifier.py       # 引用真实性验证 (DOI/PMID上限)
    ├─ literature_check.py        # 证据覆盖率
    ├─ completeness_check.py      # 结构验证
    └─ methodology_redteam.py     # 方法论弱点检测 + 数据声称验证

data/
├─ decompose_pilot_results.json   # 48个scFM候选 (topic_id格式 p05_sc_multiomics_ai_T000..)
├─ p05_agent_candidates.json      # Agent候选 (Router/Bandit/Self-Evolving)
└─ p05_harness_output/            # 评估管线产出

dashboard/
├─ js/tabs/p05.js                 # P05方案质量 标签页 (443行)
│   6 DIM_KEYS → 分组柱状图 → 候选卡片 → 详情弹窗
│   弹窗含: 迭代评分历史, 新颖性验证, 红队发现, 引用验证, 技术路线图
├─ build_data.py                  # _build_p05_harness() + _aggregate_harness_runs()
└─ index_standalone.html          # 独立HTML (data.json内嵌)

tests/
├─ test_p05_harness_e2e.py        # E2E - scooped/reposition/skip_mcp流程 (412行)
├─ test_novelty_verify.py         # Phase 1.5 新颖性验证 (698行)
└─ test_scfm_card_extract.py      # S7 回归测试 (21 tests, Phase 2.1产出)

scripts/
├─ generate_coverage_maps.py      # 覆盖图生成 (archetype感知, V2G字段过滤)
├─ decompose_directions.py        # 方向分解 (--projects p05 使用自定义轴)
├─ rerun_p05_p06_p07.py           # 重跑 S11+S12
└─ validate_p05_consistency.py    # 跨模块一致性验证 (Phase 3.1产出)
```

---

## 管线关系图

```
┌─────────────────────────────────┐
│     decompose_pilot_results      │
│     (48 scFM 候选)                │
│     p05_agent_candidates.json    │
│     (Agent 候选)                  │
└──────────┬──────────────────────┘
           │
           ├──────────────────────────────────┐
           │                                  │
     ┌─────▼──────────┐              ┌────────▼──────────┐
     │  管线 A (主)     │              │  管线 B (评估)      │
     │  12-skill 序列   │              │  Phase 0→3 循环    │
     │                  │              │                    │
     │  evidence_cards  │──candidate:─→│  标注卡匹配         │
     │  1172张          │  topic_id    │  回退: 全库         │
     │                  │              │                    │
     │  coverage_map    │              │  rubric评分         │
     │  67 cells        │              │  6维×3轮迭代        │
     │                  │              │                    │
     │  11 gaps         │              │  通过阈值 ≥4.0      │
     │  5 hypotheses    │              │                    │
     └────────┬─────────┘              └────────┬──────────┘
              │                                  │
              │                         harness_result.json
              │                                  │
              ├──────────── build_data.py ───────┘
              │
              ▼
        dashboard/data.json
              │
              ▼
        index_standalone.html
              │
              ▼
        P05方案质量 标签页
        6维分组柱状图 + 候选卡片 + 详情弹窗
```

---

## 关键设计决策

1. **候选驱动内循环**: 每个候选独立处理 S4-S10, 外层收敛判断全局覆盖饱和度
2. **S6C 深度阅读作为分叉步骤**: 替代遗留 s6a_scfm_search, 提供结构化 evidence-ledger 格式
3. **S7 完全覆盖共享实现**: 必需 — scFM 论文有 38 个领域特定字段, 共享 S7 的 `llm_structured(list)` 方法产生 schema 冲突
4. **深度阅读优先, LLM 补充**: S7 启发式路径减少 LLM 调用; 仅当枚举字段为空时触发轻量 LLM
5. **评估管线 vs 主管线独立**: 评估使用独立 LLM/MCP 调用, 不对主管线评分产生循环依赖
6. **Archetype 字符串检测**: S11 缺口分析使用 `c.archetype` 而不是字段值来检测 — 当卡片在 archetype 之间转换时, 字段可能为 None 但 archetype 字符串始终可靠
7. **评估维度单一数据源**: 仪表盘 `DIM_KEYS` 与 `rubric.py RUBRIC_DIMENSIONS` 在 `build_data.py` 中对齐, 防止分叉

---

## 已知问题与限制

| 问题 | 影响 | 状态 |
|------|------|------|
| gap supporting_cards 切片 `[:10]` 导致多缺口共享相同支持卡片 | 缺口质量信号不可靠 | 未修复 (S11 上游) |
| 评估管线每候选耗时 10-20分钟 (含 MCP 搜索) | 10候选 ~3-6小时 | 需要分批运行 |
| Agent候选无主管线 evidence_cards (不经过 S1-S12) | 评估管线回退到全局库 | 需手动合并 |
| harness_result.json 维度依赖运行时的 rubric 版本 | 旧运行可能缺维度 | build_data.py 补齐 0.0 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1 | 2026-07-22 | 初始架构文档 — 两条管线+目录结构+关系图 |
