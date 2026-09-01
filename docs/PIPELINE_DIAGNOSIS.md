# Pipeline Diagnosis Guide

基于 p05_sc_multiomics_ai 完整排查过程提炼的跨项目诊断经验。

## 1. 流水线技能链路

```
S1(方向分解) → S2(术语规范化) → S3(资源收集) → S4(多源搜索) → S5(引用雪球)
  → S6(文献筛选) → [S6a(项目发散搜索)] → S7(证据卡片提取)
  → S8(数据可用性) → S9(方法数据集匹配)
  → [S10(功能证据搜索, 仅Archetype A)]
  → S11(缺口分析) → S12(假设生成)
```

每个技能的失败传播路径:
- S1/S2/S3 失败 → 整个项目失败 (无后续输入)
- S4 失败 → 该候选/topic 被放弃
- S5 失败 → 非阻塞, 优雅跳过
- S6 失败 (pass_rate=0) → 非阻塞, S7 回退到 S4 原始论文
- S7 失败 → 0张卡片, 但循环继续
- S8/S9 失败 → 非阻塞

## 2. 通用故障模式

### 2.1 S4: 搜索结果质量

**症状**: `quality_gate failed` (0篇论文), 或返回大量空标题/空摘要论文

**根因**:

| 根因 | 影响项目 | 修复位置 |
|------|----------|----------|
| PubMed 返回无 title/abstract 的记录 | p01-p03, p06-p07 | `skill_04_multi_source_search.py:91` |
| 候选驱动的查询过于特化 (全维度组合) | 仅 p05 | `loop_engine.py:411-431` (查询分解) |
| 子问题作为查询词 (50-150字完整句子) | p01-p04, p06-p07 | `loop_engine.py:828` (>80字过滤) |

**已修复**: 
- 空论文过滤: `deduped = [p for p in deduped if p.get("title") or p.get("abstract")]`
- 候选查询分解: 全组合query + 各维度单独query + S1 key_terms 安全网 (上限8个)
- 子问题长度过滤: `len(sq) <= 80`

**各项目空论文比例 (R0)**:
| 项目 | 空标题% | 空摘要% | 主要来源 |
|------|---------|---------|----------|
| p01 | 20% | 99% | PubMed |
| p02 | 25% | 99% | PubMed |
| p03 | **100%** | **100%** | PubMed (全部无效) |
| p04 | 0% | 80% | PubMed + Semantic Scholar |
| p05 | ~60% | ~99% | PubMed |
| p06 | 83% | 99% | PubMed |
| p07 | 85% | 99% | PubMed |

> **p03 最严重**: 86/86 篇论文全部空标题。过滤后仍 > 0 (质量门只检查 count) 但论文实际不可用。

### 2.2 S5: 引用雪球

**症状**: `quality_gate failed` 或 `'NoneType' object is not iterable` 崩溃

**根因**:

| 根因 | 影响项目 | 修复位置 |
|------|----------|----------|
| PMID 传入 Semantic Scholar API 未加 `PMID:` 前缀 | 全部 (PubMed为主源) | `skill_05_citation_snowball.py:140-150` |
| API 返回 `data: null` 时遍历崩溃 | 全部 | `skill_05_citation_snowball.py:71-72,104-105` |
| 种子论文在 S2 无反向引用 | 全部 (数据特性) | 无法修复 — 非代码问题 |

**已修复**: 
- PMID 识别 + `PMID:` 前缀: `re.match(r'^\d{1,12}$', seed)` → `f"PMID:{seed}"`
- None 防护: `items = resp.data.get("data"); if not items: return []`

**诊断**: S5 即使修复后仍常失败 (种子论文无引用)。这不是 bug — 许多 PubMed 论文在 Semantic Scholar 数据库中缺少引用关系。S5 失败是非阻塞的。

### 2.3 S6: 文献筛选 pass_rate=0

**症状**: 所有论文被 `keyword filter` 拒绝，`kept=0`

**根因**: `_tier1_keyword()` 使用 compound key_terms 做精确子串匹配。复合词很少以完整形式出现在论文中 — 例如论文写的是 `single-cell transcriptome` 而非 `single-cell multi-omics`。

**原始匹配逻辑** (`skill_06_literature_screening.py`):
```python
hits = sum(1 for k in inp.key_terms if k.lower() in text)  # 精确子串
score = hits / max(1, len(inp.key_terms))
keep = score >= 0.15 or hits >= 2
```
15 个复合 key_terms → 一篇相关论文通常只命中 1 个 → 拒绝。

**已修复**: `_expand_key_terms()` 方法将复合词拆为原子词:
- `"single-cell multi-omics"` → `["single-cell", "multi-omics"]`
- `"cross-task generalization"` → `["cross-task", "generalization"]`
- `"variant-to-gene (V2G)"` → `["variant-to-gene", "v2g"]`  (括号清理: `strip("()[]{}")`)
- 阈值调整为 `score >= 0.12 or hits >= 2` (适配展开后 ~25 词的扩大分母)

**各项目 key_terms 复合词比例**:
| Archetype | 项目 | 复合词% | 含括号 | S6 风险 |
|-----------|------|---------|--------|---------|
| A (V2G) | p01 | 70% | 是 | 高 |
| A (V2G) | p02 | 83% | 是 | **极高** |
| A (V2G) | p03 | 60% | 否 | 高 |
| B (PRS) | p04 | 44% | 否 | 低 (多单字方法名) |
| C (SC AI) | p05 | 45% | 否 | 中 (candidate_driven) |
| D (Omics) | p06 | 62% | 否 | 高 |
| D (Omics) | p07 | 44% | 否 | 中 |

