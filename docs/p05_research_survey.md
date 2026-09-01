# P05 单细胞多组学基础模型 — 调研文档 v1

> 项目ID: p05_sc_multiomics_ai | 原型: archetype_c_sc_ai | 调研日期: 2026-07-13

---

## 一、项目概览

### 1.1 研究方向

Survey and benchmark single-cell multi-omics foundation models (scVI, scGPT, Geneformer, scFoundation, UCE, MultiVI) for cross-task generalization. Identify gaps in multimodal integration (RNA+ATAC+protein), transfer learning evaluation, held-out cell-type generalization, and interpretability, and propose foundation-model training/evaluation improvements.

### 1.2 考察的六种基础模型

| 模型 | 架构 | 预训练规模 | 关键文献 |
|------|------|-----------|----------|
| scVI | VAE-based | ~1M cells | Lopez et al., 2018 |
| scGPT | Transformer | 33M cells | Cui et al., 2023 |
| Geneformer | Transformer | ~30M cells | Theodoris et al., 2023, Nature |
| scFoundation | Asymmetric Transformer | 50M cells, 100M params | Hao et al., 2024, Nat Methods |
| UCE | Contrastive | 多物种单细胞 | Rosen et al., 2023 |
| MultiVI | VAE-based multimodal | — | Ashuach et al., 2023 |

### 1.3 调研产出统计

| 指标 | 数值 |
|------|------|
| 证据卡片数 | 24 |
| 识别的研究空白 | 10 |
| 生成的假说 | 5 |
| Pipeline轮次 | 4轮（未收敛，因max_rounds停止） |
| Token消耗 | 38,091 / 5,000,000 |

---

## 二、核心研究问题（6个子问题）

1. 六种基础模型在跨任务泛化（细胞类型注释、扰动预测、基因调控网络推断）上的比较
2. RNA+ATAC+protein 多模态融合策略的局限与改进
3. 跨组织、跨物种、跨测序技术的迁移学习效能及影响因素
4. 对训练时未见细胞类型的泛化能力（held-out cell-type generalization）
5. 注意力权重、特征归因等可解释性方法在生物验证中的应用
6. 数据增强、对比学习、标准化benchmark等训练与评估改进方案

### 研究范围边界

- **包含**: 六种基础模型的调研和基准测试，聚焦多模态整合、迁移学习、held-out泛化、可解释性，提出训练/评估改进建议
- **排除**: 从零开发新模型、非列表模型的详细分析、临床转化应用、非单细胞组学、纯理论分析

---

## 三、识别到的疾病与数据资源（S1 key_terms）

### 涉及的7种疾病

| 疾病 | 数据集/来源 |
|------|------------|
| 结直肠癌 | GSE132465 (10 patients) |
| 黑色素瘤 | TCGA-SKCM (10 patients) |
| 阿尔茨海默病 | Banner Sun Health Research Institute (48 donors) |
| 2型糖尿病 | Human Pancreas Analysis Program (6 donors) |
| COVID-19 | COVID-19 Cell Atlas (12 donors, mild vs severe) |
| 系统性红斑狼疮 | ImmPort PBMC (8 donors) |
| 急性髓系白血病 | — |

### 涉及的7种组织

PBMC、胰腺、脑（前额叶皮质）、皮肤、肠道、肾脏、骨髓

---

## 四、10个研究空白（Gap Analysis）

