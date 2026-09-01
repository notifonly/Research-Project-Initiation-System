# P05 Harness Engineering — Session Work Journal

**Date**: 2026-07-15
**Session**: 为 p05 构建独立的 Research Plan Quality Harness (批判-修正循环 + MCP 文献补充 + 循环验收)
**Files Created**: 17 files (~75KB code), 2 docs

---

## 概述

p05 (Single-cell multi-omics FM benchmark) 经过完整 pipeline 运行后产出 445 证据卡、11 缺口、5 假设，但未收敛且方向分解的 40 个候选方向只有基础元数据 (research_question, scores, rationale)。需要一个专门的质量验收体系把候选方向转化为完整、可靠、经过评审的研究方案。

核心决策：**不复用 LoopEngine/Harness** — 它们设计用于全栈文献发现管线 (S1-S12, MCP文献爬取, 覆盖矩阵收敛)。p05 的需求是"对已有数据做深度分析+质量保证"，本质上是 LLM 写作+审稿循环，属于不同的计算范式。

---

## 变更清单

### 1. `scripts/p05_harness/config.yaml` (新建, 38 lines)

定义验收标准、MCP源、循环参数:
- `rubric`: 5维度权重 (literature_coverage:0.25, technical_feasibility:0.25, innovation_clarity:0.20, data_accessibility:0.15, gap_alignment:0.15)
- `loop.pass_threshold: 4.0`, `loop.min_dimension_score: 3.0`, `loop.max_iterations: 3`
- `mcp.search_sources: [semantic_scholar, pubmed, biorxiv, arxiv]`

### 2. `scripts/p05_harness/mcp/search_engine.py` (新建, 230 lines)

独立的 MCP 搜索引擎 — 创建自己的 `MCPRegistry` 实例，不依赖 SkillContext。

| 方法 | 功能 |
|------|------|
| `search(query)` | 多源并行搜索 → 标题MD5去重 → citation_count+年份评分 → 返回 top 20 |
| `search_multi(queries)` | 多查询合并搜索 → 全局去重 → 返回 top 30 |
| `verify_doi(doi)` | Crossref API DOI resolution → 验证标题/年份 |
| `verify_pmid(pmid)` | PubMed esummary → 验证标题/年份 |
| `_normalize_paper(item, source)` | 将所有源格式化为统一 paper dict |

**设计要点**: 各文献源 API 返回格式不同 (Semantic Scholar vs PubMed vs bioRxiv) → `_normalize_paper` 做统一，后续处理无需关心来源。

### 3. `scripts/p05_harness/mcp/query_generator.py` (新建, 70 lines)

LLM 将 critique 中发现的文献缺口转化为精确的学术搜索查询。

输入: critique_text + research_question + method + disease
输出: `[{"gap": "缺口描述", "gap_en": "...", "queries": ["q1", "q2", "q3"]}]`

### 4. `scripts/p05_harness/validators/rubric.py` (新建, 230 lines)

5 维评审量规，每维 1-5 分的详细评分标準描述 + LLM critique prompt。

`CritiqueResult`: 从 LLM 响应解析评分的 dataclass:
- `scores: dict[str, float]` — 各维度分数
- `weighted_score: float` — 加权总分
- `passed: bool` — weighted ≥ pass_threshold AND min_dim ≥ 3.0
- `detailed_feedback: dict` — 每个维度的具体建议
- `literature_gaps: list[str]` — 文献缺口主题

### 5. `scripts/p05_harness/validators/citation_verifier.py` (新建, 100 lines)

从方案中提取所有引用 (DOI/PMID)，通过 MCP 验证存在性。

`_extract_references(plan)`: 扫描 data_sources_detail[].url + summary_zh + technical_roadmap 中的 DOI/PMID 模式。

### 6. `scripts/p05_harness/validators/literature_check.py` (新建, 80 lines)

检查方案引用的文献与候选方向关联的证据卡之间的重叠度。

