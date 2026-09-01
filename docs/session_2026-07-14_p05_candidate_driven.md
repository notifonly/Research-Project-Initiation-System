# p05 Candidate-Driven Architecture — Session Work Journal

**Date**: 2026-07-14
**Session**: p05 候选驱动的内循环架构重构
**Files Changed**: 4 files, ~+195/-20 lines

---

## 概述

将 p05_sc_multiomics_ai 项目从基于 flat key_terms 的传统内循环，重构为以方向分解候选 (direction decomposition candidates) 作为内循环迭代单位的架构。实现了 LLM 查询重写、洗牌遍历、和多个 bug 修复。

---

## 变更清单

### 1. `projects/p05_sc_multiomics_ai/config.yaml`

| 变更 | 说明 |
|------|------|
| 移入 `convergence` 节 | `candidate_driven`, `candidate_source`, `max_candidates`, `min_candidate_score`, `candidate_order: shuffle` |
| 移除 | `topic_exhausted` 从 `inner_loop_or` (它是内部返回原因，不是收敛条件) |

### 2. `shared/skills/skill_01_direction_decompose.py` (-20 lines)

- 移除 `_load_decompose_dimensions()` 及相关富集逻辑 (87-107行)
- 分解数据现在通过 LoopEngine 直接加载，不再通过 S1 key_terms 平铺

### 3. `shared/core/loop_engine.py` (+185 lines)

**新增枚举值**:
- `InnerConvergenceReason.TOPIC_EXHAUSTED`

**新增状态字段**:
- `_candidate_driven: bool`
- `_candidates: list[dict]`
- `_candidate_idx: int`
- `_current_candidate: Optional[dict]`
- `_candidate_progress: dict[str, dict]`

**新增方法**:
- `_load_candidates()` — 读取 decompose_pilot_results.json，支持 shuffle/score_desc 排序
- `_build_candidate_queries(candidate)` — 维度拼接: `{method} {disease} {tissue} {data}`
- `_rewrite_candidate_queries(candidate)` — LLM 查询重写 (Phase 2)，调用 llm_complete() 从 research_question 生成 3-5 精准搜索词。失败时 fallback 到 `_build_candidate_queries()`
- `_run_candidate_driven_loop()` — 候选级 S4→S9 遍历，含 LLM 查询缓存、进度追踪、per-candidate checkpoint
- `_checkpoint_candidate()` — 保存每个候选的处理进度

**修改的方法**:
- `_run_inner_loop()` — 根据 `_candidate_driven` 分发到标准/候选循环
- `_prepare_skill_input()` S4 块 — 从 `_candidate_progress` 缓存读取 LLM 查询词，回退到维度拼接

**逻辑保护**:
- S4 失败 → 立即放弃候选 (break)，避免 S5-S9 无源级联
- 已穷尽候选 → 后续 round 跳过
- `_candidate_progress` 更新时保留 `llm_queries` 缓存

### 4. `archetypes/archetype_c_sc_ai/skills/skill_07_scfm_card_extract.py` (+5 lines)

- `execute()` 读取 `ctx.scratch['_candidate_topic_id']`
- `_build_card()` 追加 `f"candidate:{topic_id}"` 到 `tags` 字段

### 5. `scripts/decompose_directions.py`

- 搜索词优先级: `{disease} {tissue}` → `{method} {disease}` (第230-233行)
- 重新运行 p05 分解，产出差异化分数

---

## 架构决策

| # | 决策 | 选择 |
|---|------|------|
| 1 | 候选队列管理 | LoopEngine 内置 (Option A) |
| 2 | S4 查询构造 | 维度拼接 + LLM 重写组合 |
| 3 | 卡片标注 | BaseEvidenceCard.tags (key: `candidate:{topic_id}`) |
| 4 | 遍历粒度 | 每个候选一次 S4→S9，无子迭代 |
| 5 | 实施范围 | p05 试点，验证后推广 |

## 修复的 Bug

1. **配置位置错误**: `candidate_driven` 在 config.yaml 顶层而非 `convergence` 节
2. **S4 失败级联**: S4 quality_gate 失败后仍运行 S5-S9
3. **候选重复执行**: 已穷尽的候选在外层循环中重新遍历
4. **缓存被覆盖**: `_candidate_progress` 字典覆写破坏了 LLM 查询缓存

## 数据流

```
S1(LLM) → S2(术语) → S3(FM扫描) → LoopEngine 加载 40 候选

候选 Txxx: 
  → LLM 重写查询词 (仅一次, 缓存)
  → S4("scVI Alzheimer microglia CTD" + 3个LLM查询词)
  → S5(引用滚雪球) → S6(筛选) → S6a(SCFM搜索)
  → S7(提取 → 卡片打标 candidate:p05_Txxx)
  → S8(数据可用性) → S9(方法数据匹配)

所有候选遍历完成 → S11(gap分析) → S12(假设生成)
```

## 指标

- 40 候选可用，配置 max_candidates=3，shuffle 顺序
- LLM 查询重写: ~210 tokens/候选，跨 outer loop 轮次缓存
- 已发现可产出论文的候选 (T031 产出 12-13 cards)
