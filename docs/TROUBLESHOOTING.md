# Troubleshooting Guide

Quick-reference mapping of common symptoms, root causes, and fixes from real debugging sessions.

## 0 cards, 0 gaps, 0 hypotheses (total pipeline failure)

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| All 0, logs show `AuthenticationError` | LLM API key not configured | Create `.env` with `AISCIENCE_LLM_API_KEY`, `AISCIENCE_LLM_BASE_URL`, `AISCIENCE_LLM_MODEL` |
| All 0, LLM works but s4 `quality_gate failed` instantly | `inp.queries` is empty → scoping→inner data flow broken | `_run_scoping()` must return enriched `SkillInput`; `run()` must pass it to `_run_inner_loop()` |
| s4 returns papers, s7 runs but returns 0 cards | `_parse_json` doesn't handle JSON arrays `[...]` | Rewrite `_parse_json` to find `[`...`]` and handle truncated arrays |
| s4 returns papers, s7 runs, cards produced but not collected | L2 key mismatch: synthesis stores/receives under wrong keys | Ensure `warm_to_l2("identified_gaps", ...)` and `warm_to_l2("hypotheses", ...)` match retrieval keys |

## quality_gate failed (per-skill)

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| s4: `quality_gate failed` in <1s | `inp.queries` is empty list → no search tasks created | Ensure `key_terms`/`sub_questions`/`normalized_traits` flow from scoping via `_prepare_skill_input` |
| s4: `quality_gate failed` after API calls | All MCP sources returned 0 papers | Check MCP API keys (semantic_scholar); check queries are meaningful |
| s5: `pre_check failed: no seed papers` | s4 returned 0 papers (upstream failure) | Fix s4 first |
| s5: `quality_gate failed` with `NoneType` error | API returns null for `externalIds` or `authors` | Use `(paper.get("externalIds") or {}).get("DOI")` pattern |
| s1: `quality_gate failed` | LLM returned stub response (no API key or API error) | Check `.env` LLM configuration |

## Validation error for Evidence Card

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `raw_data_accession`: string_type, got `[]` (list) | LLM returned list for string field | Coerce: `_coerce_opt_str()` handles list→join, None→None |
| `method_brief`: string_type, got `None` | LLM returned null for required string | Coerce: `_coerce_str()` handles None→"", list→join |
| `trait_label`: string_type, got `['...']` (list) | LLM returned list for Optional[string] | Coerce: `_coerce_opt_str()` handles list→join |
| `pos` / `sample_size`: int_type, got `"12345"` (str) | LLM returned string for int field | Coerce: `_coerce_int()` handles str→int |
| `p_value` / `effect_size_beta`: float_type, got `"0.05"` (str) | LLM returned string for float field | Coerce: `_coerce_float()` handles str→float |
| `source_type`: unexpected value "literature" | Literal type only accepts `"paper"`, `"database"`, etc. | Use exact Literal value: `"paper"` not `"literature"` |
| `limitations`: field not found | Schema uses `limitation_explicit`/`limitation_implicit`, not `limitations` | Match field names exactly to schema |
| `extracted_at`: string_type mismatch | Field is `str` (ISO datetime), passing `time.time()` float | Use default `utc_now_iso()` or pass ISO string |

## Timeout / Performance

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Skill s7 times out at 120s | Sequential LLM calls per paper (e.g. 200 papers × 30s each) | Parallelize with `asyncio.gather(*tasks, return_exceptions=True)`; cap targets to 5 |
| s4 takes very long | Many MCP sources queried sequentially | MCP calls are already parallel within s4; check API latency |
| Full run >10 min per project | Many LLM calls across 12 skills × 3 rounds | Expected baseline ~500-800s per project; 7 projects run in parallel |

## MCP / External API

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| PubMed papers have no title/abstract | `esearch` returns only PMIDs; need `esummary` + `efetch` | Chain `esearch` → `esummary` (title/authors) → `efetch` (abstracts) |
| `resp.json()` throws on text response | MCP endpoint returns plain text, not JSON | Fallback: try `resp.json()`, on failure use `resp.text` |
| `abstract: null` in Semantic Scholar response | API returns null for missing fields | Use `p.get("abstract") or ""` not `p.get("abstract", "")` |
| s5 `'NoneType' object is not iterable` | API returns null for list fields (authors, externalIds) | Use `(paper.get("authors") or [])` pattern |

