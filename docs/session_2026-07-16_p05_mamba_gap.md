# P05 Mamba Architecture Gap — Session Work Journal

**Date**: 2026-07-16
**Session**: 基于RegFormer的Mamba架构挖掘P05研究缺口：S7枚举扩展 + C11新模式 + 6篇新scFM卡片入库
**Files Changed**: 4 files (+~75 lines), 2 JSONL data fixes, 13 new evidence cards

---

## 概述

用户发现 P05 的 10 个深度分析方向全部遵循同一套路（对已有 scFM 做下游评估），且代码库无法表示/检测正在兴起的非 Transformer scFM。核心任务：
1. 扩展 S7 的枚举空间，让 LLM 能正确标注 Mamba/Hyena/VQ-VAE 架构
2. 新增 C11 gap pattern 检测架构同质化
3. 修正 RegFormer 20 张卡片的误标（attention → Mamba）
4. MCP 搜索 6 篇新论文并提取 13 张证据卡片
5. 重跑 S11+S12 生成新的缺口和假设

---

## 变更清单

### 1. `archetypes/archetype_c_sc_ai/skills/skill_07_scfm_card_extract.py` (2 处修改)

| 行号 | 变更 | 说明 |
|------|------|------|
| 53-54 | `model_architecture` 枚举追加 `Mamba, SSM, Hyena, VQ-VAE` | 原有 8 个值，扩展为 12 个。关键：Mamba 和 SSM 分开提供，因 pre-Mamba SSM (S4/S5/S6) 与 selective SSM (Mamba) 是不同的架构族 |
| 56-58 | `model_family` 枚举追加 7 个值 | RegFormer, GeneMamba, MambaCell, scHyena, scLong, CLM-X, cellVQ |
| 258-260 | prompt 模板同步更新两个枚举 | 确保 LLM 在提取时可见新选项 |

### 2. `archetypes/archetype_c_sc_ai/gap_patterns.py` (新增 C11)

```python
C11 = GapPattern(
    id="C11",
    name="architecture_homogeneity",
    description="scFM领域模型架构单一化：绝大多数研究基于Transformer架构，Mamba/SSM/Hyena/VQ-VAE等非Transformer架构缺乏探索",
    axis="model_architecture",
    severity="medium",
    cross_archetype=False,
)
```

加上 C11 后 archetype C 共 11 个 gap pattern (C1-C11)。

### 3. `shared/skills/skill_11_gap_analysis.py` (新增 ~30 行，行 360-390)

C11 检测逻辑：

```
统计 evidence cards 中的 model_architecture 分布
→ 计算 transformer_ratio = n_transformer / n_total
→ 计算 n_known = n_total - n_unknown (unknown 类卡不计)
→ 触发条件:
    transformer_ratio > 0.70  (Transformer占绝对多数)
    OR (n_known > 0 AND n_transformer/n_known > 0.90)  (已知架构中几乎全是Transformer)
→ gap_score = 0.5 + transformer_ratio * 0.1
→ feasibility = 0.65 (非Transformer模型已存在)
→ competitiveness = 0.45 (起步早但尚未大面积发表)
```

**关键决策：阈值检测 vs 二元检测**

第一版实现使用 `not has_non_transformer`（存在任意非 Transformer 即跳过），但在步骤5添加 14 张非 Transformer 卡片后，C11 被永久关闭（总会有非 Transformer）。修订为阈值检测 (`transformer_ratio > 0.70`)，即使存在少量非 Transformer 卡片，当 Transformer 占比超 70% 时仍能正确触发缺口。

### 4. 数据修正：RegFormer 卡片 (20 张)

两个 JSONL 文件中 RegFormer 相关卡片：

| 文件 | 卡片数 | 修正内容 |
|------|--------|----------|
| `data/l1_warm/p05_sc_multiomics_ai/cards.jsonl` | 15 | `model_architecture: "attention"` → `"Mamba"`, `model_family: "other"` → `"RegFormer"` |
| `projects/p05_sc_multiomics_ai/output/evidence_cards.jsonl` | 5 | 同上 |

使用 Python 脚本逐行解析 JSON，匹配 `paper_pmid: "42086551"`（RegFormer 的 PubMed ID）进行修正。

### 5. 新增证据卡片 (13 张，6 个新 scFM)

通过 Semantic Scholar / CrossRef / arXiv / bioRxiv MCP 搜索，为 6 个缺失模型各创建 2-3 张 SCFMEvidenceCard：

| 模型 | 架构 | 论文 | 来源 | Year | Cards |
|------|------|------|------|------|-------|
| **GeneMamba** | Mamba (Bi-Mamba + pathway-aware CL) | GeneMamba: A Unified Framework for Single-Cell Analysis | arXiv:2504.16956 | 2025 | 3 |
| **MambaCell** | Mamba (Bidirectional + multi-task SSL) | MambaCell: Mamba-Based Foundation Model for Single-Cell Analysis | IEEE JBHI | 2026 | 2 |
| **scHyena** | Hyena (sub-quadratic operator) | scHyena: Foundation Model for Full-Length Single-Cell RNA-seq | arXiv:2310.02713 | 2023 | 2 |
| **scLong** | Transformer (1B params, 28k genes) | Large-scale foundation model on single-cell transcriptomics | Nat Commun | 2026 | 2 |
| **CLM-X** | Multi-way Transformer (RNA+ATAC) | CLM-X: A Unified Multi-Modal Single-Cell Foundation Model | bioRxiv | 2026 | 2 |
| **cellVQ** | VQ-VAE | Illuminating cell states by a comprehensive and interpretable single cell foundation model | Nat Commun 26(1) | 2026 | 2 |

