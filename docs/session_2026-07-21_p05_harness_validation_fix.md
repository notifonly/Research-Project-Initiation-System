# P05 Harness 验收修复验证与工程防护 — Session Work Journal

**Date**: 2026-07-21
**Session**: 用户审查 p05 harness 修复后的验收报告截图，发现 14 个数据质量/管线 bug/仪表盘问题；逐项修复并通过 4 轮端到端验证运行确认；将经验沉淀到文档
**Outcome**: 12 项修复全部通过端到端验证，T005=4.00 通过 / T001=3.15 未通过，引用验证三态生效，仪表盘 6 维全显，无 JS 错误

---

## 概述

用户提供 p05 harness 修复验收截图（T005 scVI 3.80 clear/3H, T001 scGPT 3.15 adjacent/3H, 0 passed），审查原始数据和管线代码后发现实际交付方案存在系统性偏差。核心问题沿三条线索展开：管线代码 bug（6 个）、报告问题（4 个）、仪表盘问题（5 个）和数据质量风险（1 个）。按 P0→P1→P2 优先级修复，经 4 轮端到端验证确认修复生效。

---

## 发现的问题与根因

### P0 管线 Code Bugs

| # | 症状 | 根因 | 位置 |
|---|------|------|------|
| 1 | T001 分数 3.15 来自第 1 轮方案，但交付的方案是第 2 轮（3.0 分）——分数方案不匹配 | `loop_runner.py:412` 注释"deliver best plan"，但 `:434` `result.plan = current_plan` 覆盖了 best_plan | `loop_runner.py` |
| 2 | 引用验证恒为空（`citation_checks=[]`），报告"引用验证"一节完全空白 | 去重逻辑 `key = doi or pmid or title`，"Author et al., 2018" 和 GSE accession 的 key 为空串 → 全部丢弃。方案 schema 无 `references` 字段，文献只以散文形式出现 | `citation_verifier.py:75-81` |
| 3 | 引用验证误杀著名真实论文（Lopez 2018/scVI, Cui 2024/scGPT, Theodoris 2023/Geneformer）→ "hallucinated" | 作者-年份验证使用疾病关键词（"acute myeloid leukemia"）污染查询，而被引用论文本身不讨论该疾病 | `loop_runner.py` context_keywords 构造 |
| 4 | refine 后方案的红队/新颖性判定是初始方案的过期结果（T005 终版已补齐基线，仍报"缺基线"） | Phase 1.5/1.6 只在初始方案上跑一次，refine 循环结束后不复验 | `loop_runner.py` `_process_candidate()` |
| 5 | MCP 调用计数偏高（累计值跨阶段重复加），且单位混杂（搜索次数 + 论文数 + 声明数） | `mcp_calls += self.search_engine.search_calls` 使用引擎级累计值；计数点混用 `len(new_papers)` 和 `len(unverified_claims)` | `loop_runner.py:196/220/245` + `search_engine.py:35/41` |
| 6 | T005 "clear" 是空虚判定：`papers_found=0`、所有 `closest_works` 为空 → "什么都没搜到"被当作"确无近似工作" | `_judge_overlap` no-papers 分支直接返回 clear；没有区分"已搜索无结果"和"未搜索" | `phase15_novelty_verify.py` |

### P1 报告问题

| # | 症状 | 根因 |
|---|------|------|
| 7 | 迭代评分表只有 5 个维度，漏掉第 6 维"评估严谨性"（w=0.15） | report.py 硬编码 5 维度列表，未从 rubric 动态读取 |
| 8 | T001 报告写 3.1，JSON 里是 3.15（显示不一致） | `f"{score:.1f}"` 截断 |
| 9 | 新颖性判定和红队发现完全没有进报告正文 | report.py 未读取 novelty_verdict/redteam_result 字段 |
| 10 | "文献覆盖度：unknown（引用 0 篇，证据卡 0 篇）" | 13 张证据卡只属于 T002/T009/T015/T036；T001/T005 没有标签证据卡 → `literature_check.py` 早期返回 status='unknown' |