| Gap ID | 名称 | 描述 | 涉及卡片 | 得分 | 可行性 |
|--------|------|------|----------|------|--------|
| **C4** | **弱基线对比** | 20/24 张卡缺少与 PCA/logistic 等简单基线的对比 | 20 | 0.61 | 0.75 |
| P3 | 覆盖率空缺 | 224个期望的axis组合未覆盖 | — | 0.85 | 0.60 |
| C3 | held-out评估缺失 | 23 张卡未评估未见细胞类型的泛化 | 23 | 0.63 | 0.65 |
| C2 | 标准化基准缺失 | 13 张卡缺乏标准化评估指标 | 13 | 0.63 | 0.80 |
| C9 | 可解释性缺失 | 20 张卡未进行可解释性分析 | 20 | 0.53 | 0.50 |
| C6 | 迁移学习评估缺失 | 10 张卡缺乏迁移学习评估 | 10 | 0.59 | 0.55 |
| C8 | 扩展性指标缺失 | 7 张卡缺少预训练规模指标 | 7 | 0.58 | 0.70 |
| P9 | 公共数据引用缺失 | 24 张卡未引用公共数据accession | 24 | 0.60 | 0.90 |
| P10 | 跨原型桥接 | PRS评分/基础模型融合未被探索 | — | 0.50 | 0.50 |
| C5 | 权重未公开 | 19 张卡预训练权重未发布 | 19 | 0.49 | 0.40 |

---

## 五、5个研究假说

### H1: 多物种多模态预训练在胰腺癌中的零样本注释

**核心**: 多物种、多模态预训练基础模型在胰腺癌免疫中的zero-shot细胞类型注释将超越Geneformer/scGPT

- 新颖性: 0.85 | 可行性: 0.65 | 影响: 高
- 需从头训练模型

### H2: held-out细胞类型+标准化指标的unified benchmark

**核心**: 纳入held-out评估和标准化指标后，Geneformer/scGPT在罕见细胞类型上不如PCA+LR

- 新颖性: 0.80 | 可行性: 0.70 | 影响: 中

### H3: 预训练规模与迁移学习的关系

**核心**: 预训练>10M细胞的基础模型才能在肾病分类中超越小模型

- 新颖性: 0.75 | 可行性: 0.60 | 影响: 高

### H4: 注意力权重基因模块 + PRS整合

**核心**: 结合注意力可解释性与多基因风险评分，桥接单细胞与群体遗传学

- 新颖性: 0.70 | 可行性: 0.50 | 影响: 中
- ~~PubMed检索到无关论文（体育/心理学等），需优化关键词~~

### H5: 基础模型 vs 简单基线系统性基准测试 ⭐ 推荐

**核心**: 在20+任务上系统比较FM与PCA/LR基线，揭示何时基础模型真正必要

- 新颖性: 0.80 | 可行性: 0.75 | 影响: 高
- **推荐优先推进**：不需从头训练模型，公开数据+预训练权重可获取

---

## 六、H5 详细研究方案（推荐开题方向）

### 6.1 研究定位与差异化

| 已有工作 | 做了什么 | 没做什么 |
|----------|---------|---------|
| scFoundation (Hao et al., 2024, Nat Methods) | 证明scFoundation SOTA | 无简单基线对比，无成本分析 |
| BioLLM (Hu et al., 2025, Patterns) | 统一FM评估框架 | FM vs FM，无简单基线对比 |
| scDrugMap (Wang et al., 2025, Nat Commun) | 药物响应FM benchmark | 仅药物响应，非跨任务 |
| Csendes et al. (2025, BMC Genomics) | 发现简单基线可超越FM | 仅2FM、1任务类型 |

**H5独特贡献**: 第一个系统性回答"何时简单方法就足够"的研究，提供决策框架而非又一轮性能排序。

### 6.2 核心研究问题

> 对于单细胞组学中的细胞注释、批次校正、扰动预测等任务，在什么样的任务难度、样本规模和数据特征下，简单方法（PCA+LR、自编码器、scVI）已足够——从而可以省去基础模型的高昂计算成本？

### 6.3 核心假说

1. **难度依赖假说**: 常见细胞类型、大样本量、单一组织来源的任务上，PCA+LR或scVI与FM无显著差异
2. **成本-效益假说**: TDI低于某阈值时，FM的计算/碳排放成本远超性能增益
3. **惊取代价假说**: FM仅在罕见细胞类型(<1%)和跨物种zero-shot任务中有不可替代价值

### 6.4 实验框架：四层方法阶梯