## LLM / JSON Parsing

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `_parse_error: True` in output | `_parse_json` couldn't parse LLM response | Check: (1) JSON array handling, (2) truncated JSON, (3) markdown code blocks |
| LLM returns `{"findings": [...]}` but code expects `[...]` | Dict-wrapped list fallback not implemented | After `llm_structured(list)`, check: `if isinstance(result, dict): for v in result.values(): if isinstance(v, list): result = v` |
| LLM output truncated mid-JSON | `max_tokens=4096` too small for evidence cards | Set `AISCIENCE_LLM_MAX_TOKENS=8192` in `.env` |
| Truncated JSON array missing `]` | LLM hit token limit mid-array | `_parse_json` should attempt `json.loads(raw + "]")` after stripping trailing comma |
| `json.JSONDecodeError` on LLM response | LLM returns markdown code block (` ```json\n{...}\n``` `) | Strip code fences before parsing: check for ``` prefix, remove all lines that are just ``` |
| JSON array wrapped in dict `{"key": [...]}` | LLM added extra wrapping layer | `if isinstance(result, dict): for v in result.values(): if isinstance(v, list): result = v` |

## PubMed / Decomposition

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| PubMed search returns 0 for domain-specific queries | Query too specific (15+ words: `"type 2 diabetes GWAS fine-mapping SuSiE eQTL colocalization CD4+ T cells perturb-seq"`) | Use broad queries: `{disease} {method_short}` (2-7 words). Add tissue keyword as secondary query. |
| All candidates from same disease (no diversity) | Nested-loop iteration: `disease × tissue × method × pop` fills first disease before rotating | Round-robin or hash-interleave dimensions when generating candidate combos |
| All candidates have identical scores | Literature search uses only disease name → all return same count (e.g. 187k for "Rheumatoid arthritis") | Include tissue keyword + method keyword in search query to differentiate counts |
| `decompose_directions.py` fails: `FileNotFoundError: config.yaml` | Short project ID (`p01`) passed instead of full ID (`p01_gwas_perturb_seq`) | Add `resolve_project_id()` that scans `projects/` directory for matching prefixes |
| `UnicodeEncodeError` in Windows console | GBK codec cannot encode emoji/dashes (—, 🧬) used in output | Use `_safe_print()` that falls back to `.encode("ascii", errors="replace")` |

## Infrastructure

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Log lines printed twice | Dual log handler registered | Check `logging_setup.py` for duplicate handler registration |
| `--only p01` returns 0 projects | Project key is full name `p01_gwas_perturb_seq`, not `p01` | Use `--only p01_gwas_perturb_seq` (or fix CLI to accept short names) |
| `CardStore.all_rows()` returns empty after restart | LanceDB connected but no table → fallback JSONL not loaded | Check `_load_fallback` condition: use `if self._table is None` not `if self._db is None` |
| Cards not persisted across runs | CardStore fallback never loads | Same as above; also check `data/l0_cold/` and `data/l1_warm/` paths |

## Debugging Workflow

1. **Check LLM first**: Run `python -c "import asyncio; from shared.core.llm_client import llm_complete; print(asyncio.run(llm_complete('reply PONG')))"` — should print `PONG`
2. **Check single project**: `python main.py --only p01_gwas_perturb_seq` (use full project key)
3. **Check per-skill logs**: Search logs for `quality_gate failed`, `ERROR`, `validation error`, `AuthenticationError`
4. **Check L2 context**: Add debug logging in `_run_synthesis` to inspect `prev_outputs` keys
5. **Check _parse_json**: If cards=0 but s7 LLM calls succeed, inspect raw LLM output format