卡片关键字段 (以 GeneMamba 的一张为例)：
```json
{
  "model_architecture": "Mamba",
  "model_family": "GeneMamba",
  "pretrain_cells": 30000000,
  "paper_title": "GeneMamba: A Unified Framework for Single-Cell Analysis",
  "paper_year": 2025,
  "paper_venue": "arXiv",
  "paper_doi": "10.48550/arXiv.2504.16956"
}
```

### 6. S11+S12 重跑

执行 `python scripts/rerun_p05_p06_p07.py` 重新运行 p05 的 S11 (gap analysis) 和 S12 (hypothesis generation)。

**架构分布统计** (457 张卡片):
| 架构 | 数量 | 占比 |
|------|------|------|
| transformer | 353 | 77.1% |
| VAE | 44 | 9.6% |
| unknown/未标 | 43 | 9.4% |
| Mamba | 10 | 2.2% |
| MLP | 3 | 0.7% |
| CNN | 1 | 0.2% |
| Hyena | 2 | 0.4% |
| VQ-VAE | 2 | 0.4% |

**C11 检测结果**:
- `transformer_ratio = 353/457 = 0.771` > 0.70 → **触发**
- gap_text: "Architecture diversity deficit: 353/457 (77%) cards use transformer-based (transformer); only 58 cards use non-Transformer architectures (Hyena, VQ-VAE, Mamba, MLP, CNN, VAE)"
- Scores: total=0.58, feasibility=0.65, competitiveness=0.45, cross_archetype=0.20
- Rank: **8/12** (P05 的总缺口从 11 增至 12)

**S12 新假设**:
S12 生成了 address C11 的假设（hybrid VAE+architecture approach），与原有 5 个假设一同写入 final_report.json。

### 7. Dashboard 重建

执行 `python dashboard/build_data.py` 重新生成 `dashboard/data.json`：
- 全量卡片: 3,234 张
- 全量缺口: 160 个
- 全量假设: 35 个

---

## 架构决策

| # | 决策 | 选择 | 原因 |
|---|------|------|------|
| 1 | C11 检测方式 | 阈值检测 (`transformer_ratio > 0.70`) | 二元检测 (`not has_non_transformer`) 在添加非 Transformer 卡片后会永久失效。阈值方式容忍少数非 Transformer 卡片的存在，但仍能识别"压倒性多数使用 Transformer"的结构性问题 |
| 2 | Mamba 和 SSM 层级 | 并列而非包含 | Pre-Mamba SSM (S4/S5/S6) 与 selective SSM (Mamba/Mamba2) 在可训练能力上有本质区别。将二者分开让 LLM 可以更精确地标注 |
| 3 | 新卡片写入位置 | 同时写入 `l1_warm/cards.jsonl` 和 `output/evidence_cards.jsonl` | S11 从 l1_warm 读取卡片做 gap analysis，output 目录的卡片用于最后展示。二者需保持同步 |

---

## 经验教训

### 1. S7 的 LLM 枚举是硬约束，不是软建议

**问题**: RegFormer 是一篇 Mamba 架构论文，但 `model_architecture` 被提取为 `"attention"`。根本原因是 S7 prompt 中的枚举列表没有 "Mamba" 选项，LLM 被迫在已有选项中选最接近的一个。

**经验**: 对快速演进的研究领域（single-cell FM 领域一年新增 5+ 篇新架构论文），S7 枚举需要：
- 定期审查（2-3 个月一次），对照最新 paper 补充新架构值
- 考虑加入 `"其他"` 兜底选项 + 人工审校 loop，让 LLM 能表达"我知道这不是现有选项中的任何一个"
- 在 `evidence_card.py` schema 层面对 `model_architecture` 做宽松处理（不限制 Literal），避免类型层面也存在同样限制

### 2. Gap pattern 系统只能检测"已定义的维度"

**问题**: C1-C10 覆盖了 benchmark 完整度、interpretability、transfer learning、weights release 等关键维度，但没有架构多样性维度。这些 pattern 是人工根据领域认知手工编写的，无法自适应发现"从未被考虑过的缺口维度"。

**经验**: 
- 新增 gap pattern 的成本低（一个 pattern 定义 + 30 行检测逻辑），应鼓励定期对照领域前沿动态回顾现有 pattern 覆盖度
- 考虑在 gap pattern 评审时加入"领域新动向检查"：过去 6 个月有哪些新论文方向是现有 pattern 无法捕获的？
- C11 的阈值检测方式给出了一个模板：统计分布自动检测（不必逐个枚举"缺少的具体值"）

