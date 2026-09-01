# P05 Harness 架构诊断 — Session Work Journal

**Date**: 2026-07-17
**Session**: Harness 迭代暴露的架构缺陷诊断：数据覆写、评分噪音、量规硬编码、无增量保存
**New Issue**: 下次迭代 4 项架构改进（P0: checkpoint + 可插拔量规, P1: 命名run历史, P2: 中位数评分）

---

## 概述

本次会话完成了 7 项 harness 改进和 2 轮验证，但也暴露了 4 个系统架构问题。其中最严重的是：agent run 覆写了 decompose run 的 `harness_result.json`，导致 10 个候选的完整方案数据永久丢失。其他问题包括 LLM 评分随机性导致 pass/fail 非确定性、同一套量规对跨学科方向和传统方向一刀切、以及长时运行崩溃不保存已完成结果。

---

## 暴露的问题

### 1. 单文件覆写模型 — 跨 run 数据丢失（🔴 严重）

**表现**: agent 候选 run 将 `harness_result.json` 从 10 候选 / 5 通过覆写为 3 候选 / 1 通过。被覆写的 decompose 候选数据不可恢复。

**根因**: `loop_runner._save_results()` 始终硬编码覆盖 `harness_result.json`，无版本区分。

**影响**: dashboard 展示的 P05 方案质量从此前的"6 pass / 4 fail"变为"1 pass / 2 fail"，丢失了 10 个方向 × 5 轮迭代的完整评分和方案细节。

### 2. LLM 评分非确定性 — pass/fail 是随机变量（🔴 严重）

**表现**: 
- `agent_router_001` 跨 2 次 run: 3.90 → 3.65（-0.25）
- `T001` 跨 3 次 run: 4.15 → 3.15 → 4.15（振荡 1.00）
- 边缘候选（3.7-4.1）的 pass/fail 由 LLM 随机性决定，不可复现

**根因**: rubric 评分来自单次 LLM response。GPT-4o-mini 在评分任务上存在固有方差。

**影响**: 用户无法信任单次 run 的 pass/fail 结论。回滚已有的"通过"判定不具备可重现性。

### 3. 量规硬编码 — 跨学科方向被错误惩罚（🟡 中等）

**表现**: agent 方向的 `competitiveness < 0.10`（无人做过）本应是优势，但 lit_coverage 权重 0.25 让文献缺失变成最大减分项。

**当前修复**: `_get_competitiveness()` 硬编码检测 + 权重硬切换（0.25→0.10）。问题：切换幅度过大导致 router_001 得分反降；且只能检测 competitiveness 一个信号，无法区分"跨学科新方向"和"传统方向文献不全"。

**根因**: rubric 设计为通用量规，未考虑"不同量规适用于不同类型的研究方向"。

### 4. 无增量保存 — 长时运行崩溃全部丢失（🟡 中等）

**表现**: 第一次 overnight run（10 候选，max_iterations=5）运行 2 小时后超时，shell 强制 kill，已完成的 9/10 候选数据全部丢失，无法部分恢复。

**根因**: `_save_results()` 在全部候选处理完成后才一次性写文件。

---

## 架构改进设计

### 改进 1: 增量 checkpoint

**目标**: 每个候选完成即永久写入，崩溃后自动恢复

```
loop_runner.process_candidate() 返回 → 立即 append 到 run_{timestamp}.json
_save_results() → 依次读取 runs/*.json → 聚合到 harness_result.json
```

**改动**:
- `loop_runner.py`: `_process_candidate` 返回 `CandidateLoopResult` 后立即调用 `_append_to_run_file(result, run_path)`
- `loop_runner.py`: `run()` 入口检查 `run_path` 是否存在 → 存在则恢复已完成的候选列表 → 跳过
- `build_data.py`: 读取 `runs/` 下所有 JSON → 按 `candidate_id` dedup → 聚合

**cost**: ~15 行

### 改进 2: 可插拔量规

**目标**: 根据 candidate 的 `rubric` 字段选择评分方案，不再硬编码竞争度检测

```python
# rubric.py
class BaseRubric:
    dimensions: dict[str, float]  # {name: weight}
    pass_threshold: float
    min_dimension: float

class DefaultRubric(BaseRubric):
    dimensions = {"literature_coverage": 0.25, "technical_feasibility": 0.25,
                  "innovation_clarity": 0.20, "data_accessibility": 0.15,
                  "gap_alignment": 0.15}

class CrossDomainRubric(BaseRubric):
    dimensions = {"literature_coverage": 0.12, "technical_feasibility": 0.20,
                  "innovation_clarity": 0.30, "data_accessibility": 0.20,
                  "gap_alignment": 0.18}
    # 文献权重降低是因为跨学科领域文献本就不存在
    # 数据可及性权重提高是因为跨学科方向更需要具体数据支撑
```