## Dashboard HTML 不显示内容

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| 页面空白，console: `SyntaxError: Identifier 'INLINE_DATA' has already been declared` | `index.html` 模板引用了 `inline_data.js`，`build_data.py` 又注入了一份内联脚本，导致 `const INLINE_DATA` 重复声明 | `index.html` 是构建模板，**不要**添加 `<script src="inline_data.js">`；`build_data.py` 会自动注入到 `index_standalone.html` |
| 页面空白，console: `ReferenceError: Cannot access 'TABS' before initialization` | `loadData()` 同步调用 `init()` → 访问同文件下方 `const TABS`，但 `const` 存在 TDZ（暂时性死区） | 将 `loadData();` 改为 `setTimeout(loadData, 0);`，延迟到所有 `const` 声明完成后执行 |
| 页面空白，无 console 错误，fetch 静默失败 | `file://` 协议下 `fetch('data.json')` 被浏览器 CORS 阻止 | 本地打开必须用 `index_standalone.html`（内联数据），不能直接打开 `index.html` |
| 页面空白，`INLINE_DATA` is undefined | `build_data.py` 将内联脚本插入在 `</body>` 前（主脚本之后），`loadData()` 同步执行时尚未定义 | 修改 `build_data.py`：将内联脚本插入到主 `<script>` 块**之前**，而非 `</body>` 之前 |
| `ReferenceError: XxxTab is not defined` in standalone HTML | New JS tab file (`js/tabs/Xxx.js`) created but not added to `_build_standalone_html()` `js_files` list | Add new file to `js_files` list in `build_data.py` (between existing tabs and `app.js`), then re-run `python dashboard/build_data.py` |
| New dashboard tab present in `index.html` but missing in `index_standalone.html` | `index.html` (modular) loads scripts from `<script src>` tags; `index_standalone.html` (self-contained) inlines them via `js_files` list in `_build_standalone_html()` | Always update both: (1) `<script src>` in `index.html`, (2) `js_files` list in `build_data.py`, (3) TABS + renderTab in `app.js` |

## Wrong archetype card schema (cards labeled "v2g" but project is sc_fm/omics_score)

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| p05/p06/p07 cards have `"archetype": "v2g"` and v2g-specific fields | S7 `EvidenceCardExtractInput.archetype` default was `"v2g"`; loop_engine only set archetype when `data.get("archetype")` was falsy (never triggered for p05-p07) | Removed hardcoded default (`archetype: str = ""`); loop_engine always sets archetype from `evidence_card_class.model_fields["archetype"].default` |
| Existing data still has wrong schema | Fix only applies to future runs; historical data unchanged | Run `python scripts/rerun_p05_p06_p07.py` to convert cards and regenerate gaps/hypotheses |

## Empty coverage_map.json (all projects return [])

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| All 7 `coverage_map.json` files are `[]` | Coverage matrix cells were tracked but never populated during pipeline run | Run `python scripts/generate_coverage_maps.py` (zero LLM, reads evidence_cards.jsonl) |
| p05/p06/p07 coverage maps have few cells (<10) | Cards use wrong archetype schema → coverage axes mismatch | Fix card schema first (above), then regenerate coverage maps |

## Pipeline progress shows <50% (e.g. 38%) when pipeline fully completed

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Dashboard 管线进度百分比远低于实际（如 38%），但所有卡片/缺口/假设均已生成 | `compute_pipeline_progress()` 仅在 checkpoints 目录中按 skill ID 精确匹配；内循环技能 (S4-S10) 没有独立 checkpoint 文件，仅有聚合的 `rN_inner_loop.json`，因此被永远标记为 incomplete | 在 `compute_pipeline_progress()` 中增加 `*inner_loop*` checkpoint 检测：若存在任何 inner_loop checkpoint 文件，则将 S3-S10（含 s6a/s6b）标记为已完成 |
| 某个项目进度明显低于其他项目 | 该项目的 `data/l1_warm/{pid}/checkpoints/` 目录缺少 inner_loop checkpoint（可能是早期中断或仅运行了部分阶段） | 检查 checkpoint 目录完整性：应至少包含 `r0_s1_*`, `r0_s2_*`, `r0_s3_*`, `r0_inner_loop.json`, `r0_s11_*`, `r0_s12_*`；若 S11/S12 已产出 gaps/hypotheses 但无 inner_loop checkpoint，运行 `python scripts/generate_coverage_maps.py` 后重新 `build_data.py` |

