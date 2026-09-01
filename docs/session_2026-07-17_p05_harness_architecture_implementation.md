# P05 Harness 架构改进实施 — Session Work Journal

**Date**: 2026-07-17
**Session**: 4项架构改进实施（增量checkpoint + 可插拔量规 + 命名run + 中位数评分） + agent_v3 验证
**Previous**: session_2026-07-17_p05_harness_architecture_diagnosis.md (设计了这4项改进)
**Files Changed**: 6 files (+~250 lines)

---

## 概述

实施上一 session 诊断出的 4 项架构改进，并用 3 个 agent 候选跑 `agent_v3` 验证 cross_domain 量规效果。2/3 agent 候选通过验收（v2 仅 1/3 通过），rl_002 从 3.50 跃升至 4.10。

关键发现：cross_domain 量规解除了创新方向的文献惩罚，但概念层面的结构缺陷（如 router_001 的 scFM orchestration 缺乏 prior work）仍无法靠量规调参解决。

---

## 变更清单

### P0-1: 增量 Checkpoint（loop_runner.py, +45 lines）

**核心改动**:
- `__init__`: 新增 `run_name` 参数，创建 `runs/{run_name}/` 子目录和 `checkpoint.json`
- `run()`: 启动时调用 `_load_completed_ids()` 跳过已完成的候选；每处理完一个候选立即调用 `_append_checkpoint(result)`
- 新增 `_load_completed_ids()`, `_append_checkpoint()`, `_candidate_to_dict()` 三个辅助方法

**收益**: 崩溃/超时后可从断点恢复，不再丢失已完成的候选数据。本次 agent_v3 运行在 10min 超时后，4 个已完成的候选（含 T006）全部保存成功。

### P0-2: 可插拔量规（rubric.py 重写 + phase2_critique.py, +110 lines）

**rubric.py 重构**:
- 提取 `DIMENSION_DESCRIPTIONS` 为独立 dict（共享评分标尺描述）
- 新增 `BaseRubric` dataclass: `dimension_weights`, `pass_threshold`, `min_dimension`, `novelty_guidance`
- 新增 `DefaultRubric`: lit=0.25, tech=0.25, innov=0.20, data=0.15, gap=0.15
- 新增 `CrossDomainRubric`: lit=0.12, tech=0.20, innov=0.30, data=0.20, gap=0.18
- 新增 `RUBRIC_REGISTRY` 字典: `{"default": DefaultRubric, "cross_domain": CrossDomainRubric}`
- 新增 `get_rubric(candidate)` 函数: 根据 candidate["rubric"] 选择量规并应用 smooth novelty 修正
- 新增 `_apply_smooth_novelty_weights()`: 平滑公式 `new_lit = max(0.10, current_lit - (0.10 - comp))` — 举例：comp=0.05 时 default rubric lit 从 0.25→0.20（而非旧版的 0.10），cross_domain lit 从 0.12→0.10
- `from_llm_response()` 新增 `rubric` 参数
- `build_critique_prompt()` 改为接收 `candidate` dict 而非裸 competitiveness 值
- **Bug fix**: `__post_init__` 中 `dict(cls.dimension_weights)` 复制类级 dict，避免实例间共享可变状态

**phase2_critique.py 适配**:
- 导入 `get_rubric` 替代 `_get_competitiveness`
- `critique_plan()` 内创建 rubric 实例并传递给 `from_llm_response` 和 `build_critique_prompt`

**向后兼容**: `RUBRIC_DIMENSIONS = DefaultRubric().dimensions` 保留旧接口；`_get_competitiveness()` 保留留作 shim。

### P1: 命名 Run + 历史归档（main.py + loop_runner.py + build_data.py, +120 lines）

**main.py CLI 新增**:
- `--run-name NAME`: 指定 run 名称（默认 `run_{timestamp}`）
- `--merge run1,run2`: 聚合多个 run 到 `harness_result.json`，写 `latest_run.txt`
- `--list-runs`: 列出 `runs/` 下所有已保存 run 及通过数
- `--recover NAME`: 从指定 run 断点恢复
- 新增 `list_saved_runs()`, `merge_runs()` 函数