### 2.4 S7: 证据卡片提取字段为空

**症状**: S7 quality_gate failed (`task`/`task_category` 全部 `None`), 或卡片字段全空

**根因 (仅 p05 自定义 S7)**: `llm_structured(list)` 隐式添加泛化的 "a JSON array" schema hint，覆盖了 prompt 中详细的字段要求。

**已修复** (`skill_07_scfm_card_extract.py`): 改用 `llm_complete` + `_parse_json` 直接调用，无 schema hint 覆盖。

**其他项目**: p01-p04, p06-p07 使用共享 `EvidenceCardExtract`，无自定义 quality_gate，不受此问题影响。

## 3. 各项目诊断要点

### p01 (GWAS + perturb-seq)
| 检查项 | 状态 | 说明 |
|--------|------|------|
| S4 空论文 | 20% 空标题 | 过滤修复覆盖 |
| S5 PMID 解析 | 需要 | 修复已覆盖 |
| S6 pass_rate | 风险高 | 70%复合词 + 括号 `(V2G)` |

### p02 (GWAS + spatial)
| 检查项 | 状态 | 说明 |
|--------|------|------|
| S6 pass_rate | **风险极高** | 83%复合词 + `(e.g., coloc, eCAVIAR...)` 括号 |

### p03 (GWAS + scATAC)
| 检查项 | 状态 | 说明 |
|--------|------|------|
| S4 空论文 | **100% 空标题** | 86/86 篇无效, 但过滤后 count 可能仍 >0 |
| 风险 | **严重** | 过滤后论文可能 0 篇 → S4 真正失败 |

### p04 (PRS advance)
| 检查项 | 状态 | 说明 |
|--------|------|------|
| S4 空论文 | 0% 空标题 | 唯一使用 Semantic Scholar 的项目 |
| S6 pass_rate | 风险低 | 多单字方法名 (LDpred2, PRS-CS) |
| 整体 | **最健康** | 搜索质量远高于其他项目 |

### p05 (SC multi-omics AI) — 本次排查对象
| 检查项 | 状态 | 说明 |
|--------|------|------|
| 收敛模式 | candidate_driven | 唯一使用候选驱动循环 |
| S4 查询 | 已修复 | 基于 decompose 候选的多级查询 + S4 缓存 |
| S5 引用 | 仍失败 | 非阻塞, 数据特性 |
| S7 提取 | 已修复 | llm_complete 替代 llm_structured, 字段正常 |

### p06 (Digital immune)
| 检查项 | 状态 | 说明 |
|--------|------|------|
| S4 空论文 | 83% 空标题 | 过滤修复覆盖 |
| S6 pass_rate | 风险高 | 62% 复合词 |

### p07 (Aging clock)
| 检查项 | 状态 | 说明 |
|--------|------|------|
| S4 空论文 | 85% 空标题 | 过滤修复覆盖 |
| S6 pass_rate | 风险中 | 44% 复合词 |

## 4. 复用策略

### 4.1 设计原则

1. **以字典当测试出发**: PubMed 的 empty-title 记录会污染 S4 输出 — 始终在 S4 执行后检查 title/abstract 是否为空
2. **ID 解析要完整**: 不同来源的 paper ID 格式不同 (PMID vs S2 ID) — 传递给 API 前确认前缀
3. **复合词需拆解**: 关键词匹配 (S6) 不能依赖精确子串 — 始终拆解为原子词 + 清理标点
4. **LLM structured 谨慎**: llm_structured() 的 schema hint 会覆盖 prompt 中的 field 要求 — 对复杂 schema 使用 llm_complete + 手动解析
5. **S5 失败是正常的**: 不要将 S5 quality_gate 视为 bug — 多数论文缺少引用关系
6. **PubMed 作为主源时要小心**: PubMed 返回的记录经常缺失内容 — 优先使用 Semantic Scholar (p04 的方案)

### 4.2 新项目/新方向诊断 checklist

运行新项目后检查:

- [ ] S4 `deduplicated_count > 0` 且 papers 中 title/abstract 非空比例 > 30%
- [ ] S5 无 NoneType 崩溃 (quality_gate failed 不算失败)
- [ ] S6 `pass_rate > 0` (如果=0, 检查 key_terms 是否过于复合)
- [ ] S7 `findings_count > 0` 且卡片关键字段非空 (如有自定义 S7)
- [ ] 每轮 `cards > 0` (=0 时排查 S4→S7 哪个环节断裂)
- [ ] 收敛条件合理: jaccard ~ 0.7-1.0, gap_ratio < 0.5, citation_closed

### 4.3 修复文件索引

| 文件 | 修改内容 | 影响范围 |
|------|----------|----------|
| `shared/skills/skill_04_multi_source_search.py:91` | 过滤空 title+abstract 论文 | 全部项目 |
| `shared/skills/skill_05_citation_snowball.py:71-72,104-105,140-150` | PMID→S2 ID 解析 + NoneType 防护 | 全部项目 |
| `shared/skills/skill_06_literature_screening.py:90-122` | _expand_key_terms 原子词展开 + 括号清理 + 阈值调整 | 全部项目 |
| `shared/core/loop_engine.py:411-431` | _build_candidate_queries 多级查询分解 | 仅 p05 |
| `shared/core/loop_engine.py:525-535,553,606-609` | S4 论文缓存 + 跨轮次保留 | 仅 p05 |
| `shared/core/loop_engine.py:828` | 子问题长度过滤 (>80字符跳过) | p01-p04, p06-p07 |
| `archetypes/archetype_c_sc_ai/skills/skill_07_scfm_card_extract.py` | llm_complete 替代 llm_structured | 仅 p05 |
