# 自进化基准测试智能体 — 研究方案报告

> 候选编号: p05_agent_benchmark_003 · 版本: v1 · 日期: 2026-07-22
> 所属项目: p05_sc_multiomics_ai (单细胞多组学基础模型基准评测)
> 评审结果: **通过** (4.0/5.0)

---

## 1. 研究概览

| 字段 | 内容 |
|---|---|
| **候选 ID** | p05_agent_benchmark_003 |
| **研究方向** | AI Agent — Self-Evolving Benchmark Agent |
| **核心方法** | Self-Evolving Benchmark Agent (continuous evaluation + adaptive suite expansion) |
| **适用领域** | Cross-task generalization (12 scFM evaluation tasks) |
| **combined_score** | 0.94 |
| **final_score** | 4.0 / 5.0 (通过) |
| **通过阈值** | ≥ 4.0 |
| **投递目标** | Nature Methods / Genome Biology / Cell Systems |

**核心研究问题**:

> How can a self-evolving benchmark agent that continuously evaluates single-cell foundation models across 12 tasks (cell-type annotation, batch integration, perturbation prediction, gene regulatory network inference, imputation, zero-shot generalization, etc.), automatically identifies model weaknesses through performance decomposition analysis, and extends the benchmark suite with targeted adversarial evaluations, produce more comprehensive and fair model comparisons than static benchmark suites (scIB, OpenProblems) measured by inter-model ranking stability and coverage of failure modes?

---

## 2. 研究背景与动机

### 2.1 现有静态基准的局限

当前单细胞基础模型（scFM）评估主要依赖两个静态基准套件：

- **scIB** (Luecken et al., 2022, Nature Methods)：覆盖批次整合和细胞类型注释 2-3 项任务
- **OpenProblems** (Luecken et al., 2021, NeurIPS)：覆盖批次整合、细胞类型注释和扰动预测

这些静态基准面临 **Goodhart 定律**问题：当指标成为优化目标时，其评估有效性下降。模型可能过拟合于固定测试集，导致排名不再反映真实泛化能力。

### 2.2 缺失的评估维度

现有基准未覆盖以下前沿评估场景：

| 缺失维度 | 相关文献 |
|---|---|
| 零样本泛化（跨数据集） | Kedzierska et al., 2025 |
| 扰动预测基准 | PertEval-scFM (Wenteler et al., 2025) |
| 低监督场景泛化 | CellBench-LS (Xu et al., 2026) |
| 跨模态泛化（RNA→ATAC→Protein） | CITE-seq 场景 |
| 生物驱动评估标准 | Wu et al., 2025 |
| 模型接口统一 | BioLLM (Qiu et al., 2024), scUnify (Kim et al., 2026) |

### 2.3 本方案的核心主张

构建一个 **评估引擎 → 弱点检测 → 对抗测试生成 → 套件扩展** 的闭环系统，通过两个**元指标**量化评估质量：