**loop_runner.py**:
- `_save_results()` 改为写入 `runs/{run_name}/harness_result.json` 和 `runs/{run_name}/p05_final_enriched.json`
- 新增 `_harness_to_dict()` 辅助

**build_data.py**:
- `_build_p05_harness()`: 优先读 `latest_run.txt` 聚合多 run，fallback 读单文件
- 新增 `_aggregate_harness_runs()`: 按 candidate_id 去重合并多个 run
- 新增 `_parse_harness_candidates()`: 提取公共候选解析逻辑
- 新增 `score_stability` 字段输出

### P2: 边缘候选中位数评分（rubric.py + loop_runner.py, +55 lines）

**rubric.py 新增 `RobustCritique`**:
- `is_edge_candidate(score)`: 判断 score ∈ [3.7, 4.1]
- `aggregate(results)`: 对 n 个 CritiqueResult 取 median weighted_score 和 per-dimension median scores，计算 stdev 作为 score_stability

**loop_runner.py**:
- 在 `_process_candidate` 的 iteration 0 后检查：若 `RobustCritique.is_edge_candidate(critique.weighted_score)`，额外跑 `N_REPEATS - 1` 次 critique，取 aggregated 结果

**实际效果**: 本次 agent_v3 运行中无候选触发（router_001 iter0=3.6, rl_002 iter0=3.42, benchmark_003 iter0=3.6，均不在 3.7-4.1 区间）。说明触发条件设计需调整——应改为在所有迭代完成后对最终分触发，而非仅首轮。

---

## Runtime 验证: agent_v3

**命令**: `python scripts/p05_harness/main.py --candidates-file data/p05_agent_candidates.json --run-name agent_v3`

| 候选 | v2 分 | v3 分 | Δ | 状态 | 量规 | 分析 |
|------|-------|-------|-----|------|------|------|
| agent_router_001 | 3.65 | **3.70** | +0.05 | ❌ | cross_domain | 小改善。llm_coverage 权重削到 0.10 解除了部分惩罚，但方向的核心 gap（scFM orchestration 缺乏 prior work）不是量规能解决的。gap_alignment 仍卡在 3.0 |
| agent_rl_002 | 3.50 | **4.10** | **+0.60** | ✅ | cross_domain | 最大受益者。Bandit 方向的文献缺失（无单细胞领域先例）在旧版量规下被大量扣分 → cross_domain 量规让 reviewer 接受"方向新所以文献少"的逻辑。iter 1 即跃升至 4.1 通过 |
| agent_benchmark_003 | 4.65 | 4.00 | -0.65 | ✅ | cross_domain | 得分显著下降但仍通过。原因：cross_domain 量规改变了 reviewer 评分框架——创新权重翻倍但 reviewer 对"自演化 benchmark"这种高度抽象的概念缺乏评分基准，给分偏保守。旧版 4.65 本身也存在 LLM 随机性虚高成分 |

**通过率**: 2/3 (v2: 1/3)
**总耗时**: ~565s (9.4 min) for 4 candidates (3 agents + 1 decompose before timeout)
**LLM calls**: 20, MCP calls: 126

---

## 新暴露问题 + 经验教训

### 1. Cross-domain 量规对创新方向效果显著，但需区分"真的跨学科"和"文献不全的传统方向"

**证据**: rl_002 从 3.50→4.10 (+0.60)，literature_coverage 维度从主要惩罚源变为边缘维度。reviewer 在 guidance prompt 引导下接受了"方向新所以文献少"的前提。