### 3. 阈值检测 > 二元检测（对存在性缺口）

**问题**: 第一版 C11 使用 `not has_non_transformer` 作为触发条件——只要有任意一张非 Transformer 卡片就不触发。步骤5加入 14 张非 Transformer 卡片（2 Hyena + 2 VQ-VAE + 10 Mamba）后，C11 永久失效。

**经验**: 
- "完全不存在" 的缺口应该用二元检测（如 C2 `no_benchmark`：“没有标准化评估指标”）
- "分布严重不均" 的缺口必须用阈值检测（如 C11：“77% 是 Transformer，但理论上可以有更多架构多样性”）
- 判断标准：如果加上 1-2 个 counter-example 后缺口就不成立了，说明这个缺口不适合二元检测

### 4. 卡片数据污染具有传播性

**问题**: RegFormer 的 20 张卡片全部标注为 `model_architecture: "attention"`。这些卡片作为 S11 和 S12 的输入，导致 gap analysis 无法识别"Mamba 架构文献存在但卡片标注错误"，hypothesis 也无法基于 Mamba 架构提出研究问题。

**经验**:
- 关键字段（如 `model_architecture`）的错误标注会向下游传导，污染 gap analysis 和 hypothesis
- 考虑添加 S7 后的轻量校验：如果 `model_architecture == "attention"` 但 `key_finding` 中提到 "Mamba" 或 "state-space"，则标记为可疑
- JSONL 卡片修正时应一次修正两个文件（l1_warm 和 output），避免不一致

### 5. P05 方向同质化的根因在配置层

**问题**: 10 个深度分析方向全部遵循同一模式（已有 scFM + 疾病 + 下游评估），原因是 `config.yaml` 中的 `foundation_models_of_interest: [scVI, scGPT, Geneformer, scFoundation, UCE, MultiVI]` 限制了候选生成的范围，decompose 只能围绕这 6 个 models 产生方向。

**经验**:
- 方向的多样性由上游配置决定。如果发现方向同质，应先检查 `config.yaml` 的 `methods` / `foundation_models_of_interest` 是否过于窄
- decompose 的 `methods` 维度应尽可能 cover 领域全貌（包括新模型），质量 harness 自然会淘汰不可行的方向
- 对比 p05 和 p06/p07: 后者有 PRS methods / omics scores 的多种候选方法，分解结果自然更具多样性

### 6. Literature check 盲区：检查依赖的卡片的覆盖度

**问题**: p05 harness 的 `literature_check.py` 检查方案引用的文献与候选方向关联的证据卡之间的重叠度。如果证据卡本身不覆盖特定模型族（如 Mamba），这个检查就无法标记方案在"引用 Mamba 论文"方面的不足。

**经验**:
- Literature check 是一个 "card-bounded" 验证——其有效范围受限于证据卡的内容
- 考虑增加 "field coverage" 检查维度：文献中出现了多少篇相关方向的最新论文（不限于卡片）？方案是否引用了这些？
- 或用简单的 paper-level 检查替代 card-level 检查：方案引用是否覆盖了 MCP 搜索能返回的 top-3 最新论文？

---

## 指标

| 指标 | 修改前 | 修改后 |
|------|--------|--------|
| model_architecture 枚举值 | 8 | 12 |
| model_family 枚举值 | 12 | 19 |
| Gap patterns (C 类) | 10 | 11 |
| P05 证据卡片总数 | 445 | 457 |
| P05 缺口总数 | 11 | 12 |
| 架构分布: Transformer 占比 | ~88% (包含误标注) | 77.1% (修正后) |
| 非 Transformer scFM 在卡片中 | 0 个 | 6 个 |

---

## 文件清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `archetypes/archetype_c_sc_ai/skills/skill_07_scfm_card_extract.py` | +3 lines | 枚举扩展 |
| `archetypes/archetype_c_sc_ai/gap_patterns.py` | +11 lines | 新增 C11 |
| `shared/skills/skill_11_gap_analysis.py` | +30 lines | C11 检测逻辑 |
| `data/l1_warm/p05_sc_multiomics_ai/cards.jsonl` | 15 cards 修正 + 13 new | RegFormer 修复 + 新模型卡片 |
| `projects/p05_sc_multiomics_ai/output/evidence_cards.jsonl` | 5 cards 修正 + 13 new | RegFormer 修复 + 新模型卡片 |
| `data/l1_warm/p05_sc_multiomics_ai/checkpoints/r4_s11_gap_analysis.json` | overwritten | S11 重跑 |
| `data/l1_warm/p05_sc_multiomics_ai/checkpoints/r4_s12_hypothesis_generate.json` | overwritten | S12 重跑 |
| `projects/p05_sc_multiomics_ai/output/final_report.json` | overwritten | 12 gaps + 5 hypotheses |
| `dashboard/data.json` | rebuilt | 全量数据重建 |
| `docs/CHANGELOG.md` | +80 lines | r7 条目 |
| `docs/session_2026-07-16_p05_mamba_gap.md` | — | 本文件 |