```
Level 0（零基线）:   均值预测 / 多数类投票
Level 1（经典基线）: PCA(50/100/200d) + LogisticRegression / RandomForest
Level 2（专用基线）: Autoencoder(SDAE) + MLP, scVI + scANVI
Level 3（基础模型）: Geneformer, scGPT, scFoundation, UCE (zero-shot + fine-tune)
```

### 6.5 任务难度指数（TDI）

```
TDI = w1 × (1 - cell_type_abundance) + w2 × (1 - sample_size_norm)
    + w3 × cross_species_bool + w4 × tissue_heterogeneity
```

权重通过弹性网回归从实验数据中学习。

### 6.6 数据集设计（8数据集 × 5样本量 × 6任务类型）

| 数据集 | 疾病 | 组织 | 关键细胞类型 |
|--------|------|------|-------------|
| Tabula Sapiens | 健康参考 | 多组织(24) | 常见+罕见 |
| GSE132465 | 结直肠癌 | 肠道 | 上皮/间质/免疫 |
| TCGA-SKCM | 黑色素瘤 | 皮肤 | T细胞/基质 |
| Alzheimer Banner | AD | 脑(前额叶) | 神经元/小胶质 |
| HPAP | T2糖尿病 | 胰腺 | α/β/δ细胞 |
| COVID-19 Cell Atlas | COVID-19 | PBMC/肺 | T/B/单核 |
| SLE ImmPort | 红斑狼疮 | PBMC | B/T/DC |
| Nephrobase | 肾病 | 肾脏 | 足细胞/近端小管 |

### 6.7 评估体系

**性能指标**:

| 任务 | 指标 |
|------|------|
| 细胞注释 | Macro F1, Weighted F1, Cohen's κ |
| 批次校正 | batchASW, kBET, graph connectivity, iLISI |
| 扰动预测 | Spearman ρ, AUROC (Top-K) |
| 嵌入评估 | NMI, ARI, silhouette score |

**成本指标**（核心创新）:

| 指标 | 计算方式 |
|------|---------|
| GPU时间 | wall-clock × GPU数 |
| 碳排放 | codecarbon实测CO₂e |
| 效率指数(EI) | ΔF1 / (log₁₀(e) × t) |

**统计检验**:

- 配对 Wilcoxon signed-rank test + Bonferroni校正
- 混合效应模型: ΔF1 ~ model + log(n_cells) + rarity + cross_species + (1|dataset)
- Bootstrap 95% CI (1000次) + Permutation testing (n=10000)

### 6.8 论文框架预设计

```
Title: "Minimum Sufficiency in Single-Cell Foundation Models:
        When Simple Baselines Are Enough"

Figure 1: 方法概览
Figure 2: 主对比热图 (数据集×任务×方法)
Figure 3: 难度-增益曲线 (TDI vs ΔF1)
Figure 4: 成本-效益散点图 (碳排放 vs F1)
Figure 5: 样本量-性能曲线 (50→5000 cells)
Figure 6: 临床决策树 (输出最小充分方法推荐)

Discussion: FM在罕见细胞类型和跨物种任务中不可替代；
           简单基线合理使用是科学rigor而非能力不足；
           反对在不必要场景中过度使用复杂模型
```

### 6.9 时间线（12周）

| 周 | 阶段 | 产出 |
|----|------|------|
| W1-2 | 数据统一化 | 8个AnnData，标准化gene symbol，TDI标注 |
| W3-4 | 基线实现 | Level 0-2全pipeline，统一5-fold评估器 |
| W5-7 | FM基准测试 | 加载4个FM权重，zero-shot + fine-tune |
| W8-9 | 统计分析 | 混合效应模型，TDI拟合，效率指数计算 |
| W10 | 决策树构建 | 训练/验证/测试，与BioLLM对齐 |
| W11-12 | 论文撰写 | draft，代码整理，补充实验 |

### 6.10 风险管理