1. **跨模型排名稳定性** (Kendall's W / Spearman rank correlation)
2. **失败模式覆盖率** (新发现失败模式数 / 总失败模式数)

---

## 3. 技术方案

**总工期**: 46 周 (约 12 个月)

### Step 1: 构建基础评估引擎与 12 项任务实现 (8 周)

#### 覆盖任务

| 任务 | 评估指标 | 参考框架 |
|---|---|---|
| 细胞类型注释 | F1-score, 宏平均准确率 | scIB |
| 批次整合 | iLISI, cLISI, ASW, kBET | scIB, OpenProblems |
| 扰动预测 | Pearson 相关系数, RMSE | PertEval-scFM (Wenteler et al., 2025) |
| 基因调控网络推断 | AUROC, AUPRC | BEELINE |
| 数据填补 | RMSE, 余弦相似度 | OpenProblems |
| 零样本泛化 | 跨数据集准确率 | Kedzierska et al., 2025 |
| 跨模态泛化 | CITE-seq 数据评估 | — |
| 低监督场景泛化 | 标签稀疏场景准确率 | CellBench-LS (Xu et al., 2026) |
| 可扩展性 | 推理时间, GPU 内存 | — |
| 可解释性 | 注意力权重分析 | — |
| 跨物种泛化 | 物种间迁移准确率 | — |
| 鲁棒性 | 噪声/批次扰动下性能保持率 | — |

#### 性能分解分析

采用**特征分组策略**定位模型弱点：

- 将细胞按稀有类型（<1%）、高噪声基因（变异系数 >2）、不同批次分组
- 使用 SHAP 的 KernelExplainer，以模型输出为黑盒函数
- 每组细胞作为特征组，计算边际贡献 → 输出弱点热力图

**工具**: scib, openproblems, scanpy, scvi-tools, PyTorch Lightning, SHAP
**产出**: 标准化评估代码库 + 弱点分析模块

---

### Step 2: 集成现有单细胞基础模型并建立基线 (10 周)

#### 目标模型

| 模型 | 加载方式 | 架构 |
|---|---|---|
| scVI | scvi-tools | VAE |
| scGPT | HuggingFace Transformers | Transformer |
| Geneformer | HuggingFace Transformers | Transformer |
| scFoundation | 官方仓库 | Transformer |
| UCE | 官方仓库 | Transformer |
| MultiVI | scvi-tools | VAE |

#### 统一推理接口

- 数据格式: AnnData (h5ad)
- 基因 ID 映射: Ensembl ID → 模型词汇表
- 批次处理: 参考 BioLLM 和 scUnify 适配器模式
- 额外记录: GPU 内存、推理时间

**工具**: HuggingFace Transformers, scvi-tools, scFoundation, UCE, AnnData, PyTorch
**产出**: 6 模型 × 12 任务基线性能报告 + 统一接口代码库

---

### Step 3: 开发弱点检测与对抗性测试生成模块 (10 周)

#### 核心流程

```
性能分解热力图 → DBSCAN 聚类 → 系统性失败模式识别 → 对抗测试生成
```

#### 对抗测试生成策略

| 类型 | 方法 | 示例 |
|---|---|---|
| 数据扰动 | 添加噪声、模拟批次效应 | scGen/scVI 数据生成 |
| 任务变体 | 跨物种/跨模态/低监督 | 参考 CellBench-LS |
| 组合挑战 | 稀有细胞类型 + 高噪声 | 采样策略 |

#### 质量门控

- MMD 距离阈值 < 0.05 确保合成数据质量 (Wu et al., 2025)
- Pearson 相关系数 > 0.3 确保任务相关性

**工具**: DBSCAN, scGen, scvi-tools, PyTorch, scikit-learn, MMD
**产出**: 弱点检测算法 + 对抗测试生成模块 + 首批 20+ 对抗测试用例

---

### Step 4: 实现自进化循环与元指标评估 (10 周)

#### 自进化循环

```
迭代 1: 评估 → 弱点检测 → 对抗生成 → 套件扩展
迭代 2: 重新评估 → 新弱点检测 → 新对抗 → 套件再扩展
...
迭代 5: 收敛评估
```

#### 元指标

| 指标 | 计算方法 | 含义 |
|---|---|---|
| 排名稳定性 | Kendall's W, Spearman 秩相关 | 模型排名在迭代间是否收敛 |
| 失败模式覆盖率 | 新失败模式 / 总失败模式 | 是否持续发现新弱点 |
| 对抗测试有效性 | AUC-ROC 区分模型强弱 | 生成测试的判别力 |

#### 与静态基准对比

- 记录 scIB/OpenProblems 的排名与覆盖率
- 量化自进化基准相对于静态基准的改进幅度

**工具**: scipy.stats, scikit-learn, matplotlib, seaborn, pandas
**产出**: 5 轮迭代评估结果 + 元指标分析报告 + 静态基准对比

---

### Step 5: 验证、文档化与开源发布 (8 周)

- 独立验证数据集（不同平台/物种）测试泛化能力
- Sphinx 文档 + pytest 单元测试 + GitHub Actions CI/CD
- GitHub + PyPI 开源发布 + ReadTheDocs 部署
- 预印本 + 与 scIB/OpenProblems 社区沟通集成可能性

---

## 4. 数据与资源

### 数据集清单

| 数据集 | 规模 | 许可 | 用途 |
|---|---|---|---|
| PBMC 10k (10x Genomics) | ~10K 细胞 | CC-BY 4.0 | 细胞类型注释、批次整合 |
| HCA 骨髓数据 | ~100K 细胞 | ODC-By 1.0 | 批次整合、零样本泛化 |
| Tabula Sapiens | ~500K 细胞 | CC-BY 4.0 | 零样本泛化、跨组织 |
| scPerturb | ~100K 细胞 | MIT | 扰动预测 |
| BEELINE | ~1K-10K 细胞/数据集 | GPL-3.0 | GRN 推断 |
| OpenProblems NeurIPS 2021 | ~50K 细胞 | CC-BY 4.0 | 标准化基准 |
| CITE-seq PBMC | ~10K 细胞+200 蛋白质 | GEO 公开 | 跨模态泛化 |
| CellBench-LS | 5K-50K 细胞/数据集 | CC-BY 4.0 | 低监督场景 |

### 计算资源估算

- **GPU**: 约 6,000 GPU 小时
- **平台**: AWS (p3.2xlarge/p4d) 或 4× NVIDIA A100 本地集群
- **优势**: 所有模型有公开预训练权重，无需从头训练

---

## 5. 可行性分析

| 维度 | 评分 | 说明 |
|---|---|---|
| 数据可及性 | 92/100 | 全部公开数据集，含备选方案 |
| 技术难度 | 78/100 (高) | 多框架模型接口整合困难，但 BioLLM/scUnify 可降低难度 |
| 时间可行性 | 12 个月 | 已为对抗测试生成和循环迭代预留缓冲 |

### 关键风险与缓解

| 风险 | 缓解措施 |
|---|---|
| 模型接口不统一 | 适配器模式封装, 参考 BioLLM/scUnify |
| 对抗测试低质量 | MMD 距离 + 相关性双重门控 |
| 自进化局部最优 | 随机扰动 + 多样性采样 |
| 计算资源超支 | 混合精度推理 + 模型量化 |
| 社区接受度低 | 与 scIB/OpenProblems 合作推广 |

---

## 6. 创新点与差异化

### 创新点 1: 自进化基准概念

首次将自进化智能体概念引入单细胞基础模型评估，解决静态基准的 Goodhart 问题。与 scIB (Luecken et al., 2022) 和 OpenProblems (Luecken et al., 2021) 形成互补。

### 创新点 2: 弱点驱动的对抗测试生成

性能分解分析 → 弱点定位 → 针对性对抗测试的自动化闭环，区别于手动设计评估任务的传统方法。引用 Kedzierska et al., 2025 的零样本评估和 Wenteler et al., 2025 的扰动预测基准。

### 创新点 3: 元指标量化基准质量

跨模型排名稳定性 + 失败模式覆盖率作为评估基准本身质量的指标，为基准社区提供新维度。参考 Goodhart 定律讨论 (Manheim & Garrabrant, 2019)。

### 创新点 4: 12 任务全面覆盖

比 scIB (2-3 项) 和 OpenProblems (3 项) 覆盖更广，特别是零样本泛化、跨模态泛化、低监督场景等前沿任务：

| 任务 | scIB | OpenProblems | 本方案 |
|---|---|---|---|
| 批次整合 | ✓ | ✓ | ✓ |
| 细胞类型注释 | ✓ | ✓ | ✓ |
| 扰动预测 | ✗ | ✓ | ✓ |
| 零样本泛化 | ✗ | ✗ | ✓ |
| 跨模态泛化 | ✗ | ✗ | ✓ |
| 低监督场景 | ✗ | ✗ | ✓ |
| GRN 推断 | ✗ | ✗ | ✓ |
| 数据填补 | ✗ | ✗ | ✓ |

---

## 7. 预期产出

1. **自进化基准框架开源代码库** (GitHub + PyPI) — 引用 BioLLM 和 scUnify 设计
2. **6 个 scFM 在 12 项任务上的详细性能报告和弱点分析** — 引用 Kedzierska et al., 2025; Wu et al., 2025
3. **不少于 50 个对抗性测试用例库** — 覆盖零样本、低监督、跨模态场景
4. **5 轮自进化迭代的元指标评估报告** — 与 scIB/OpenProblems 对比
5. **预印本论文** — 引用 ≥ 10 篇核心文献 (Luecken et al., 2022; Luecken et al., 2021; Kedzierska et al., 2025; Wenteler et al., 2025; Wu et al., 2025; Qiu et al., 2024; Steiner et al., 2025; Xu et al., 2026; Kim et al., 2026; Han et al., 2026)

---

## 8. 评审迭代历史

### 迭代 0 (未通过, weighted_score = 3.6)

| 维度 | 评分 |
|---|---|
| 文献覆盖度 | 2.0 |
| 技术可行性 | 3.0 |
| 创新性清晰度 | 4.0 |
| 数据可及性 | 4.0 |
| 缺口对齐度 | 4.0 |
| 评估严谨性 | 3.0 |

**文献缺口 (8 项)**:

- 缺少 scIB 基准原始论文 (Luecken et al., 2022)
- 缺少 OpenProblems 基准原始论文 (Luecken et al., 2021)
- 缺少 scGPT 模型原始论文 (Cui et al., 2024)
- 缺少 Geneformer 模型原始论文 (Theodoris et al., 2023)
- 缺少 scFoundation 模型原始论文 (Hao et al., 2024)
- 缺少 UCE 模型原始论文 (Rosen et al., 2023)
- 缺少 Goodhart 定律在 ML 评估中的讨论
- 缺少 Shapley 值在单细胞数据中的应用文献

---

### 迭代 1 (通过, weighted_score = 4.0)

| 维度 | 评分 | 变化 |
|---|---|---|
| 文献覆盖度 | 4.0 | +2.0 |
| 技术可行性 | 3.0 | — |
| 创新性清晰度 | 4.0 | — |
| 数据可及性 | 5.0 | +1.0 |
| 缺口对齐度 | 4.0 | — |
| 评估严谨性 | 3.0 | — |

**关键改进**:

1. 补充所有核心文献引用 (6 篇模型/基准原始论文)
2. 补充 Goodhart 定律 + Shapley 值应用文献
3. 为所有数据集添加具体 URL、许可信息和备选方案
4. 细化任务覆盖对比表 (scIB vs OpenProblems vs 本方案)
5. 补充引用验证和文献覆盖检查

**剩余文献缺口 (3 项)**:

- Goodhart 定律在单细胞基准评估中的实证文献
- 对抗性测试生成在生物信息学中的先例文献
- 自进化循环收敛性分析的相关方法文献

---

## 9. 参考文献

| 文献 | 引用角色 |
|---|---|
| Luecken et al., 2022 (Nature Methods) | scIB 基准 |
| Luecken et al., 2021 (NeurIPS) | OpenProblems 基准 |
| Cui et al., 2024 (Nature Methods) | scGPT 模型 |
| Theodoris et al., 2023 (Nature) | Geneformer 模型 |
| Hao et al., 2024 (bioRxiv) | scFoundation 模型 |
| Rosen et al., 2023 (bioRxiv) | UCE 模型 |
| Kedzierska et al., 2025 | 零样本评估方法 |
| Wenteler et al., 2025 | PertEval-scFM 扰动预测基准 |
| Wu et al., 2025 | 生物驱动评估标准 |
| Qiu et al., 2024 | BioLLM 统一框架 |
| Kim et al., 2026 | scUnify 统一框架 |
| Xu et al., 2026 | CellBench-LS 低监督基准 |
| Han et al., 2026 | 真实世界 RNA-seq 集成评估 |
| Manheim & Garrabrant, 2019 | Goodhart 定律 |
| Steiner et al., 2025 | 单细胞基础模型综述与基准 |

---

## 附录: 数据来源

本报告数据来源于以下文件:

- `data/p05_harness_output/harness_result.json` — 候选评分、迭代历史、研究计划
- `data/decompose_pilot_results.json` — 候选元信息
- `scripts/p05_harness/validators/rubric.py` — 6 维评分量表定义
- `scripts/p05_harness/config.yaml` — 评审循环参数

---

> 变更历史: v1 — 2026-07-22 — 基于 harness 评审数据生成初始研究报告
