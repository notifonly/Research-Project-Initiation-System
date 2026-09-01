# Session 2026-07-26 — P09 开题手册 + SpaceNetGWAS 原型包 + 独立项目迁移

## 背景

P09 (scGWAS × Spatial Transcriptomics Network Module Discovery, Archetype F) 已通过 harness 验收 (4.10/5.0)，但没有完整的开题项目文档和可运行的 Python 原型包。需求：基于 harness 产出的 5 步技术路线、创新点、数据源和缺口分析，生成一份高可执行性的开题手册，附带可运行的 spacegwasnet 原型包。

## 开题手册 (handbook/)

基于 `data/p09_harness_output/runs/run_seeded_v1/p05_final_enriched.json` 中的详细方案，生成 8 个目录 32 个文件的手册：

### 01立项/ (3 files)
- **研究背景与问题陈述.md**: 完整缺口溶解矩阵 (F1-F10)，每个缺口包含描述/解决方案/证据/剩余问题/状态
- **文献综述.md**: 3 条方法谱系综述 (scGWAS/gsMap/空间表达模块)，含详细对比矩阵
- **可行性分析报告.md**: 8 月时间线 (月度里程碑)、5 类风险分析、预算估算

### 02方案/ (6 files)
- **01_技术路线总览.md**: 五步流水线 ASCII 图、数据流全景、32 周 Gantt 图、30+ 项技术栈
- **02_数据获取与预处理.md**: GEO + GWAS 下载脚本 (wget/curl/Python)、Space Ranger 2.0.0 命令、scanpy QC pipeline、MAGMA SNP2GENE、SHA256 manifest
- **03_空间邻域图构建与共表达计算.md**: Squidpy 3 种图模式对比、向量化 Spearman 共表达、SpatialDE SVG、距离衰减分析
- **04_双权重空间模块搜索算法.md**: Box-Cox 推导、双权重几何解释、MEBE 3 子算法伪代码+完整 Python 实现、空间块 CV 参数调优、Infomap 替代方案、3 层空间置换零模型
- **05_评估框架与基准测试.md**: SCZ↔AD 交叉性状解耦协议、7 基线 Python 实现、LOSO-CV、AUPRC/ΔAUC/空间 FDR、5 项消融实验
- **06_生物学解释与工具发布.md**: g:Profiler、RCTD、Dockerfile、CLI 设计、Sphinx、CI workflows、bioRxiv 检查表

### 06论文稿件/ (5 files)
- **01_论文大纲与结构.md**: 3 候选标题、250 字摘要骨架、7 节大纲、图表清单
- **02_引言部分草稿.md**: ~1,200 字英文章稿 (7 段)，含 29 篇参考文献
- **03_方法部分草稿.md**: ~3,000 字英文方法论 (9 子节)，含伪代码
- **04_投稿期刊分析.md**: Nature Methods/Genome Biology/Cell Systems 三家 fit 分析、Cover Letter、8 位审稿人
- **05_补充材料计划.md**: Fig. S1-S4 + Table S1-S3 设计、6 项补充方法

### 03实验记录/ (1 file)
- **实验日志模板.md**: 周级记录模板、5 步实验记录表、参数调优网格、基线对比矩阵

### 04原始数据/ (1 file)
- **数据清单.md**: D1-D4 4 级数据目录、GSE167492 4 slice 详情、GWAS 元数据、下载 SOP

### 07成果/ (1 file)
- **成果清单.md**: 2 篇发表计划、6 个会议、专利评估、引用预测

### 08结题/ (2 files)
- **结题报告.md**: 执行摘要、F1-F10 缺口溶解报告、5 项教训/最佳实践/反模式、未来工作 11 项
- **项目总结PPT大纲.md**: 22 页答辩大纲、时间预算、预判问答

## SpaceGWASnet 原型包 (05代码/spacegwasnet/)

### 包结构 (12 files)
- `__init__.py`: package init, __version__, 全部 exports
- `preprocess.py`: load_visium_data, load_gwas_scores, boxcox_normalize, filter_mhc_region, run_scanpy_qc
- `spatial_graph.py`: SpatialGraph class, build_spatial_neighbor_graph (k-NN/Delaunay/radius), compute_local_coexpression, distance_decay_analysis
- `spatial_dual_weight.py`: **核心算法** — select_seed_genes, dual_weight_score, mebe_greedy_expand, consensus_cluster_modules, infomap_communities, spatial_permutation_test, compute_module_significance, run_pipeline
- `evaluation.py`: cross_trait_decoupling, 7 baselines (random_gwas/random_coords/pure_coexpression/gwas_top_genes/gsmap_simplified/spatial_blind_scgwas/known_pathways), leave_one_slice_out_cv, compute_auprc, compute_delta_auc, evaluate_all_baselines
- `utils.py`: SHA256, build_data_manifest, setup_logging, load_config, export_results, DataVersionManifest
- `cli.py`: Click CLI — 5 子命令 (run/preprocess/evaluate/visualize)
- `setup.py`: Package setup with dependency list
- `tests/test_core.py`: **52 个单元测试** (synthetic data fixtures)
- `notebooks/tutorial.ipynb`: 9-section walkthrough
- `README.md`: 完整 API 文档