### P2 仪表盘问题

| # | 症状 | 根因 |
|---|------|------|
| 11 | 评分概览图被裁切（5 维 stack 累加 ~19 但 yAxis max=5，只看得到 2 个颜色） | `_renderScoreBar`: `stack:'total'` + `yAxis.max: 5`，维度语义独立不应累加 |
| 12 | 第 6 维"评估严谨性"在 P05 页完全缺失（统计卡、图表、弹窗） | `dimKeys` 只定义 5 个维度 |
| 13 | 维度均分与报告不一致（仪表盘 3.3 vs 报告 3.5） | build_data 按所有轮次重算，报告按每候选最终轮计算 |
| 14 | 候选卡片 detail 弹窗缺新颖性/红队/critique 内容；创新点显示 "[object Object]" | `_parse_harness_candidates` 丢弃关键字段；JS 直接渲染对象而非 `.claim` |

---

## 修复内容

### P0#1: best_plan 覆盖 (loop_runner.py)

```python
# 循环中跟踪 best_plan/best_score/best_critique
best_plan = None
best_score = -1.0
best_critique = None
for iteration in range(max_iterations):
    # ... critique loop ...
    if weighted_score > best_score:
        best_score = weighted_score
        best_plan = current_plan
        best_critique = cr

# 循环后交付（不覆盖）
result.plan = best_plan
result.final_score = best_score
result.final_critique = best_critique.to_dict() if best_critique else None
# 引用验证 + 文献覆盖基于 result.plan（best）
```

### P0#2: 引用验证三态重写 (citation_verifier.py)

完全重写引用提取和验证逻辑：

- **去重 key 回退链**: `doi` → `pmid` → `accession` → `author|year` → `title`（永不丢弃）
- **Accession 模式**: GSE/GDS/E-XXX-/ENCSR/ENCFF/SRP/ERP/DRP
- **三态验证**:
  - DOI/PMID 找到 → `verified` ✅（强信号）
  - DOI/PMID 未找到 → `not_found` ❌（强信号——已知 ID 的 API 解析可靠）
  - accession 未找到 → `unverifiable` ❓（文献搜索不索引 GEO/ENCODE，弱信号）
  - 作者-年份 找到匹配 → `verified` ✅（启发式）
  - 作者-年份 未找到匹配 → `not_found` ❌（启发式，可能假阴性）
- **作者-年份验证**: 三查询策略 `[(surname+year+context_keywords,5), (surname+context_keywords,5), (surname+year,10)]`，年份容差 ±1，标题去重
- **关键词校准**: author-year 查询只用方法名（`context_keywords = _kw_method`），不混入疾病名——疾病会污染非疾病文献的搜索命中率
- **容量上限**: `_MAX_VERIFY_PER_TYPE = {doi:15, pmid:10, accession:10, author_year:8}` 防过量调用

### P0#4: refine 后复验 (loop_runner.py)

```python
# Phase 1.5/1.6 第一次运行后保存 initial 版本
novelty_verdict_initial = _novelty_dict(novelty_output, repositioning_attempts, reverified=False)
redteam_result_initial = _redteam_dict(redteam_output, reverified=False)

# refine 循环后复验
if best_plan is not plan:  # 方案被修改过
    novelty_output = await verify_novelty(best_plan, ...)
    redteam_output = await run_redteam(best_plan, ...)
    # 存储 final 版本，标记 reverified_post_refine=True
```

### P0#3: MCP delta 计数 (loop_runner.py + search_engine.py)

- 新增 `lookup_calls` 计数（search_engine.py 的 verify_doi/verify_pmid）
- 闭包 `mcp_ops()` 返回 `search_calls + lookup_calls`
- 所有计数点改为 before/after delta：`mcp_before = mcp_ops(); ...; mcp_delta = mcp_ops() - mcp_before`

### P1#5: insufficient_evidence 判定 (phase15_novelty_verify.py)

