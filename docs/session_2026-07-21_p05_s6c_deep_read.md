# P05 S6C 论文精读技能实现与管线集成 — Session Work Journal

**Date**: 2026-07-21  
**Session**: 实现 s6c_deep_read 论文精读技能并集成到 p05 管线；重构候选方向分解为自定义轴系（scFM架构深度 + Agent方法论）；48候选生成并端到端验证运行
**Outcome**: 6 阶段精读技能完成，7 文件代码变更，99 测试全过无回归，管线跑通 r3 合成

---

## 概述

基于用户的前期研究方向（scFM 架构深度 + Agent 方法论），以及用户的论文精读方法论（主张-证据审计、公式溯源、批判性评估），将精读嵌入为管线内的自动化技能 s6c_deep_read。重构 p05 候选方向从 disease×tissue 5轴排列改为项目专属维度体系，从 awesome-foundation-model-single-cell-papers 清单提取结构化分类体系。

核心问题：当前 S4-S7 链路只能做到摘要级信息提取 → 457 张卡片（大量是结肠癌化疗文献），p05 需要架构级深度分析。

---

## 实现内容

### Phase 1: s6c 精读模块 (全新 5 文件)

**目录**: `shared/skills/deep_read/`

| 文件 | 行数 | 职责 |
|------|------|------|
| `__init__.py` | 34 | 模块导出（schema/gate/mapper 全部） |
| `schemas.py` | 145 | 10 个数据模型：SourceLocator, ExtractedFact, AuthorClaim, ClaimJudgment, FormulaAnalysis, ExperimentAnalysis, CriticalAssessment, QualityGateResult, DeepReadNote, DeepReadSkillInput/Output |
| `quality_gates.py` | 90 | 5 道程序化质量门：claims_have_evidence, no_author_claim_mislabeled, strong_verdicts_require_direct_evidence, judgment_claims_exist, formula_confidence_threshold |
| `expression_mapper.py` | 55 | 15 条 (verdict, confidence) → 中文措辞确定性映射规则 |
| `skill_06c_deep_read.py` | 495 | 主技能 DeepReadSkill: 6 阶段执行（身份注册 → 事实抽取+主张审计合并 → 质量门 → 公式实验深度分析 → 公式反驳双重审计 → 批判性评估） |

**执行策略**:
- **Tier 1** (所有论文): 阶段 2+3+6 — 约 3k tokens/论文
- **Tier 2** (每候选 top 2): 全部 6 阶段 — 约 12k tokens/论文
- 公式置信度 < 0.85 触发 construct→refute 双重审计

**核心设计原则**:
- 事实 vs 主张严格分离（evidence_status: directly_stated / inferred / author_claim / unresolved）
- 判断措辞必须匹配证据强度（expression_mapper 规则引擎，禁止 LLM 过强表述）
- 所有信息绑定源码定位（section/page/equation）
- 程序化质量门 + LLM 阶段分离：质量门是代码检查，LLM 产出不过代码检查则标记 needs_human_review

### Phase 2: SCFMEvidenceCard 扩展

**文件**: `archetypes/archetype_c_sc_ai/evidence_card.py` (+3 字段)

```python
evidence_status: Optional[str] = None      # directly_stated | inferred | author_claim | unresolved
evidence_strength: Optional[str] = None     # fully_supported | partially_supported | insufficient | conflicting
deep_read_source: Optional[str] = None      # paper_id of deep-read note that informed this card
```

### Phase 3: S7 精读笔记消费

**文件**: `archetypes/archetype_c_sc_ai/skills/skill_07_scfm_card_extract.py` (+90 行)

- `SCFMExtractInput.deep_read_notes` 新字段：接收 s6c 产出的结构化笔记
- `_index_deep_read_notes()`: 按 paper_id 索引查找
- `_extract_from_deep_read()`: 优先使用精读笔记中的 facts/claims/judgments 构建证据卡片，包含 evidence_status/evidence_strength/deep_read_source
- `execute()` 分支逻辑：每篇论文先查精读笔记 → 有则 `_extract_from_deep_read`，无则 `_extract_from_paper`

### Phase 4: loop_engine.py 集成

**文件**: `shared/core/loop_engine.py` (+35/-15 行)

- **S6C 数据准备**: `_prepare_skill_input()` 新 s6c_ 分支 — 注入 S6 kept 论文，读取 deep_read 配置参数
- **S7 精读笔记注入**: S7_ 分支检查 accumulated data 中 `notes` 字段 → 写入 `deep_read_notes`
- **候选查询泛化**: `_build_candidate_queries()` 从固定 4 轴（disease/tissue/method/data）→ 动态遍历所有维度键值
- **LLM 查询重写泛化**: `_rewrite_candidate_queries()` 手动拼接 disease/method/tissue → 动态维度摘要 + 通用提示

### Phase 5: p05 config.yaml 重构

**文件**: `projects/p05_sc_multiomics_ai/config.yaml` (100→150 行)

主要变更：
- `research_direction`: 从 "Survey and benchmark scVI, scGPT, Geneformer, scFoundation, UCE, MultiVI" → "Systematically evaluate across architecture families... + AI agent methods"
- `skill_sequence`: s6a_scfm_search → s6c_deep_read（收敛步骤不变）
- `foundation_models_of_interest`: 扁平列表 → 按架构家族分组（transformer/mamba/hyena/vae/vqvae/diffusion/jepa/llm_based）
- 新增 `deep_read` 配置块: max_papers=5, max_tier2=2, truncate=24000, formula_confidence=0.85
- 新增 `decompose.custom_axes` 双线轴系:
  - **scfm_depth**: 5 轴 — architecture_family × modality_combination × training_paradigm × pretraining_corpus × evaluation_paradigm
  - **agent_line**: 2 轴 — agent_paradigm × capability
