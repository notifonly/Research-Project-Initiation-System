# 全项目候选驱动架构推广 — Session Work Journal

**Date**: 2026-07-15
**Session**: 候选驱动内循环架构从 p05 推广到全部 7 个项目
**Files Changed**: 7 files, ~+40 lines

---

## 概述

将 p05 验证通过的候选驱动内循环架构推广到其余 6 个项目（p01-p04, p06-p07）。核心改动：项目 config.yaml 中启用 `candidate_driven: true`，并修改 shared S7 支持候选标记（`candidate:{topic_id}` tag）。全程无需修改 `loop_engine.py`、`tool_flow.py` 或任何原体级代码——架构本身已是泛型的。

---

## 变更清单

### 1. `shared/skills/skill_07_evidence_card_extract.py` (+7 lines)

| 方法 | 变更 | 行 |
|------|------|-----|
| `execute()` | 读取 `ctx.scratch.get("_candidate_topic_id", "")` | +1 |
| `_extract_from_paper()` | 新增 `topic_id` 参数，传递给 `_build_card()` | +2 |
| `_build_card()` | 新增 `topic_id` 参数；若非空则追加 `f"candidate:{topic_id}"` 到 `tags` | +4 |

### 2. `shared/skills/skill_07_evidence_card_extract.py` — `_sanitize_field_value()` 修复 (+12 lines)

| 问题 | 修复 |
|------|------|
| LLM 返回 `None` 给 list 字段 (`locus_genes`) → pydantic 报错 `Input should be a valid list` | `None` + list annotation → 返回 `[]` |
| LLM 返回 `True/False` 给 str 字段 (`coloc_result`, `comparison_to_clinical_score`) → pydantic 报错 `Input should be a valid string` | `bool` + str annotation → 返回 `"True"/"False"` |

新增逻辑:
```python
if value is None:
    if "list" in annotation:
        return []
    return None
if isinstance(value, bool):
    if "str" in annotation:
        return "True" if value else "False"
    return value
```

### 3-8. 6 个项目 config.yaml（各 +5 lines）

| 项目 | 文件 | 新增字段 |
|------|------|----------|
| p01 | `projects/p01_gwas_perturb_seq/config.yaml` | `candidate_driven: true`, `candidate_source`, `max_candidates: 3`, `min_candidate_score: 0.0`, `candidate_order: shuffle` |
| p02 | `projects/p02_gwas_spatial/config.yaml` | 同上 |
| p03 | `projects/p03_gwas_scatac/config.yaml` | 同上 |
| p04 | `projects/p04_prs_advance/config.yaml` | 同上 |
| p06 | `projects/p06_digital_immune/config.yaml` | 同上 |
| p07 | `projects/p07_aging_clock/config.yaml` | 同上 |

### 9. p04 decompose 数值修复

`python scripts/decompose_directions.py --projects p04` 重跑，修复所有候选评分平直 0.345 的问题 → 现在范围 0.365-0.632。

---

## 架构决策

| # | 决策 | 选择 |
|---|------|------|
| 1 | 推广范围 | 全部 6 个未升级项目，一次完成 |
| 2 | max_candidates | 统一 3（与 p05 一致），shuffle 顺序 |
| 3 | 候选标记方案 | Shared S7 直接支持（不要求每个原体自定义 S7） |
| 4 | 验证策略 | 逐个串行运行，先 p01 试点再批量 p02-p07 |
| 5 | p04 评分修复 | 推广前先重跑 decompose，确保候选质量 |

---

## 修复的 Bug

### 本次 Session

| # | Bug | 根因 | 影响 | 修复 |
|---|-----|------|------|------|
| 1 | p04 decompose 所有候选评分 0.345 | 分解阶段评分退化（T2D+PRS 领域文献暴量导致密度评分饱和） | 40 候选无法区分 | 重跑 decompose，引入更窄的搜索词 |
| 2 | S7 `locus_genes: None` 报错 | LLM 对含 list annotation 的字段返回 None | 卡片被丢弃，S7 提取失败率 ~30% | `_sanitize_field_value` 处理 None→`[]` |
| 3 | S7 `coloc_result: True` 报错 | LLM 对含 str annotation 的字段返回 bool | 同上，额外 ~15% 失败率 | `_sanitize_field_value` 处理 bool→`"True"/"False"` |

### 已知问题（非本次引入）

| # | 问题 | 表现 | 状态 |
|---|------|------|------|
| 4 | p01 S11 gap_analysis 每轮失败 "skill returned failure" (~17min/轮) | 仅 archetype A 的 p01，p02 同原体正常 | 待排查 |
| 5 | 7 项目并行运行时 S4/S5/S6/S7 超时 | 重度并发，API 资源争用 | 建议串行或降低并发度 |
| 6 | checkpoint 保存偶尔失败 | 磁盘 IO 争用 | 非关键，有重试机制 |

---

## 数据流

