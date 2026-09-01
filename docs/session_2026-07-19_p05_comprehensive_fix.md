# P05 全面修复 — Session Work Journal

**Date**: 2026-07-19
**Session**: 基于 3 个探索代理系统审查 60+ 问题，修复覆盖流水线 loop engineering + P05 Harness + 文档 + 重跑验证
**Outcome**: 53/53 tests pass, p05 重跑验证通过, dashboard 重建成功

---

## 概述

经过 3 个探索代理（主流水线 loop engineering + Harness 工程 + 文档/Archetype C 审查）对 p05 项目的全面只读审查，发现 60+ 个问题。按严重度分层执行修复，覆盖共享代码、Harness、文档、数据。

---

## 发现的严重根因（Top 10）

| # | 根因 | 位置 | 影响 |
|---|------|------|------|
| 1 | 覆盖矩阵在主流程从未被填充（`add_card` 零调用） | `loop_engine.py` | coverage_summary 全空 → 外循环三判据全失效 → 恒 max_rounds |
| 2 | `gap_yield` 正确公式赋给 `_` 丢弃 | `loop_engine.py:683` | GAP_YIELD 永不满足 |
| 3 | `base_skill.run()` 不拷 `_metrics` → `output.metrics` | `base_skill.py:77-96` | 全部 skill 指标恒 0（S5 new_citations 等） |
| 4 | decompose 候选 schema 键名与消费者全面不匹配（`scores.combined` vs `combined_score`；`disease` vs `disease_phenotype`） | `loop_engine.py:396,412-416` | 排序/过滤失效、查询退化 |
| 5 | CardStore 无去重 + S7 uuid4 card_id + 跨轮重抽 | 多处 | 36% 重复卡（164/458） |
| 6 | candidate 模式内循环实为单次扫描（无迭代无反思） | `loop_engine.py:475-631` | 12-21 query 即"收敛" |
| 7 | synthesis 输入丢失 research_direction/archetype | `loop_engine.py:335-341` | S12 prompt 空方向 |
| 8 | S5 quality_gate 无 S2S API key → 429 → 全有或全无 → always failed | `skill_05` | 阻塞 pipeline |
| 9 | literature_check 用中文散文句当英文论文标题做子串匹配 | `validators/literature_check.py` | 永不可能匹配 |
| 10 | citation_verifier 只认 DOI/PMID，GSE/author-year 不验证 | `validators/citation_verifier.py` | 捏造 GSE123456 漏网 |

---

## Phase 1: 主流水线修复（共享代码，13 文件）

### base_skill.py
- `run()` 末尾把 `self._metrics` 合并进 `output.metrics` — 恢复全 skill 可观测性

### loop_engine.py
- `_load_candidates`: 兼容 `scores.combined` + `combined_score` fallback
- `_build_candidate_queries` / `_rewrite_candidate_queries`: 读 `dimensions.{disease,tissue,method,population}` + 旧键 fallback
- S7 后对新卡片调 `coverage_matrix.add_card()`（candidate 与标准模式）
- `gap_yield`: 启用 L683 正确公式；空矩阵 jaccard 返回 0.0
- S5 后向 L2 写 `reading_list` 键
- 跨轮候选去重：已产卡 topic 跳过重处理，0卡候选允许改写 query 重试一次
- `_inject_synthesis_context`: 显式注入 research_direction/archetype
- checkpoint 瘦身：只存必要键
- `queries_run` 更名为实际语义计数

### coverage_matrix.py
- `add_card` 计数 `>1` → `>=1`
- 空矩阵 jaccard 返回 0.0（替代虚假 1.0）

### card_store.py
- `add()` 去重：DOI/PMID 优先，否则 (normalized_title, key_finding_hash)
- 新增 `dedup_existing()` 离线清理方法

### skill_05_citation_snowball.py
- execute 写 `_metrics["new_citations"]`
- quality_gate 区分基础设施失败（429/无key→降级通过+warning）

### skill_07 (shared + archetype C)
- shared: reliability_flag DOI/PMID 存在的卡升 "medium"
- archetype C: prompt 删 "Use 0 for not reported" / "unknown or closest match"；reliability_flag 升级

### skill_11_gap_analysis.py
- C1-C11 / P3 / P9 / P10 全部传 `supporting_cards`

### archetype_c_sc_ai/gap_patterns.py
- 补回 C10 注册（C1-C11 共 11 个 pattern），docstring 更新

### skill_12_hypothesis_generate.py
- prompt 加 `raw_data_accession` 锚定提示
- `required_datasets` 池外剔除
- `addresses_gap` 多 ID 拆分校验

### scripts/rerun_p05_p06_p07.py
- patch final_report 时同步 `total_cards` / `coverage_summary`
- summary.json 保留真实 duration / budget

### scripts/decompose_directions.py
- 疾病↔组织兼容规则表 + LLM 连贯性复核
- 输出补扁平 `combined_score` 兼容键
- T030+ 不再固定 0.3，标记 `literature_unchecked`

---

## Phase 2: P05 Harness 修复（12 文件）

### validators/literature_check.py — 完全重写
- 正则提取：`Author et al., year` / DOI / GSE accession
- 模糊匹配：作者+年份+关键词重叠 ≥ 阈值
- 分母按卡数；无卡候选 → `status: "unknown"`

### validators/citation_verifier.py
- 新增 author-year / GSE 模式
- verified_title/year 与方案声称值比对
- 中文标点剥离（。》））
- GSE accession 标记为存在但不可验证