| 风险 | 缓解 |
|------|------|
| scFoundation权重未公开 | 已有 `clinicalml/sc-foundation-eval` 仓库确认 |
| BioLLM覆盖了部分对比 | 差异化：BioLLM是FM vs FM，H5是FM vs 简单基线 + 决策框架 |
| 简单基线性能太差（假说不成立） | Csendes 2025已证实均值可超越FM；结果正反都有发表价值 |
| 跨数据集batch effect干扰 | 每个数据集独立评估 + scVI预处理 sensitivity analysis |

### 6.11 预期贡献

1. **科学贡献**: 首次系统性验证单细胞FM的"最小充分性原则"，填补C4空白
2. **方法贡献**: TDI + EI评分体系可被后续benchmark工作复用
3. **实践贡献**: 决策树工具可直接服务研究者选择方法
4. **发表潜力**: Nature Methods / Genome Biology / Cell Systems（benchmark/resource类型）

---

## 七、关键文献索引

| 文献 | 期刊 | 年份 | PMID | 与本方向关系 |
|------|------|------|------|-------------|
| Transfer learning enables predictions in network biology (Geneformer) | Nature | 2023 | 37258680 | Geneformer原始论文 |
| Discovery of candidate therapeutic targets with Geneformer | Nat Protocols | 2026 | 42026145 | Geneformer使用方法 |
| Large-scale foundation model on single-cell transcriptomics (scFoundation) | Nat Methods | 2024 | 38844628 | scFoundation原始论文 |
| Methods and applications for single-cell and spatial multi-omics | Nat Rev Genet | 2023 | 36864178 | 多组学方法综述 |
| Benchmarking foundation cell models for post-perturbation RNA-seq | BMC Genomics | 2025 | 40269681 | 发现简单基线可超越FM |
| BioLLM: standardized framework for benchmarking scFMs | Patterns | 2025 | 40843339 | 清华FM评估框架 |
| scDrugMap: benchmarking large FMs for drug response | Nat Commun | 2025 | 41381537 | 药物响应FM benchmark |
| Spatially resolved multi-omics in pancreatic cancer | Gastroenterology | 2023 | 37263303 | 胰腺癌多组学数据 |
| RegFormer: scFM powered by gene regulatory hierarchies | Nat Commun | 2026 | 42086551 | 最新FM方法 |

---

## 八、与老师汇报建议

### 30秒版本

> "我对P05感兴趣——单细胞多组学基础模型的benchmark。P05系统调研发现83%的文献没有和简单基线做对比，这是个严重的系统性空白。我的计划是在8个数据集、6类任务上，用4层方法阶梯系统回答'基础模型到底什么时候真正必要'。不需要从头训练模型，12周可完成，有明确的发表空间。"

### 3分钟版本

1. **研究空白**: 20/24论文无基线对比（C4 gap），已有工作（BioLLM/scFoundation/scDrugMap）都在做FM vs FM的性能排序，没有人系统回答"什么时候不需要FM"
2. **研究设计**: 8数据集 × 5样本量 × 6任务类型 × 4方法层级 = 完整矩阵；引入TDI难度指数和EI效率指数
3. **差异化**: 不是又一个benchmark，是决策框架——产出可被湿实验生物学家使用的"方法选择决策树"
4. **发表定位**: Nature Methods / Genome Biology / Cell Systems 的 benchmark/resource 类型
5. **可行性**: 数据公开（GEO/TCGA/HCA），代码已有（scvi-tools, HuggingFace），P05已确认预训练权重可获取

---

## 九、后续待办

- [ ] 确认 scFoundation 预训练权重获取路径（`clinicalml/sc-foundation-eval` / `Jpickard1/scFoundationModels`）
- [ ] 下载 8 个目标数据集并验证数据完整性和细胞类型标注质量
- [ ] 确认与清华 BioLLM 框架的技术对接方式
- [ ] 撰写文献综述初稿，明确与已有 benchmark 工作的关系
- [ ] 与老师汇报后确定具体的优先假说方向

---

*生成时间: 2026-07-14 | 基于 P05 4轮pipeline完整运行结果*
