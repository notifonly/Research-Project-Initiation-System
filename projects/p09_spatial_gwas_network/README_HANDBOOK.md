# P09 开题手册已迁移

P09 项目 (Archetype F: scGWAS × Spatial Transcriptomics Network Module Discovery) 的完整开题手册和 SpaceNetGWAS Python 原型包已迁移为独立工程性项目：

> **D:\program\SpaceNetGWAS\**

## 迁移内容

- **开题手册** (8 目录 22 文件): 研究背景、6 步技术方案、论文稿件、实验记录模板、数据清单、成果计划、结题报告
- **SpaceNetGWAS 原型包** (12 文件): 双权重空间模块搜索算法的完整 Python 实现，52 单元测试全部通过
- **独立项目基础设施**: pyproject.toml、.gitignore、data/results 目录

## AIscience 侧保留

以下 p09 相关文件保持在 AIscience 中不变：

| 位置 | 用途 |
|------|------|
| `projects/p09_spatial_gwas_network/config.yaml` | 项目配置 (seeded candidate) |
| `projects/p09_spatial_gwas_network/tool_flow.py` | Pipeline 入口 |
| `archetypes/archetype_f_spatial_gwas/` | Archetype F 原型定义 (evidence_card, gap_patterns) |
| `scripts/p09_harness/` | P09 Harness 评估框架 |
| `data/p09_harness_output/` | Harness 运行结果 |

## 快速入口

```bash
cd D:\program\SpaceNetGWAS
pip install -e ".[dev]"
pytest tests/ -v
python scripts/demo_run.py
```