**Checkpoint 目录参考结构：**
```
data/l1_warm/{pid}/checkpoints/
  r0_s1_direction_decompose.json    ← 独立 scoping checkpoint
  r0_s2_terminology_normalize.json  ← 独立 scoping checkpoint
  r0_s3_v2g_locus_collect.json      ← 独立 scoping checkpoint
  r0_inner_loop.json                ← 聚合内循环 (S4-S10) checkpoint
  r0_s11_gap_analysis.json          ← 独立 synthesis checkpoint
  r0_s12_hypothesis_generate.json   ← 独立 synthesis checkpoint
  r1_inner_loop.json                ← 第二轮
  ...
```

## S11 gap analysis only returns P9/P10 for sc_fm/omics_score projects

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| p05-p07 gaps are only P9 (public data) and P10 (cross-archetype bridge) | `_has_v2g_fields()` / `_has_prs_fields()` are the only archetype detectors; no sc_fm or omics_score blocks existed | Add `_has_sc_fm_fields()` / `_has_omics_score_fields()` (check `c.archetype` string); add C1-C10 and D1-D10 gap analysis blocks |
| Detection fails even after schema fix | Converted cards have all fields None → detection by field value fails | Always use `c.archetype` string for detection, not field values |

## LSP/IDE Type Check Warnings (NOT runtime errors)

These warnings appear in VS Code / Pyright / Pylance but do **NOT** affect runtime behavior:

```
Method "execute" overrides class "BaseSkill" in an incompatible manner
  Parameter 2 type mismatch: base parameter is type "SkillInput",
  override parameter is type "DirectionDecomposeInput"
    "SkillInput" is not assignable to "DirectionDecomposeInput"
```

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Pyright/Pylance reports `Method "execute" overrides class "BaseSkill" in an incompatible manner` on every Skill subclass | Python duck-typing allows covariant parameter narrowing in method overrides; Pydantic validates at runtime. All skills in this project (s1–s12) use this pattern (`MySkill.execute(inp: ConcreteInput)`) — it is deliberate and correct. Static type checkers flag it because they enforce Liskov substitution contravariance, but this is a known limitation of Python type checking, not a bug. | **No fix needed.** These warnings are cosmetic. `python main.py` runs without errors. If desired, suppress per-file: add `# pyright: ignore[reportIncompatibleMethodOverride]` at the top of the skill file. |

## P05 Harness Dashboard 数据异常

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| P05 方案质量 tab 统计指标全为 0（LLM 调用 0 / MCP 调用 0 / 耗时 0.0 min），但 run 实际有统计 | `build_data.py` `_aggregate_harness_runs()` 从 `checkpoint.json` 读**文件级** `total_llm_calls`/`total_mcp_calls`/`total_duration_s`，但 `loop_runner._append_checkpoint()` 写的 checkpoint 只有 `{"candidates": [...]}`，统计字段在**每个 candidate 记录内**（`total_llm_calls`/`total_mcp_calls`/`duration_s`） | 聚合时对去重后的 `all_candidates` 按 candidate 求和（与 `scripts/p05_harness/main.py` `merge_runs()` 语义对齐）；验证方法：per-candidate 求和应与 run 目录下 `harness_result.json` 文件级统计一致 |
| 某个方向的验收结果在 tab 上完全不可见（如 agent 方向） | 分方向/分批次多次运行 harness 后未执行 `--merge`，`data/p05_harness_output/latest_run.txt` 只含最后一个 run；dashboard 只聚合 latest_run.txt 列出的 run | `python scripts/p05_harness/main.py --merge run1,run2`（按 candidate_id 去重，重写顶层 `harness_result.json` 和 `latest_run.txt`，无需 API key），然后 `python dashboard/build_data.py` 重建。**教训：harness 每次新增方向的 run 后应立即 merge** |