**风险**: 当前 `rubric: "cross_domain"` 是手动标注。如果 decompose 候选中有传统方向文献覆盖确实差（写方案的人没认真查文献），误标为 cross_domain 会导致 lit_coverage 维度形同虚设。需要后续引入自检机制（如：检查 candidate 的 method 关键词列表中是否有 ≥1 个 scFM benchmark 或 standard evaluation 术语出现 → 则判定为传统方向）。

### 2. benchmark_003 得分回归揭示 reviewer 对抽象概念的评分困难

**问题**: 旧版 4.65→4.00 的大幅下降，核心不是方案变差了，而是 cross_domain 量规的 prompt guidance 引导 reviewer "区分可修复和不可修复缺口"——对"自演化智能体"这种需要发明新概念的方案，reviewer 给了 tech_feas=3.0 而非旧版的 4.0。旧版的高分（4.65）本身可能含有 LLM 随机性虚高成分。

**经验**: 对于"需要发明新方法"的方向（如 benchmark_003 的自演化 benchmark agent），即使用 cross_domain 量规，在不可修复缺口上的 tech_feas 评分仍会保守。这是因为 LLM reviewer 对"开放研究问题"的评估能力有限。考虑在 prompt 中明确告诉 reviewer：该方向的目标是 提出框架性贡献而非实际跑出跑实验。

### 3. router_001 +0.05 再次证明：结构性 gap 不是量规能弥补的

**问题**: router_001 与前 session 结论一致——agent_rl_002 方向（contextual bandit + scFM）的核心问题是 gap_alignment 维度，即"scFM + bandit 之间的 gap 太大"的 reviewer 判断。这不是文献覆盖问题，无法靠权重调整解决。

**经验**（与前 session 一致）: 预注入论文 / 调整量规 / 修改 prompt framing 只能解决 literature_coverage 维度。如果一个方向在 gap_alignment 和 tech_feas 上卡住，内容层要先做方向层面的大改（如换一个已有 prior work 的应用场景），不要指望靠量规调参解决。

### 4. RobustCritique 触发条件设计缺陷

**设计**: 在 `iteration == 0` 的首次 critique 后检查 score 是否在 [3.7, 4.1]。

**问题**: 三种候选首次 critique score 均不在边缘区间（3.6, 3.42, 3.6），RobustCritique 完全未被触发。但 rl_002 在 iter 1 达到了 4.1（刚好在边缘），benchmark_003 的最终分 4.0 也在边缘。边缘区间检测应放在最终分而非首轮分。

**改进方向**: 在所有迭代完成后，若最终 score 在边缘区间，对该最终 iteration 跑 RobustCritique (n=3) 取中位数。注意这会增加（最多）3 × 边缘候选数的 LLM 调用。

### 5. Dataclass 继承 + 类级可变 dict 的经典坑

**问题**: `DefaultRubric.dimension_weights = {"literature_coverage": 0.25, ...}` 是类级变量，所有实例共享同一个 dict 引用。第一轮 `_apply_smooth_novelty_weights()` 修改 `rubric.dimension_weights["literature_coverage"] = 0.18` 后，后续创建的实例也拿到了被污染的 dict。

**修复**: `BaseRubric.__post_init__` 中 `self.dimension_weights = dict(cls.dimension_weights)` 复制，确保每个实例独立。

**教训**: Python dataclass 子类中，不带 `field()` 声明的类变量会 shadow 父类的 field 定义。但如果是可变类型（dict/list），所有实例共享引用。**任何 dataclass 中使用 dict/list 作为默认值的地方，都应在 `__post_init__` 中复制或使用 `field(default_factory=dict)` — 但后者与类级覆盖不兼容。**

### 6. 10min 超时不足 + 增量 checkpoint 验证

**问题**: 10 候选全量跑需要 ~20min（3 agents + 7 decompose），agent_v3 在 T004 开始时超时。

**验证**: 增量 checkpoint 完全生效 — 超时前已完成 4 个候选（3 agents + T006），全部成功保存到 `runs/agent_v3/checkpoint.json`。后续可通过 `--recover agent_v3` 断点恢复。