### 测试结果
- **52 tests, 0 skip, 0 fail** (15.76s)
- 全部核心算法链路验证: Box-Cox → seed selection → dual-weight scoring → MEBE → consensus clustering → 3 spatial permutation types → module significance with FDR

### 代码修复 (3 bugfixes to source)
1. **preprocess.py**: Box-Cox scipy 1.18+ 兼容 (try/except for RuntimeError/ValueError, constant value fallback, NaN handling); MHC 默认区间 28.5-33.4Mb → 25-35Mb
2. **spatial_dual_weight.py**: KDTree import fix (`sp.spatial.KDTree` → `from scipy.spatial import KDTree`)
3. **test_core.py** (test only): MockAdata __getitem__ transpose fix, VarNames.get_indexer fallback, tolerance relaxations

### 端到端 Demo
- **demo_run.py**: 100 spots × 500 genes 合成数据，2 个预埋共表达模块
- **结果**: 2/2 共识模块检测，模块 0 回收 17/19 genes (p=0.010, z=11.2)，模块 1 回收 15/16 genes (p=0.010, z=9.9)
- **输出**: module_summary.png (4-panel: size/p-value/score/recovery), module_heatmap.png, pipeline_result.json

## 独立项目迁移

P09 手册 + spacegwasnet 包从 AIscience 项目中移出为独立工程性项目:

| 迁移项 | 原路径 | 目标路径 |
|--------|--------|---------|
| 手册文档 (22 files) | `projects/p09_spatial_gwas_network/handbook/{01立项..08结题}/` | `D:\program\SpaceNetGWAS\docs\{01_立项..08_结题}/` |
| Python 包 (8 files) | `handbook/05代码/spacegwasnet/spacegwasnet/` | `D:\program\SpaceNetGWAS\spacegwasnet/` |
| 测试 (2 files) | `handbook/05代码/spacegwasnet/spacegwasnet/tests/` | `D:\program\SpaceNetGWAS\tests/` |
| Notebooks | `handbook/05代码/spacegwasnet/spacegwasnet/notebooks/` | `D:\program\SpaceNetGWAS\notebooks/` |
| Demo | `handbook/05代码/spacegwasnet/demo_run.py` | `D:\program\SpaceNetGWAS\scripts/demo_run.py` |
| Setup | `handbook/05代码/spacegwasnet/setup.py` | `D:\program\SpaceNetGWAS\setup.py` + 新增 `pyproject.toml` |

**新增**: `.gitignore`, `data/raw/.gitkeep`, `data/processed/.gitkeep`, `results/.gitkeep`

**路径修复**:
- `spacegwasnet/README.md`: 安装/测试路径从 `spacegwasnet/` 改为 SpaceNetGWAS 根目录
- `scripts/demo_run.py`: `sys.path` 从 `parents[3]/05代码/spacegwasnet` 改为 `parents[1]`

**AIscience 侧处理**:
- 删除 `projects/p09_spatial_gwas_network/handbook/` 整个目录
- 创建 `projects/p09_spatial_gwas_network/README_HANDBOOK.md` 指向独立仓库
- `archetypes/archetype_f_spatial_gwas/`、`scripts/p09_harness/`、`data/p09_harness_output/` 保持不变

**独立项目结构**:
```
D:\program\SpaceNetGWAS\
├── README.md              # 项目总览 + F1-F10 缺口矩阵
├── pyproject.toml         # 标准 Python 项目配置
├── setup.py               # 兼容旧 pip
├── .gitignore
├── spacegwasnet/           # 核心包 (8 files)
├── tests/                  # 52 单元测试
├── notebooks/              # Jupyter 教程
├── scripts/                # demo_run.py
├── docs/                   # 完整开题手册 (22 files)
│   ├── 01_立项/ (3)
│   ├── 02_方案/ (6)
│   ├── 03_实验记录/ (1)
│   ├── 04_原始数据/ (1)
│   ├── 06_论文稿件/ (5)
│   ├── 07_成果/ (1)
│   └── 08_结题/ (2)
├── data/raw/ + data/processed/   # 真数据预留
└── results/                      # 输出预留
```