## 开发环境 / MCP 工具链 (Windows)

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Playwright MCP 报 `Browser "chrome-for-testing" is not installed`，但浏览器此前确实装过 | 全局配置 `npx -y @playwright/mcp` 无版本钉定 → npx 每次解析最新版 → MCP 静默升级后其 playwright-core 要求更新的浏览器修订号（如 chromium-1232），本机只有旧版配套的（chromium-1228）。报错中的 "chrome-for-testing" 是新版中 `--browser chromium` 的 channel 别名，不是另一个浏览器 | ① 装匹配浏览器：`npx.cmd -y @playwright/mcp@<当前解析版本> install-browser chrome-for-testing`（下载至 `%LOCALAPPDATA%\ms-playwright\chromium-<rev>`，与旧版并存，无需重启 opencode）② **防复发：全局 `~/.config/opencode/opencode.jsonc` 把 `@playwright/mcp` 钉为 `@playwright/mcp@<版本>`**，重启 opencode 生效。以后升级：改版本号 + 重跑对应版本 install-browser |
| `npx ...` 报 `PSSecurityException: UnauthorizedAccess`（无法加载 npx.ps1） | Windows PowerShell 默认执行策略禁止运行 `.ps1` 脚本，`npx.ps1` shim 被拦截 | 用 `npx.cmd` / `npm.cmd` 替代（`.cmd` shim 不受执行策略限制），无需修改系统执行策略 |
| playwright MCP 报 `Access to "file:" protocol is blocked` | MCP 服务端安全策略默认禁止 file:// 协议导航 | 起本地 HTTP 服务再访问：`python -m http.server 8899 --bind 127.0.0.1`（工作目录设为 dashboard/），然后导航 `http://127.0.0.1:8899/index_standalone.html`；验证完记得 kill 进程并清理截图/`.playwright-mcp/` 快照目录 |

## P05 Harness 管线 Bug 诊断

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| 验收报告中 final_score 与交付方案内容不匹配（如 3.15 分的方案内容来自 3.0 分的那一轮） | `loop_runner` 第 412 行注释 "deliver best plan" 但第 434 行 `result.plan = current_plan` 把 best_plan 覆盖了。引用验证和文献覆盖检查也基于被覆盖后的 plan 执行 | 循环内跟踪 `best_plan/best_score/best_critique`，循环后显式赋值 `result.plan = best_plan; result.final_score = best_score; result.final_critique = best_critique`；cite/litcov 在赋值后执行。**诊断方法**：对比 harness_result.json 中 `plan.summary_zh` 内容是否与 `iterations` 中最高分轮次的迭代记录一致 |
| 验收报告"引用验证"一节完全空白（citation_checks=[]），但方案中有真实文献引用 | `citation_verifier.py` 去重逻辑 `key = doi or pmid or title`，"Author et al., 2018"（无 DOI/PMID）和 GSE123456（accession 非 title）的 key 为空串 → 被丢弃 → `citation_checks` 恒为空列表 | 去重 key 用回退链：`doi` → `pmid` → `accession` → `"author\|year"` → `title`（永不丢弃）。引用提取正则覆盖 accession 模式（GSE/GDS/E-XXX-/ENCSR/ENCFF/SRP/ERP/DRP）和作者-年份模式 |
| 引用验证误标真实著名论文为幻觉（如 "Cui et al., 2024"→scGPT、"Lopez et al., 2018"→scVI 全被标 not_found） | 作者-年份验证的 context_keywords 混入疾病名（"acute myeloid leukemia"）——被引用论文不讨论该疾病 → 查询失效 | 作者-年份查询只用**方法名**作关键词（如 "scGPT""scVI""Geneformer"），禁止附疾病名。方法名与被引用论文的研究主题强相关，命中率最高。**验证**：`"Cui scGPT"` 查询比 `"Cui 2024 scGPT acute myeloid leukemia"` 可靠得多 |
| 红队/新颖性判定描述了 refine 前的初始方案（如 T005 终版已补齐基线仍报"缺基线"） | Phase 1.5/1.6 只在初始方案执行；refine 循环修改方案后不复验。终版方案的 dummy accession（GSE123456）已被替换但从未验证 | refine 后若 `best_plan is not plan`，复跑 verify_novelty + run_redteam。存 initial + final 双版本，final 打 `reverified_post_refine: True` 标记。未复验的 stale 结果比无结果更有害 |
| MCP 调用计数不合理（如 ~155 次，远超实际搜索量） | `mcp_calls += self.search_engine.search_calls` 使用引擎级累计计数器——每阶段累加前面的总数 → 重复计数。且计数点混用 `len(new_papers)` 和 `len(unverified_claims)` 等不同量纲 | 每个计数点改为 delta: `before = mcp_ops(); ...; mcp_calls += mcp_ops() - before`。区分 `search_calls`（文献搜索）和 `lookup_calls`（DOI/PMID 解析）两类。不混合计数量纲 |
| T005 新颖性显示 "clear" 但 papers_found=0（实际含义是"未搜索"而非"无相关工作"） | `_judge_overlap` 在搜索返回 0 篇论文时直接返回 clear——零证据被当作"新颖" | 区分"已搜索无结果"和"未搜索"。papers_found=0 → `insufficient_evidence`。该状态的语义为"数据不足以做出判定"，聚合策略保守（any-IE → overall IE），永不 falsely clear |
| 验收报告迭代评分表缺少某维度（如仅 5 维缺"评估严谨性"） | 报告生成硬编码了维度名称列表，新增维度后未同步更新 | 迭代评分表动态构建：从 `RUBRIC_DIMENSIONS` 或 rubric 配置读取所有维度名称和权重，而非硬编码 |