**建议**: 全量 `main.py` 运行设置超时 ≥ 30min。

---

## 实验数据存档

### agent_v3 迭代轨迹

**agent_router_001** (cross_domain, comp=0.05):
```
iter=0: [3,3,4,4,3] weighted=3.6 gaps=6
iter=1: [3,3,4,4,4] weighted=3.7 gaps=5  
iter=2: [3,4,4,4,3] weighted=3.7 gaps=5
→ final: 3.70, 停滞终止
```

**agent_rl_002** (cross_domain, comp=0.08):
```
iter=0: [2,3,4,4,3] weighted=3.42 gaps=9
iter=1: [3,4,5,4,4] weighted=4.1  passed
→ final: 4.10
```

**agent_benchmark_003** (cross_domain, comp=0.05):
```
iter=0: [3,4,4,4,3] weighted=3.6 gaps=8
iter=1: [4,4,4,4,4] weighted=4.0 passed (min_dim=4.0 >= 3.0)
→ final: 4.0
```

**T006** (default rubric):
```
iter=0: [3,4,4,4,3] weighted=3.52 gaps=5
iter=1: [3,4,4,4,3] weighted=3.52 gaps=4
iter=2: [3,4,4,4,3] weighted=3.52 gaps=4
→ final: 3.52, 停滞终止
```

---

## 待改进项

- [ ] RobustCritique 触发时机改为所有迭代完成后的最终分
- [ ] router_001 方向如需通过需做方向层面重构（换个有 prior work 的应用场景）
- [ ] 保留一个含假引用的 decompose 候选定期验证引用前置是否仍有效
- [ ] 全量 harness run 设置 30min 超时
- [ ] 考虑引入自检机制区分"真的跨学科"和"文献不全的传统方向"

---

## 文件清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/p05_harness/validators/rubric.py` | 重写 | BaseRubric + DefaultRubric + CrossDomainRubric + RobustCritique + smooth novelty |
| `scripts/p05_harness/phases/phase2_critique.py` | ~5 lines | 适配新量规系统 |
| `scripts/p05_harness/loop_runner.py` | +100 lines | 增量checkpoint + edge robust critique + runs目录结构 |
| `scripts/p05_harness/main.py` | +80 lines | CLI参数 (--run-name/--merge/--list-runs/--recover) + merge逻辑 |
| `dashboard/build_data.py` | +95 lines | 多run聚合 + _parse_harness_candidates 重构 |
| `data/p05_agent_candidates.json` | 3 fields | 每个agent candidate添加 `"rubric": "cross_domain"` |
| `data/p05_harness_output/runs/agent_v3/` | 新目录 | agent_v3 运行产物（checkpoint.json, harness_result.json, acceptance_report.md, p05_final_enriched.json） |
| `data/p05_harness_output/harness_result.json` | 更新 | agent_v3 聚合结果 |
| `data/p05_harness_output/latest_run.txt` | 更新 | 当前聚合指向 "agent_v3, decompose_v2" |
| `data/p05_harness_output/runs/decompose_v2/` | 新目录 | decompose_v2 运行产物 |
| `docs/session_2026-07-17_p05_harness_architecture_implementation.md` | — | 本文件 |

---

## 第二阶段: 全量 Decompose 候选恢复（方案A）

### 背景

`--merge agent_v3` 后 `harness_result.json` 仅含 3 agent + T006 = 4 候选。decompose 候选（T000-T039）的历史数据在架构诊断 session 中已被覆写丢失。需重跑 harness 用新版系统重新生成。

### 执行过程

| 阶段 | 命令 | 候选 | 结果 | 耗时 | 问题 |
|------|------|------|------|------|------|
| 1 | `--max-candidates 10 --run-name decompose_v1` | 10 | T006+T004 完成，T000 开始时超时 | 20 min | MCP 文献搜索每轮 3-5min，总耗时 >60min |
| 2 | `--max-candidates 10 --skip-mcp --run-name decompose_v2` | 10 | 8/10 完成后超时 | 20 min | `--skip-mcp` 未生效，LoopRunner 自动重新创建了 SearchEngine |
| 3 | 修复 skip_mcp bug + `--recover decompose_v2 --skip-mcp` | 2 (补缺) | T008+T009 完成，10/10 | 4 min | 跳过 8 个已完成，仅处理缺失的 2 个 |