### loop_runner.py
- best_plan / best_score 跨轮跟踪，交付最优版
- passed 判定先于 stagnation
- RobustCritique 取中位后重算 passed
- mcp_calls 改用 search_engine.search_calls 真实计数
- checkpoint 原子写（tmp+rename）+ config 快照 + skip_mcp 模式 + 恢复校验
- refine 后重跑 completeness_check + citation 预验证
- llm_calls 补计 MCP context enrichment + RobustCritique
- try/finally 关闭 search_engine

### rubric.py
- `RobustCritique.aggregate` 接受 pass_threshold 并重算 passed
- 缺失维度 → log warning + 默认 2.0
- LLM 解析失败 → 返回 -1.0（不产生幻影 3.0）

### phases/phase1_generate.py
- `_summarize_gaps` 字段名 `gap_score` → `score`

### phases/phase3_refine.py
- 防注入：摘要用 `[LITERATURE_START]...[LITERATURE_END]` 定界符 + prompt 声明忽略内嵌指令

### main.py
- 候选选择感知证据卡（`filter_candidates` 有卡优先排序）
- 普通运行也更新 `latest_run.txt`
- 无效 `--candidates` ID 警告
- 检查 `AISCIENCE_API_KEY` 环境变量（替代仅 litellm 导入）
- summaries `passed=False`（替代虚增 True）

### mcp/search_engine.py
- 只实例化 4 个所需 MCP（替代全部 19 个）
- `search_multi` 加 `return_exceptions=True`
- year 解析 try/except 防护
- 新增 `self.search_calls` 原子计数器

### 清理
- 删除根目录空 `acceptance_report.md` / `p05_final_enriched.json` / `harness_result.json`

---

## Phase 3: 文档修复（8 文件）

| 文件 | 改动 |
|------|------|
| `docs/ARCHITECTURE.md` | 收敛阈值 0.95/0.2 → 0.70/0.30；max_rounds 3→5；gap 注册表 C1-C11；Key Files 表修正 |
| `docs/使用手册.md` | 3×5 → 5×7；C1-C10 → C1-C11；新增 P05 Harness 章节（CLI/工作流/输出说明）；decompose 输出 schema 修正；scripts 目录补全 |
| `docs/SKILL_DEVELOPMENT_GUIDE.md` | 多项规范条款补充 |
| `docs/TROUBLESHOOTING.md` | harness/latest_run/skip_mcp/候选键名条目 |
| `docs/CHANGELOG.md` | r9 条目记录全部修复 |
| `AGENTS.md` | 检查兼容性 |
| `scripts/p05_harness/README.md` | 新建：架构、CLI、runs/、--merge/--recover 工作流 |
| 清理空文件 | `p05_harness_output/` 根目录 |

---

## Phase 4: 重跑验证

### 4.1 备份
- 旧 p05 输出备份至 `data/backup_20260719_1225/`

### 4.2 重新生成候选
- `python scripts/decompose_directions.py --projects p05`
- 连贯性过滤生效：过滤 8 个不连贯组合（RA×肠道杯状细胞、T2D×多巴胺神经元等）
- 产出 32 个候选，schema 兼容

### 4.3 重跑 p05
- `python main.py --only p05_sc_multiomics_ai`
- 验证结果：

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| coverage_summary.total_cells | 0 | **16** |
| gap supporting_cards | 全空 [] | **非空** |
| 卡片重复率 | 36% (164/458) | **0%** |
| gap_yield ratio | 12.000 (fake) | **0.000~1.000** (正确) |
| Jaccard | 恒 1.0 (fake) | **0→0.812→1.000** |
| S5 行为 | 每轮 failed (阻塞) | **降级通过 + warning** |
| summary.json duration | 0.0 (硬编码) | **223.19s** (真实) |
| summary.json budget_used | 0 (硬编码) | **40810** |

### 4.4 重建 Dashboard
- `python dashboard/build_data.py` → 成功

---

## 测试结果

```
53 passed in 0.62s
```

修复期间发现的 3 个回归问题已修复：
1. `main.py:264` syntax error — 嵌套 `c.get` 缺闭合 `)`（已修）
2. `test_jaccard_empty` — 断言从 1.0 → 0.0（适配空矩阵修复）
3. `test_inner_convergence_reasons` — 断言从 5 → 6（适配新增 TOPIC_EXHAUSTED）

---

## 已知次要残余

1. `inner_loop_rounds.round` candidate 模式下仍为 0（`iteration` 字段在 candidate 模式不更新）
2. `reading_list` 未完整连通 → `citation_closed` 收敛判据仍不触发
3. P05 harness 可用新候选/卡片重新运行验证

---

## 修改文件总览

共享流水线 (13): base_skill.py, loop_engine.py, orchestrator.py, coverage_matrix.py, card_store.py, skill_05_citation_snowball.py, skill_07_evidence_card_extract.py (shared + archetype C), skill_11_gap_analysis.py, archetype_c_sc_ai/gap_patterns.py, skill_12_hypothesis_generate.py, rerun_p05_p06_p07.py, decompose_directions.py

Harness (12): main.py, loop_runner.py, phase1_generate.py, phase2_critique.py, phase3_refine.py, rubric.py, literature_check.py, citation_verifier.py, completeness_check.py, search_engine.py, query_generator.py, report.py

文档 (10): ARCHITECTURE.md, 使用手册.md, SKILL_DEVELOPMENT_GUIDE.md, TROUBLESHOOTING.md, CHANGELOG.md, AGENTS.md, p05_harness/README.md, 清理空文件 (3)

测试 (2): test_coverage_matrix.py, test_loop_engine.py