## P05 Dashboard 可视化异常

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| P05 页评分柱状图只看得见 2 个颜色（其余 4 个维度被裁切） | `_renderScoreBar` 使用 `stack:'total'` 堆叠 5 维（总和 ~19）+ yAxis max=5 → 柱体高度 5 以上的部分不可见。维度语义独立，堆叠总计无意义 | 改为 grouped bars（`stack: undefined`，`barMaxWidth: 14`），yAxis max=5 正确展示各维度。语义独立的维度永远不用 stack；对比用 grouped bar 或 radar chart |
| 统计卡/图表/弹窗中缺少某个评分维度（如 6 维只显示 5 维） | JS `DIM_KEYS`/`DIM_LABELS` 和 Python rubric 维度列表不同步。新增 rubric 维度后 JS 需手动更新 | 维度定义在单一权威来源（如 rubric config），Python 和 JS 都从该来源生成；或在 build_data 时注入完整的维度列表到 data.json，JS 动态读取 |
| 候选 detail 弹窗中创新点显示 `1. [object Object]` | 数据结构为 `innovation_points: [{claim:"...", closest_existing_work:"..."}]`，JS 直接拼接 `cd.innovation_points[ni]`（对象→字符串） | 渲染嵌套对象时必须提取对应字段：`typeof ip === 'string' ? ip : ip.claim`。辅助函数在 tab 模块内自包含定义 |
| 弹窗中缺少新颖性判定/红队发现/评审意见章节 | `build_data._parse_harness_candidates` 只提取了已知字段，丢弃了 `novelty_verdict/redteam_result/final_critique` 等字段 | 数据解析函数默认**透传**源数据所有字段，不静默丢弃。新增字段走 `+=` 而非"只提取已知字段" |
| 仪表盘维度均分与报告不一致（如 3.3 vs 3.5） | 仪表盘 `_aggregate_harness_runs` 按所有轮次迭代重算维度均分；报告按每候选最终轮计算 | 统一计算口径：均定义为"各候选最佳轮（max weighted_score）的维度评分均值"。禁止各自实现不同的聚合逻辑 |
| JS console 报 `ReferenceError: esc is not defined`，导致弹窗无法打开 | `esc()` 函数定义在其他模块中（如 charts.js），但 p05.js 在 standalone HTML 的加载顺序中可能先于 charts.js 执行 | tab 模块内自包含定义辅助函数（`esc`/`truncate`），不依赖跨模块隐式加载顺序。或用内联替换：`.replace(/&/g,'&amp;').replace(/</g,'&lt;')...` |