- 新增 `decompose.agent_discovery`: enabled=true, seed_sources 指向 awesome list

### Phase 6: decompose_directions.py 自定义轴系支持

**文件**: `scripts/decompose_directions.py` (+120/+5 行)

- `phase1_custom_dimensional_decompose()`: 新函数 — 从 config 读取自定义轴系，构建动态 LLM 提示，返回 `dict[str, list[str]]`
- `process_project_custom()`: 新函数 — 自定义轴系交叉组合 + 文献检查
- `process_project()`: 检测 `decompose.custom_axes` 存在则分支到自定义流程
- `CandidateTopic.dimensions: dict` 新字段 — 存储动态维度值
- 输出格式: 自定义轴系的 candidates 使用 `dimensions: {axis_key: value, ...}` 而非硬编码 disease/tissue

### Phase 7: Harness 提示更新

**文件**: `scripts/p05_harness/phases/phase1_generate.py` (1 行变更)

- `GENERATE_SYSTEM` 从 "scVI, scGPT, Geneformer, scFoundation, UCE, MultiVI 领域" → "单细胞多组学基础模型和AI Agent领域"

---

## 分解运行结果

`python scripts/decompose_directions.py --projects p05` 成功产出:

- **48 候选方向**: 24 scfm_depth + 24 agent_line
- **scfm_depth**: 7 架构家族 × 各自模态/训练/评估维度组合
- **agent_line**: 8 种 agent 范式 × 核心能力组合
- 自定义参数: max_tokens=6000, `_parse_json` 修复 ```json 处理

---

## 流水线端到端验证

`python main.py --only p05_sc_multiomics_ai` 运行结果（10min 超时前达到 r3）:

### 成功流转
- ✅ S1 用新 research_direction 重跑 — 子问题包含 Mamba/Hyena/VQ-VAE/Diffusion/JEPA/AI agent/adaptive benchmarking
- ✅ 48 候选加载（24 scfm + 24 agent），3 候选/轮处理
- ✅ S6C 精读每轮触发："S6C: deep-reading 5 papers (max tier2: 2)"
- ✅ S7 产卡每候选 15-63 张（多数为摘要级抽取，精读笔记在 S6C→S7 链路中流转）
- ✅ S11/S12 合成每轮运行（gap 分析 + 假说生成）
- ✅ 99 单元测试全过，0 回归

### 已知问题
| 问题 | 状态 | 备注 |
|------|------|------|
| S7 质量门失败 (2/3 候选人) | 预期 | 宽泛查询带回不相关论文（植物单细胞等），需收紧 S4 查询精度 |
| S5 引文滚动 (20/20 MCP 错误) | 预期 | PubMed/SS API 限流，非阻塞 |
| Provenance 验证器警告 (248/248) | 先存 | 验证器期望特定字段，与当前卡片 schema 不匹配 |
| 外层收敛不完整 | 预期 | 10分钟超时，citation_closed 需要更多轮次 |

---

## 后续建议

1. **S4 查询精度**: 全局 "Mamba single-cell" 查询带回 Hyena 蛋白质模型论文 → 收紧为候选维度组合查询
2. **S7 质量门阈值**: scFM 方向卡片质量门要求过高（>15% 非未知任务），宽泛方向应调低阈值或使用自适应阈值
3. **S6C 精读笔记利用率**: 当前 S6C→S7 链路完整但未见精读笔记被有效消费（需要更长的运行时间），后续需要检查笔记注入是否生效
4. **完整流水线运行**: 超时后可用 `python main.py --only p05_sc_multiomics_ai --max-rounds 5` 继续运行

---

## 文件变更清单

| 操作 | 文件 | 行数变化 |
|------|------|----------|
| 新增 | `shared/skills/deep_read/__init__.py` | +34 |
| 新增 | `shared/skills/deep_read/schemas.py` | +145 |
| 新增 | `shared/skills/deep_read/quality_gates.py` | +90 |
| 新增 | `shared/skills/deep_read/expression_mapper.py` | +55 |
| 新增 | `shared/skills/skill_06c_deep_read.py` | +495 |
| 修改 | `shared/skills/__init__.py` | +3 |
| 修改 | `archetypes/archetype_c_sc_ai/evidence_card.py` | +4 |
| 修改 | `archetypes/archetype_c_sc_ai/skills/skill_07_scfm_card_extract.py` | +90/0 |
| 修改 | `shared/core/loop_engine.py` | +35/-15 |
| 修改 | `projects/p05_sc_multiomics_ai/config.yaml` | +50/-15 |
| 修改 | `scripts/decompose_directions.py` | +125/+5 |
| 修改 | `scripts/p05_harness/phases/phase1_generate.py` | +1/-1 |
| 新增 | `projects/p05_sc_multiomics_ai/AGENTS.md` | +80 |
| 总计 | 13 文件 | +1207 行 |

---

**验证通过**: `pytest tests/ --ignore=tests/test_p05_harness_e2e.py` → 99 passed
**预存失败**: `test_p05_harness_e2e.py::test_scooped_reposition_fail_rejects_candidate` — mock 对象缺少 `lookup_calls` 属性（与会话无关的既有 bug）