### 7. `scripts/p05_harness/validators/completeness_check.py` (新建, 80 lines)

非 LLM 结构校验: 检查 `summary_zh`, `technical_roadmap`, `data_sources_detail`, `feasibility`, `innovation_points`, `expected_outputs` 是否存在且非空；检查 `feasibility` 子字段；检查 `roadmap` 步骤是否含 `title/desc/methods`。

### 8. `scripts/p05_harness/phases/phase1_generate.py` (新建, 240 lines)

Phase 1: 初始方案生成 + MCP context 注入。

`generate_initial_plan()`: LLM 基于候选方向 + 证据卡 + 缺口 + 假设 + MCP补充文献 → 完整研究方案 JSON。

`enrich_context_with_mcp()`: Phase 0 — 对每个候选方向运行 MCP 搜索，取 top 5 论文，LLM 摘要后注入生成 prompt。

### 9. `scripts/p05_harness/phases/phase2_critique.py` (新建, 160 lines)

Phase 2: LLM 评审 + MCP 缺口补搜。

`critique_plan()`: 调用 rubric.py 中的 critique prompt → 返回 CritiqueResult。

`search_gap_literature()`: 如果 critique 检出文献缺口 → 调用 query_generator 生成搜索查询 → MCP 多源搜索 → 去重排名 → 返回 top 10。

### 10. `scripts/p05_harness/phases/phase3_refine.py` (新建, 140 lines)

Phase 3: LLM 修正方案 + MCP 引用验证。

`refine_plan()`: 将原方案 + 评审意见 + 新文献整合为一个修正 prompt → LLM 生成修正方案。

### 11. `scripts/p05_harness/loop_runner.py` (新建, 320 lines)

核心循环控制器。`LoopRunner` 管理每个候选方向的完整生命周期:

```
对每个候选方向:
  Phase 0: MCP context 预搜 → 注入
  Phase 1: LLM 生成初始方案
  Completeness check
  For iteration in 1..3:
    Phase 2: LLM 评审 → 文献低分? → MCP 缺口补搜
    记录 iteration record
    如果 passed → break
    如果最后一轮 → 不做 refine
    Phase 3: LLM 修正 → MCP 调用验证
  文献覆盖度检查
  保存 CandidateLoopResult
```

### 12. `scripts/p05_harness/main.py` (新建, 250 lines)

CLI 入口。调用链: `load_p05_data()` → `filter_candidates()` → `LoopRunner.run()` → `add_summaries()` → `generate_report()`.

数据加载: `decompose_pilot_results.json` (候选方向) + `evidence_cards.jsonl` (按 candidate:xxx tag 分组) + `final_report.json` (缺口+假设).

### 13. `scripts/p05_harness/report.py` (新建, 200 lines)

生成 Markdown 验收报告，包含: 总体统计、各维度平均分、深度分析迭代详情表、MCP补充文献统计、引用验证表、需人工复核清单。

---

## 5 条经验教训

### 1. 写作用质量循环 ≠ 发现用质量循环

LoopEngine 设计用于 full-stack discovery: S4 搜索 → S5 snowball → S6 筛选 → S7 提取 → S8-S9 匹配 → 覆盖矩阵收敛。每个步骤都是数据驱动、MCP 重型。

p05 harness 用于 plan quality: 1 次 LLM 生成 → N 次 LLM 批判→修正。LLM 调用是瓶颈，MCP 是辅助（只在批判指出缺口时触发）。强行复用 LoopEngine 会引入不需要的状态管理 (CardStore, CoverageMatrix, CheckpointManager)。

**经验**: 先判断任务范式——discovery vs quality——再决定复用还是新建。

### 2. MCP 搜索结果质量取决于查询生成质量

Phase 2 的"缺口补搜"看似简单，但 `query_generator.py` 是链上最脆弱的环节。如果 LLM 生成的查询太泛 (e.g. "scGPT cancer")，会返回大量无关论文。Prompt 中要求"使用 PubMed 兼容搜索语法 + 具体方法名 + 生物学概念"是关键。