- `Verdict` Literal 新增 `'insufficient_evidence'`
- `_judge_overlap` no-papers 分支 → per-claim `insufficient_evidence`
- `_aggregate_overall_verdict`: any-IE 或 all-IE → overall `insufficient_evidence`（保守策略，永不 falsly clear）
- no-queries 早期返回 → `insufficient_evidence`

### P2#9: 证据卡回退 (loop_runner.py + literature_check.py)

候选无标签证据卡时回退到全库 13 张卡，`literature_coverage.evidence_source='fallback_pool'`。报告和仪表盘标注 `[回退全库证据卡]`。

### P1#7/#8/#9: 报告全修 (report.py)

- 迭代评分表动态构建（`RUBRIC_DIMENSIONS` 驱动），6 维全量
- 分数 `:.2f` 格式化
- 新增新颖性判定/红队发现/引用验证/评审意见章节
- "深度分析候选方向 (N 个)" 动态标题
- MCP 计数标注去除 `~`

### P0#11/#12/#13/#14: 仪表盘全修

- **build_data.py**: `_aggregate_harness_runs` 按最佳轮迭代计算维度均分；`_parse_harness_candidates` 透传 novelty/redteam/critique 字段
- **p05.js**: 完全重写——6 维分组柱状图（无 stack）、badge 显示、弹窗新增新颖性/红队/评审意见/引用验证章节、创新点 `.claim` 提取、JS 自包含 `esc` 内联替换

---

## 最终验证跑分（Run #4, phase2_fix_verify）

| 候选 | 最终分 | 状态 | 新颖性（初始→最终） | 红队 | 引用验证 |
|------|--------|------|-------------------|------|---------|
| T005 (scVI) | 4.00 | ✅ 通过 | adjacent(10篇) → adjacent(15篇) 已复验 | 1H 2M 1L 已复验 | 1✅ 1❌ 3❓ |
| T001 (scGPT) | 3.15 | ❌ 未通过 | adjacent(1篇) → insufficient_evidence(0篇) 已复验 | 1H 2M 2L 已复验 | 1✅ 0❌ 4❓ |

- 引用验证: DOI 通道完美（Cui 2024 → scGPT 真实论文 verified；3 个假 DOI 正确标记 not_found）；accession 正确标记 unverifiable（GEO/ENCODE 不在文献索引中）
- 仪表盘浏览器实测：分组图正常、6 维全显、badge + 弹窗完整、创新点文本渲染正确、0 JS 错误

---

## 经验教训

### 1. 循环后交付逻辑必须在循环外显式验证

> **规则**: 任何在循环内跟踪 best-X 的逻辑，必须在循环结束后将 result.X 赋值为 best_X，且在代码审查时逐行验证循环后的赋值不会被覆盖。

### 2. 去重/过滤逻辑必须覆盖所有输入类型

> **规则**: 如果去重 key 是 `doi or pmid or title`，则对象 `{name:"Butler", year:2018}` 的 key 为空将被丢弃。要么扩展 key 策略，要么在 key 为空时使用递增计数器 `f"unspecified_{i}"` 保留条目。

### 3. 文献搜索验证必须区分强信号和弱信号

> **规则**: DOI/PMID → 强信号（API 判别可靠）。Accession → 弱信号（文献搜索不索引 GEO/ENCODE）→ unverifiable，提示人工核实。作者-年份 → 启发式（受查询质量影响大）。**强信号 not_found 是真正的幻觉警告；弱信号 not_found 只是"搜索未覆盖"。**

### 4. 搜索关键词质量决定验证准确率

> **规则**: author-year 引用验证的 context_keywords 只用方法名（如 "scGPT" "scVI" "Geneformer"），禁止附带疾病名。疾病名与引用论文的研究对象不匹配时会直接污染查询降命中率。

### 5. 状态性验证结果必须在状态变更后复验

> **规则**: 任何"状态性"验证（红队漏洞、新颖性判定）一旦其评估对象（方案）被修改，必须复验。存 initial 版本并打 `reverified_post_refine` 标记。未复验的 stale 结果比无结果更有害。