### 恢复机制验证

- **阶段 1 超时**: T006 和 T004 已完成并保存到 `runs/decompose_v1/checkpoint.json`，无数据丢失
- **阶段 2 恢复**: 由于阶段 1 不完整，改用 `decompose_v2` 从头开始。因 `--skip-mcp` bug 未生效，每个候选仍耗时 ~140s（含 MCP），8/10 后超时
- **阶段 3 恢复**: checkpoint 跳过 8 个已完成（T006-T007），仅处理 T008+T009（每候选 ~120s LLM only）。增量 resum 设计完全生效

### Decompose 候选评分

| 候选 ID | 得分 | 状态 | 备注 |
|---------|------|------|------|
| T004 | 4.15 | ✅ passed | iter 0=2.9 → iter 2=4.15 |
| T003 | 4.00 | ✅ passed | iter 0=2.75 → iter 2=4.0 |
| T008 | 4.00 | ✅ passed | iter 0=2.75 → iter 2=4.0 |
| T006 | 3.52 | ❌ failed | 停滞终止（连续三轮不变） |
| T000 | 3.50 | ❌ failed | iter 0=2.75, iter 1=3.75, iter 2=3.5（先升后降） |
| T002 | 3.40 | ❌ failed | 停滞终止 |
| T009 | 3.40 | ❌ failed | iter 0=2.75, iter 1=3.75, iter 2=3.4（先升后降） |
| T001 | 3.00 | ❌ failed | iter 0=2.75, iter 1=3.6, iter 2=3.0（先升后降） |
| T005 | 3.00 | ❌ failed | 停滞终止 |
| T007 | 3.00 | ❌ failed | iter 0=2.75, iter 1=3.75, iter 2=3.0（先升后降） |

**关键模式**: T000/T001/T007/T009 四候选呈"先升后降"轨迹（iter 0 → iter 1 改善 → iter 2 回落），说明 LLM 在第三轮 critique 出现了评分振荡。这是 stagnation_limit=2 发挥作用前的经典表现。

### 最终合并结果

```bash
python scripts/p05_harness/main.py --merge agent_v3,decompose_v2
# → 13 candidates: 5 passed, 8 failed
python dashboard/build_data.py
# → P05 Harness: 5 passed, 8 failed, 13 candidates
```

Dashboard 完整候选列表（按得分降序）:

| 候选 ID | 得分 | 量规 | 状态 |
|---------|------|------|------|
| T004 | 4.15 | default | ✅ |
| agent_rl_002 | 4.10 | cross_domain | ✅ |
| T003 | 4.00 | default | ✅ |
| T008 | 4.00 | default | ✅ |
| agent_benchmark_003 | 4.00 | cross_domain | ✅ |
| agent_router_001 | 3.70 | cross_domain | ❌ |
| T006 | 3.52 | default | ❌ |
| T000 | 3.50 | default | ❌ |
| T002 | 3.40 | default | ❌ |
| T009 | 3.40 | default | ❌ |
| T001 | 3.00 | default | ❌ |
| T005 | 3.00 | default | ❌ |
| T007 | 3.00 | default | ❌ |

---

## 第二阶段暴露的新问题

### 7. `--skip-mcp` 未穿透到 LoopRunner（🔴 严重）

**表现**: `--skip-mcp` 参数传给 `main.py → LoopRunner(..., search_engine=None)`，但 `LoopRunner.run()` 内有防御性代码：

```python
if self.search_engine is None:
    self.search_engine = SearchEngine(...)
```