**经验**: 搜索查询生成的 prompt 需要比批判 prompt 更严格的格式约束。

### 3. 引用验证的 ROI 有限但仪式感重要

`citation_verifier.py` 逐条验证 DOI/PMID 在 LLM 生成的内容中命中率不高 (LLM 倾向于生成 fake DOI)。但它提供了一种"验收仪式感"——让每个候选方向的方案经过真实的外部验证。对于需要人工复核的方案，它标记了哪些引用不可信。

**经验**: 即使是低命中率的验证器，作为质量门的存在本身就是价值。

### 4. 5 维评分的相关性陷阱

literature_coverage 和 innovation_clarity 高度相关——如果文献覆盖不足，创新点必然缺乏对比依据。gap_alignment 和 technical_feasibility 也相关——如果缺口未对齐，技术路线必然方向偏。这意味着某个维度低分很容易拖累整个评分。

**经验**: 在配置中设置 `min_dimension_score: 3.0` 而非仅看加权总分，防止某个维度极低分被其他高分掩盖。

### 5. 类型错误的 LSP vs 运行时

`search_engine.py` 中 `mcp.search()` 等方法来自 `BaseMCP` 的子类 (SemanticScholarMCP, PubMedMCP...)，LSP 无法推断这些方法在子类上的存在，报告大量 `Cannot access attribute` 错误。运行时因为 `MCPRegistry.get()` 返回正确的子类实例而正常工作。

**经验**: 使用 `# type: ignore[attr-defined]` 标记此类运行时多态，LSP 的警告是噪音而非 bug。

---

## 未完成项

以下是根据议题议程尚未完成的工作:

- [ ] `dashboard/js/tabs/p05.js` — p05 专属仪表盘页 (卡片网格+筛选+详情模态)
- [ ] `dashboard/build_data.py` — 新增 `_build_p05_candidates()` 数据聚合
- [ ] `dashboard/js/app.js` — 注册 p05 tab
- [ ] `dashboard/index.html` — 引入 p05.js
- [ ] 实际运行 `python scripts/p05_harness/main.py` 并验证产出
- [ ] 运行 `python dashboard/build_data.py` 重新构建仪表盘数据

---

## 文件清单

| 文件 | 大小 | 说明 |
|------|------|------|
| `scripts/p05_harness/__init__.py` | 36B | Package init |
| `scripts/p05_harness/config.yaml` | 1.0KB | 配置 |
| `scripts/p05_harness/main.py` | 9.6KB | CLI 入口 |
| `scripts/p05_harness/loop_runner.py` | 12.5KB | 循环控制器 |
| `scripts/p05_harness/report.py` | 6.6KB | 验收报告 |
| `scripts/p05_harness/mcp/search_engine.py` | 8.9KB | MCP 搜索 |
| `scripts/p05_harness/mcp/query_generator.py` | 2.2KB | 查询生成 |
| `scripts/p05_harness/phases/phase1_generate.py` | 8.5KB | 方案生成 |
| `scripts/p05_harness/phases/phase2_critique.py` | 4.8KB | 评审+补搜 |
| `scripts/p05_harness/phases/phase3_refine.py` | 4.7KB | 修正+引证 |
| `scripts/p05_harness/validators/rubric.py` | 7.8KB | 评审量规 |
| `scripts/p05_harness/validators/citation_verifier.py` | 3.4KB | 引证验证 |
| `scripts/p05_harness/validators/literature_check.py` | 2.4KB | 文献覆盖 |
| `scripts/p05_harness/validators/completeness_check.py` | 2.8KB | 结构校验 |
| `docs/session_2026-07-15_p05_harness_engineering.md` | — | 本文件 |
| `docs/CHANGELOG.md` (追加) | — | r6 条目 |