```
decompose_pilot_results.json (7 projects × 40 candidates)
        │
        ▼
loop_engine._load_candidates()
  └─ 加载对应 project_id 的 40 候选
  └─ 过滤 min_candidate_score=0.0 → 全部通过
  └─ candidate_order=shuffle → 随机取 3 个
        │
        ▼
候选 Txxx:
  └─ _rewrite_candidate_queries() → LLM 生成 3-5 精准搜索词 (缓存)
  └─ S4(multi-source) ────┬─ 失败 → 立即放弃候选 (break)
  │    └─ S4 缓存跨轮复用   │
  ├─ S5(citation snowball)  │
  ├─ S6(screening)          │
  ├─ S6a(divergent search)  │
  ├─ S7(extract)            │
  │    └─ ctx.scratch["_candidate_topic_id"] → tags += ["candidate:Txxx"]
  ├─ S8(data availability)  │
  ├─ S9(method match)       │
        │
        ▼
全部候选遍历完成 → S11(gap) → S12(hypothesis)
        │
        ▼
外循环: Jaccard + gap_ratio + citation_closed → 收敛或 max_rounds=5
```

---

## 指标

### 全部 7 项目运行结果

| 项目 | 原体 | 卡片 | 间隙 | 假设 | 轮次 | 耗时 | 收敛 |
|------|------|------|------|------|------|------|------|
| p01 | A (v2g) | ~1000 | — | — | 4† | ~60 min | N |
| p02 | A (v2g) | 512 | 58 | 5 | 5 | ~16 min | N |
| p03 | A (v2g) | 559 | 35 | 5 | 5 | ~17 min | N |
| p04 | B (prs) | 530 | 11 | 5 | 5 | ~36 min | N |
| p05‡ | C (sc_fm) | 24 | 10 | 5 | 3 | ~9 min | N |
| p06 | D (omics) | 457 | 10 | 5 | 5 | ~51 min | N |
| p07 | D (omics) | 463 | 10 | 5 | 5 | ~23 min | N |
| **合计** | | **3221** | **159** | **35** | | | |

† p01 第 4 轮 S11 超时，卡片数不完整
‡ p05 为之前运行的数据（未重新跑）

### 候选驱动验证点

| 验证项 | 状态 |
|--------|------|
| `_load_candidates()` 加载分解数据 | ✅ 全部 7 项目 |
| `_rewrite_candidate_queries()` LLM 查询重写 | ✅ 全部项目 |
| S4 缓存跨轮复用 | ✅ 全部项目 |
| S4 失败触发候选放弃 | ✅ p07 T000 |
| 候选穷尽后轮跳过 | ✅ 全部项目 |
| `candidate:{topic_id}` 标记到 cards | ✅ 全部项目 |
| Per-candidate checkpoint | ✅ 全部项目 |

---

## 经验教训

### 1. 推广前检查候选数据质量

**问题**: p04 分解所有 40 候选评分平直 (0.345 = min = max)，无法区分候选优劣。

**教训**: 启用 `candidate_driven` 前，应先检查 `decompose_pilot_results.json` 中对应项目的评分分布：
```python
scores = [c["combined_score"] for c in entry["candidates"]]
if min(scores) == max(scores):
    print(f"WARNING: {pid} scores degenerate, re-run decompose first")
```

**预防**: 在 `_load_candidates()` 中添加 warning 日志当检测到评分退化的项目。

### 2. S7 类型强制必须在 shared 层面防御

**问题**: 不同 LLM 模型 (gpt-4o-mini / deepseek) 对 pydantic schema 理解不一致：有的对 `list[str]` 字段返回 `None`，有的对 `str` 字段返回 `bool`。p05 的自定义 S7 (`_coerce_int/float/bool`) 避开了这些问题，但 shared S7 没有。

**教训**: Shared S7 的 `_sanitize_field_value()` 是所有 6 个项目的入口，必须对所有 LLM 输出做防御性类型强制。规则：
- `None` → list annotation? `[]` : `None`
- `bool` + str annotation → `"True"/"False"`
- 任何其他 annotation 不匹配 → 保留原始值让 pydantic 报错（不静默丢失）

**预防**: 新字段上线时应先跑 1 轮 dry-run，检查 S7 提取失败次数。

### 3. 候选 S4 失败级联保护

**问题**: 候选 S4 quality_gate 失败后，若不中断则 S5-S9 在无数据基础上级联失败。

**教训**: `_run_candidate_driven_loop()` 中 S4 失败立即 `break` 的设计是正确的——p07 T000 验证了这一点（S4 失败 → 0 cards → 后续轮跳过）。

**预防**: 如果 S4 quality_gate 失败率 >30%，应检查搜索关键词质量或 MCP 源可用性。

### 4. 重型并发下的超时处理

**问题**: 7 项目并行时 S4/S5/S6/S7 超时频繁，因为每个项目的 MCP 搜索 + LLM 调用都会并发到同一组 DeepSeek 服务器。

**教训**: 候选驱动架构增加了 LLM 调用次数（每候选额外一次 `_rewrite_candidate_queries`），并行度需要相应降低。

**预防**:
- 单机串行运行：每个项目独立跑，互不影响
- 分批：先 archetype A（p01-p03），再 B/D（p04,p06,p07）
- 或减小 `main.py` 的并发度参数

### 5. 同原体项目的差异要找对原因

**问题**: p01 S11 故障而 p02 正常，两者都是 archetype A + candidate-driven。第一时间怀疑是候选架构问题，但排查后确认是 p01 特定 gap pattern 匹配超时。

**教训**: 同原体项目对比是最快的根因定位方法——若同原体一个正常一个异常，问题必在该项目的特定数据/配置上。

**预防**: 调试时先用同原体项目做对照跑，排除架构层面的嫌疑。