```yaml
# candidate JSON 中
{
    "topic_id": "p05_agent_001",
    "rubric": "cross_domain",  # 新增字段
    ...
}
```

```python
# phase2_critique.py
RUBRIC_REGISTRY = {"default": DefaultRubric, "cross_domain": CrossDomainRubric}
rubric_class = RUBRIC_REGISTRY.get(candidate.get("rubric", "default"))
rubric = rubric_class()
```

**改动**:
- `rubric.py`: 重命名现有为 `DefaultRubric`，新增 `CrossDomainRubric`，新增 `RUBRIC_REGISTRY` 字典
- `phase2_critique.py`: 根据 candidate["rubric"] 选择量规，删除 `_get_competitiveness()` 硬编码
- `build_data.py`: 保存 `rubric` 字段到 dashboard JSON
- 配置文件: 删除 `competitiveness_threshold` 硬编码值

**迁移**: 默认所有候选 `rubric: "default"`，agent 候选显式设为 `"cross_domain"`

### 改进 3: 命名 Run + 历史存档

**目标**: 每次 harness 运行产生独立归档，可 A/B 对比和回滚

```
data/p05_harness_output/
├── runs/
│   └── {run_name}/
│       ├── harness_result.json
│       ├── acceptance_report.md
│       └── p05_final_enriched.json
├── harness_result.json         ← 聚合文件（build_data.py 读取）
└── latest_run.txt              ← 当前聚合指向的 run_name 列表
```

**CLI**:
```bash
# 新 run 自动生成名字
python scripts/p05_harness/main.py --candidates-file agent.json --run-name agent_v2

# 手动聚合多个 run
python scripts/p05_harness/main.py --merge agent_v2,decompose_base

# 查看所有 run
python scripts/p05_harness/main.py --list-runs
```

**改动**:
- `main.py`: 新增 `--run-name` (默认 `auto-{timestamp}`)、`--merge`、`--list-runs` 参数
- `loop_runner.py`: `_save_results` 写入 `runs/{run_name}/`
- `build_data.py`: 新增 `_aggregate_runs()` 函数，读取 `latest_run.txt` → 依次合并 runs

### 改进 4: 边缘候选中位数评分

**目标**: 对 score ∈ [3.7, 4.1] 的候选自动跑 3 次 critique，取中位数作为 final_score

```python
# rubric.py
class RobustCritique:
    def critique_with_confidence(self, plan, rubric, n=3):
        scores = []
        for _ in range(n):
            response = self.llm_client.complete(prompt)
            result = rubric.from_llm_response(response)
            scores.append(result.weighted_score)
        median_score = statistics.median(scores)
        stability = statistics.stdev(scores)  # 标准差
        return median_score, stability
```

Dashboard 追加 `score_stability` 字段:
- stdev < 0.05: "高置信度"
- stdev < 0.15: "中等置信度"  
- stdev >= 0.15: "低置信度，需人工审核"

**改动**:
- `rubric.py`: 新增 `RobustCritique` 类
- `loop_runner.py`: 边缘候选走 RobustCritique 路径（n=3 次 evaluation）
- `build_data.py`: 导出 `score_stability` 到 dashboard
- Dashboard `p05.js`: 显示置信度标签

**成本**: 仅边缘候选（约 30% 的候选）会触发 ×3 的 LLM 调用，整体成本增加 ~30%。

---

## 实施优先级

| 优先级 | 改进 | 收益 | 改动范围 | 预计变更行数 |
|--------|------|------|----------|-------------|
| 🔴 **P0-1** | 增量 checkpoint | 再也不会丢数据 | loop_runner.py | ~15 行 |
| 🔴 **P0-2** | 可插拔量规 | 消灭硬编码竞争度检测 | rubric + phase2_critique + build_data | ~80 行 |
| 🟡 **P1** | 命名 run + 历史 | A/B 对比，回滚 | main + loop_runner + build_data | ~100 行 |
| 🟢 **P2** | 中位数评分 | 消除 LLM 噪音误判 | rubric + loop_runner + dashboard | ~60 行 |

**总计**: ~255 行，跨 7 个文件

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `docs/session_2026-07-17_p05_harness_architecture_diagnosis.md` | 本文件 |