### 6. 计数器必须使用 delta 模式

> **规则**: 禁止 `total += engine.counter`（累计值重复加）。必须 `before=engine.counter; ...; total += engine.counter - before`。区分不同计数量纲（搜索次数 vs 论文数 vs 声明数），不混加。

### 7. 二进制判定"新颖/不新颖"不可靠，需第 3 态

> **规则**: `papers_found=0` 可能是"该领域没有相关工作"也可能是"搜索未覆盖"。必须引入 `insufficient_evidence` 态，其语义为"数据不足以做出判定"。`_aggregate_overall_verdict` 对 insufficient_evidence 采用保守策略（从不 falsly clear）。

### 8. 数据聚合语义必须跨模块一致

> **规则**: dashboard build_data 与 report 的维度均分必须是同一计算口径。最佳实践：定义单一规范（如"按候选最佳轮迭代取均值"），两个消费者都使用它。禁止各自实现不同的聚合逻辑。

### 9. 仪表盘数据透传原则

> **规则**: build_data `_parse_*` 解析函数默认透传源数据所有字段，不静默丢弃。新增字段走 `+=`，而非"只提取已知字段"。丢弃字段会导致仪表盘展示空白，且难以追溯到根因。

### 10. ECharts 多维评分图必须用分组柱状或雷达图

> **规则**: 禁止对语义独立的维度使用 stack 堆叠（总计无意义）。`yAxis.max` 必须 ≥ 最大可能值（5 分制维度为 5）。推荐 grouped bar（`stack: undefined`，`barWidth: 14`）或 radar chart。

### 11. 仪表盘 JS 渲染嵌套对象必须提取字段

> **规则**: 如果数据结构是 `innovation_points: [{claim:"...", closest_existing_work:"...", ...}]`，则渲染代码必须是 `ip.claim || JSON.stringify(ip)`，而非裸 `ip`（输出 `[object Object]`）。辅助函数（`esc`/`truncate`）在 tab 模块内自包含定义。

### 12. dashboard 数据语义对齐：iteration 聚合按最佳轮

> **规则**: build_data 聚合 candidate iterations 时，按 `max weighted_score` 选取最佳轮次，而非平均所有轮。这与 report 的 `final_score`（最佳轮得分）语义一致。维度均分 = 各候选最佳轮的维度评分均值。

---

## 修改文件总览

| 文件 | 改动 |
|------|------|
| `scripts/p05_harness/loop_runner.py` | best_plan 跟踪 + 交付；delta MCP 计数；refine 后复验；context_keywords 仅方法名；evidence fallback |
| `scripts/p05_harness/validators/citation_verifier.py` | 完全重写：三态验证 (verified/not_found/unverifiable)、accession+author-year 提取、去重回退链 |
| `scripts/p05_harness/search_engine.py` | 新增 `lookup_calls` 计数 |
| `scripts/p05_harness/phases/phase15_novelty_verify.py` | 新增 `insufficient_evidence` 判定；保守聚合策略 |
| `scripts/p05_harness/report.py` | 完全重写：6 维动态迭代表、新颖性/红队/引用验证章节、`.2f` 格式化、fallback 标注 |
| `dashboard/build_data.py` | 维度均分按最佳轮；透传 novelty/redteam/critique/litcov 字段 |
| `dashboard/js/tabs/p05.js` | 完全重写：6 维分组柱状图、badge、弹窗全字段、`[object Object]` 修复、esc 内联 |
| `dashboard/data.json` + `dashboard/index_standalone.html` | 重建（最终跑分数据） |
| `docs/session_2026-07-21_p05_harness_validation_fix.md` | 本日志 |
| `docs/CHANGELOG.md` | r11 条目 |
| `docs/TROUBLESHOOTING.md` | 新增 2 个 section（管线 bug + 仪表盘异常） |
| `docs/SKILL_DEVELOPMENT_GUIDE.md` | 新增 §10 P05 Harness 开发模式 |
| `AGENTS.md` | 新增 2 条 Dashboard 开发约定 |