**根因**: 这是为"不传 search_engine 时自动创建"设计的防御逻辑，未考虑用户明确要求 skip MCP 的场景。`None` 本身无法区分"未传"和"跳过"。

**修复**: 新增 `skip_mcp: bool = False` 参数到 `LoopRunner.__init__`，修改条件为 `if self.search_engine is None and not self.skip_mcp:`。

**经验**: 参数传递链中，`None` 不适合同时承担"默认值"和"禁止值"两种语义。应用显式 flag。另外，"自动创建依赖"的防御性代码需要在调用链上游就能覆盖到。

### 8. `_aggregate_harness_runs` 优先读错文件（🔴 严重）

**表现**: 合并后 dashboard 显示 6 候选而非 13。`checkpoint.json` 有完整 10 候选，`harness_result.json` 只有 resume 时新处理的 2 个，聚合器选了后者。

**根因**: 设计优先级为 `harness_result.json`（最终聚合 snapshot）优先于 `checkpoint.json`（增量记录）。但 resume 运行时 `_save_results()` 只保存"本次 run 中处理的候选"到 `harness_result.json`，导致该文件内容不完整。

**修复**: 反转优先级为 `checkpoint.json` 优先（始终是完整增量记录）。

**经验**: "snapshot vs incremental log"两种数据源的可靠性不同。snapshot 在 partial run/resume 场景下可能不完整，而 incremental log（append-only）天然保证完整性。聚合逻辑应优先使用增量记录。

### 9. Decompose 候选性能基线（🟡 中等）

**关键数据**:
- 无 MCP: 每个候选 ~120s（Phase1 生成 30s + 3×Phase2 critique 30s + 2×Phase3 refine 30s）
- 含 MCP: 每个候选 ~250s（额外 4×MCP gap search ~130s）
- 10 候选全量: 无 MCP ~22min / 含 MCP ~45min

**通过率**: decompose 3/10 通过（30%），agent 2/3 通过（66%）。agent 方向基于已知研究缺口设计，起点方案质量高于自动 decompose 的均匀采样。

**LLM 评分振荡**: 7 个 decompose 候选中有 4 个（57%）出现"先升后降"轨迹。这与 session improvement 中的观察一致：超过 iter 1 后 LLM reviewer 输出退化、评分随机振荡。`stagnation_limit: 2` 起到了早停作用，但增加了失败候选。

### 10. Resume + checkpoint 多次实战验证（🟢 成功）

**三次超时恢复**: decompose_v1 → decompose_v2 → decompose_v2 resume。每次恢复都正确跳过已完成候选，仅处理剩余项。`_load_completed_ids()` + `_append_checkpoint()` 设计无误。

**建议**: 全量 harness run 设置 30min 超时（而非 20min），以容纳 10 候选 × 3 min = 30min 无 MCP 全量运行。

---

## 第二阶段文件清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/p05_harness/loop_runner.py` | +3 lines | `skip_mcp` 参数 + 条件修复 |
| `scripts/p05_harness/main.py` | +1 line | 传递 `skip_mcp` 到 LoopRunner |
| `dashboard/build_data.py` | 1 line | checkpoint.json 优先于 harness_result.json |
| `data/p05_harness_output/runs/decompose_v1/` | 新目录 | 阶段 1 产物（T006+T004） |
| `data/p05_harness_output/runs/decompose_v2/` | 新目录 | 阶段 2+3 产物（全量 10 候选） |
| `data/p05_harness_output/harness_result.json` | 更新 | agent_v3 + decompose_v2 合并 |
| `data/p05_harness_output/latest_run.txt` | 更新 | agent_v3, decompose_v2 |

---

## 追加待改进项

- [ ] 修复 `_save_results()` resume 时只写新候选而非合并 checkpoint 全量 —— 改为从 checkpoint 读取所有已完成候选再写 harness_result.json
- [ ] 检查所有 "defense auto-create" 模式是否也需要 skip 机制
- [ ] 全量 harness 超时设为 30min
