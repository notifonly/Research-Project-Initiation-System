# Skill Development Guide

How to develop, debug, and harden skills in the AIscience pipeline. Based on real debugging experience across 20+ bugs.

---

## 1. Skill Contract

Every skill extends `BaseSkill` and must define:

```python
class MySkill(BaseSkill):
    name = "my_skill"
    description = "What this skill does"
    uses_llm = True                          # or False
    budget_phase = BudgetPhase.EXTRACTION    # SCOPING | DISCOVERY | EXTRACTION | SYNTHESIS
    input_schema = MySkillInput              # MUST be a SkillInput subclass with extra="allow"
    output_schema = MySkillOutput            # MUST be a SkillOutput subclass with extra="allow"

    async def pre_check(self, inp, ctx) -> bool: ...    # optional guard
    async def execute(self, inp, ctx) -> SkillOutput: ...  # main logic
    async def quality_gate(self, output, ctx) -> bool: ... # post-execution validation
    def metrics(self) -> dict[str, Any]: ...             # optional telemetry
```

**Key rules**:
- `input_schema` and `output_schema` MUST have `model_config = {"arbitrary_types_allowed": True, "extra": "allow"}`
- `budget_phase` determines which token budget pool is consumed
- The base `run()` method calls `pre_check → execute → quality_gate` in sequence

> **Note on IDE type warnings**: All Skill subclasses narrow their `execute()` and `quality_gate()` parameter types from `SkillInput`/`SkillOutput` to concrete subclasses (e.g., `DirectionDecomposeInput`). Pyright/Pylance will report `"Method overrides class in an incompatible manner"` — this is a known covariant override pattern used throughout the project, NOT a runtime error. Pydantic validates types at runtime. See `docs/TROUBLESHOOTING.md#lspide-type-check-warnings` for details.

### SkillContext

```python
class SkillContext:
    project_id: str
    mcp_registry: MCPRegistry    # access all MCP tools
    card_store: CardStore        # store evidence cards
    context: ContextManager      # L0/L1/L2 layers
    budget: TokenBudget          # token accounting
    archetype_config: dict       # archetype YAML config
    scratch: dict                # temporary cross-skill data
```

---

## 2. LLM Integration Patterns

### 2.1 Configuration

LLM requires `.env` configuration:

```env
AISCIENCE_LLM_API_KEY=sk-...
AISCIENCE_LLM_BASE_URL=https://your-endpoint/v1
AISCIENCE_LLM_MODEL=openai/model-name
AISCIENCE_LLM_MAX_TOKENS=8192
```

`llm_client.py` passes `api_key` only when `settings.llm_api_key` is non-empty. Without it, ALL LLM calls silently return stubs (`{"_stub": True, "_error": "..."}`). This causes a cascading 0-card pipeline failure.

### 2.2 Calling LLM from a skill

```python
# Simple text completion
result = await self._llm(prompt, ctx)
# Returns str

# Structured JSON output (object)
result = await self._llm(prompt, ctx, structured=MyModel)
# Returns dict (parsed JSON)

# Structured JSON output (list)
result = await self._llm(prompt, ctx, structured=list)
# Returns list OR dict (!) — see 2.4
```

**Never** use `self._llm(prompt, ctx, structured=V2GEvidenceCard)` expecting to get card objects directly. The LLM returns dicts. Always build Pydantic models manually from the dict.

### 2.3 _parse_json: handles more than you think

`_parse_json()` in `llm_client.py` tries these strategies in order:
1. `json.loads(raw)` — direct parse
2. Find `[...]` and parse array
3. Handle truncated arrays (missing `]`, trailing comma)
4. Find `{...}` and parse object

**Common LLM output issues the parser handles**:
- Markdown code blocks (` ```json ... ``` `)
- Trailing commas in arrays
- Tokens truncated mid-JSON (adds missing `]`)

### 2.4 Dict-wrapped list pitfall

When using `structured=list`, the LLM may return `{"findings": [...]}` instead of `[...]`. Always add a fallback:

```python
result = await self._llm(prompt, ctx, structured=list)
if isinstance(result, dict):
    for v in result.values():
        if isinstance(v, list):
            result = v
            break
if not isinstance(result, list):
    return []  # or error
```

### 2.5 Type coercion: LLM output types are unreliable

The LLM may return:
- A string for an integer field: `"pos": "12345"` instead of `12345`
- A list for a string field: `"trait_label": ["schizophrenia", "smoking"]`
- `None` for a required string field: `"method_brief": null`
- An empty list for an optional string: `"raw_data_accession": []`

**Always coerce** LLM output before constructing Pydantic models:

```python
@staticmethod
def _coerce_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v if x)
    if isinstance(v, str):
        return v
    return str(v)

@staticmethod
def _coerce_opt_str(v: Any) -> Optional[str]:
    result = _coerce_str(v)
    return result if result else None

@staticmethod
def _coerce_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None

@staticmethod
def _coerce_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
```

Apply to **every** field in evidence card construction. Never trust `finding.get("field_name", default)` alone.

### 2.6 max_tokens configuration

Default `max_tokens=4096` may truncate LLM output for evidence extraction (multiple findings per paper). Set `AISCIENCE_LLM_MAX_TOKENS=8192` for skills that produce long structured output (s7, s11, s12).

---

## 3. MCP Integration Patterns

### 3.1 Null safety

External APIs commonly return `null` for missing fields. Python's `dict.get("key", default)` only catches missing keys, NOT `null` values.

```python
# WRONG — null passes through
paper.get("abstract", "")      # returns None if key exists with null value

# CORRECT — null becomes empty string
paper.get("abstract") or ""    # returns "" for both None and missing key

# CORRECT — null becomes empty list
(paper.get("authors") or [])   # returns [] for both None and missing key
(paper.get("externalIds") or {}).get("DOI")  # safe nested access
```

### 3.2 PubMed enrichment chain

PubMed's `esearch` returns only PMIDs. To get full paper metadata, chain three calls:

```
esearch(query) → id_list (PMIDs)
  → esummary(id_list[:50]) → title, authors, year, venue
  → efetch(id_list, db="pubmed", rettype="medline") → abstracts
```

Parse MEDLINE format for abstracts: find `PMID- {id}` blocks with `AB  - {abstract text}`.

### 3.3 resp.json() fallback

Some MCP endpoints return plain text (e.g., PubMed efetch in MEDLINE format). Always add a fallback:

```python
try:
    return resp.json()
except Exception:
    return resp.text  # or parse raw text
```

---

## 4. Evidence Card Requirements

### 4.1 Field types are strict

`V2GEvidenceCard` and other card models use strict Pydantic types. A single type mismatch invalidates the entire card.

| Field | Type | Coercion needed |
|-------|------|----------------|
| `key_finding`, `method_brief` | `str` (required) | `_coerce_str()` — handles None→"" |
| `trait_label`, `chrom`, `causal_gene_claimed` etc. | `Optional[str]` | `_coerce_opt_str()` — handles list→join, None→None |
| `pos`, `sample_size` | `Optional[int]` | `_coerce_int()` — handles "123"→123 |
| `p_value`, `effect_size_beta` | `Optional[float]` | `_coerce_float()` — handles "0.05"→0.05 |
| `locus_genes`, `tags` | `list[str]` | `isinstance(v, list)` guard |
| `raw_data_accession` | `Optional[str]` | `_coerce_opt_str()` — handles `[]`→None |
| `source_type` | `Literal["paper","database","preprint","code_repo","dataset"]` | Must be one of these 5 values |
| `extracted_at` | `str` (ISO datetime) | Use `utc_now_iso()` default, NOT `time.time()` |

### 4.2 Field name matching

Schema field names must match exactly. Common mismatches:
- `limitations` → should be `limitation_explicit` / `limitation_implicit`
- `source_type` = `"literature"` → must use literal values like `"paper"`

---

## 5. Data Flow Patterns

### 5.1 Scoping → Inner Loop

The scoping phase (s1-s3) enriches the SkillInput with `key_terms`, `sub_questions`, `normalized_traits`, `locus_genes`. This enriched input MUST flow into the inner loop.

```python
# In loop_engine.run():
scoped_input = await self._run_scoping(scoping, initial_input)  # capture return
inner_result = await self._run_inner_loop(inner, round_idx, scoped_input)  # pass enriched
```

`_run_scoping()` must `return current_input` at the end.

### 5.2 _prepare_skill_input

For each skill, the loop engine prepares input from accumulated state. Use the **skill-specific input_schema**, not the base `SkillInput`:

```python
# WRONG
return SkillInput.model_validate(data)

# CORRECT
skill = self.skill_instances.get(sid)
schema = skill.input_schema if skill else SkillInput
return schema.model_validate(data)
```

This ensures default values defined in the skill's input schema (e.g., `year_range=None`) are applied.

### 5.3 L2 Context Key Naming

Outputs are stored under `"output_{skill_id}"` by `_propagate_output`. Code that reads from L2 MUST use the same key:

| Store key | Read location |
|-----------|--------------|
| `"output_s11_gap_analysis"` | `_run_synthesis()` builds input |
| `"identified_gaps"` | `_extract_gaps_from_l2()` collects final gaps |
| `"output_s12_hypothesis_generate"` | `_run_synthesis()` builds input |
| `"hypotheses"` | `_extract_hypotheses_from_l2()` collects final hypotheses |

If a retrieval function finds nothing, add explicit `warm_to_l2` calls after synthesis skills complete.

### 5.4 Cross-skill type compatibility

When s1 produces `scope_boundaries` as `dict[str, str]` but s6 expects `scope_include: list[str]`, the loop engine must convert:

```python
scope = s1_output.get("scope_boundaries", {})
inc = scope.get("include", [])
data.setdefault("scope_include", [inc] if isinstance(inc, str) else inc)
```

---

## 6. Timeout Management

### 6.1 Default timeout

`harness.run_skill()` has `timeout_s=120.0` default. Skills with many LLM calls (s7 extracting from many papers) will exceed this.

### 6.2 Parallelization + cap

```python
max_papers = 5
targets = inp.targets[:max_papers]

tasks = [self._extract_from_paper(t, ...) for t in targets]
results = await asyncio.gather(*tasks, return_exceptions=True)

for i, paper_cards in enumerate(results):
    if isinstance(paper_cards, BaseException):
        logger.warning(f"Extract failed: {paper_cards}")
        continue
    cards.extend(paper_cards)
```

**Key points**:
- Cap targets to a small number (5)
- Use `return_exceptions=True` so one failure doesn't cancel others
- Check `isinstance(result, BaseException)` for error handling

---

## 7. Common Pitfalls Checklist

When developing a new skill, verify:

- [ ] `.env` has valid LLM API key configured
- [ ] `input_schema` and `output_schema` have `extra="allow"` and `arbitrary_types_allowed=True`
- [ ] `budget_phase` matches the skill's role (SCOPING/DISCOVERY/EXTRACTION/SYNTHESIS)
- [ ] All LLM output fields are coerced before model construction
- [ ] Dict-wrapped list fallback is present when using `structured=list`
- [ ] MCP API responses use null-safe access: `x.get("field") or default`
- [ ] PubMed pipeline chains esearch → esummary → efetch
- [ ] `resp.json()` has `.text` fallback
- [ ] Evidence card field names match schema exactly
- [ ] `source_type` uses correct Literal value
- [ ] LLM-heavy skills cap targets and parallelize with `asyncio.gather`
- [ ] Scoping phase returns enriched SkillInput (if modifying loop_engine)
- [ ] L2 context keys are consistent between store and retrieval
- [ ] Cross-skill types are converted in `_prepare_skill_input`

---

## 8. Testing a Skill

```bash
# 1. Verify LLM connectivity
python -c "import asyncio; from shared.core.llm_client import llm_complete; print(asyncio.run(llm_complete('reply PONG')))"

# 2. Run single project
python main.py --only p01_gwas_perturb_seq

# 3. Check results
python -c "import json; d=json.load(open('data/run_all_report.json')); print(d['total_cards'], d['total_gaps'], d['total_hypotheses'])"

# 4. Inspect logs
rg "quality_gate failed|ERROR|validation error" logs/p01_gwas_perturb_seq.log
```

---

## 9. Adding Archetype-Specific Gap Analysis

When adding a new archetype, you MUST add a corresponding gap analysis block in `skill_11_gap_analysis.py`. This section documents the pattern using the recent addition of sc_fm (C1-C10) and omics_score (D1-D10) blocks.

### 9.1 Detection Method

Add a `_has_{archetype}_fields()` method that checks the card's `archetype` string:

```python
def _has_sc_fm_fields(self, cards: list[BaseEvidenceCard]) -> bool:
    return any(getattr(c, "archetype", "") == "sc_fm" for c in cards)
```

**Why archetype string, not field values?** Converted cards (see §9.3) have all archetype-specific fields as `None`. Field-value detection (`getattr(c, "model_architecture", None)`) will always fail. The `archetype` string is always set correctly by the card class.

### 9.2 Gap Block Pattern

Each archetype needs an `if` block in `execute()` with 10 gap checks. Follow this template:

```python
is_sc_fm = self._has_sc_fm_fields(inp.cards)
if is_sc_fm:
    # C1: single_omics_only
    no_modality = [c for c in inp.cards if not getattr(c, "modality_omics", None)
                   and not getattr(c, "modalities_integrated", None)]
    if no_modality:
        gaps.append(IdentifiedGap(
            gap_id="C1_single_omics", pattern_id="C1",
            description=f"{len(no_modality)} cards lack omics modality specification",
            score=0.8, feasibility=0.7, competition=0.3, cross_archetype=0.2,
        ))

    # C2-C10: repeat pattern for each gap type
    # ...

```

Key rules:
- `pattern_id` must match the id in `gap_patterns.py` (C1, C2, ..., D1, D2, ...)
- Use `gap_id` that's unique per detection (e.g. "C3_no_heldout", "D2_no_external")
- Set `supporting_cards` to show evidence for gaps backed by card data
- Generic patterns (P3, P9, P10) apply to ALL archetypes — do NOT gate them

### 9.3 Card Schema Conversion (Offline, No LLM)

When existing cards have the wrong archetype schema, convert without re-running LLM extraction:

```python
from archetype_c_sc_ai.evidence_card import SCFMEvidenceCard

# Load cards from JSONL (flat format with paper_* / loc_* fields)
raw = json.loads(line)
# Re-nest flat fields
for prefix, target in [("paper_", "source_paper"), ("loc_", "source_location")]:
    obj = {k[len(prefix):]: v for k, v in raw.items() if k.startswith(prefix)}
    raw.setdefault(target, {}).update(obj)
# Set correct archetype
raw["archetype"] = card_class.model_fields["archetype"].default
# Validate with correct card class — extra fields are ignored, new fields default to None
card = SCFMEvidenceCard.model_validate(raw)
```

This preserves shared fields (`key_finding`, `method_brief`, `source_paper`) while dropping v2g-specific fields and adding sc_fm/omics_score defaults. See `scripts/rerun_p05_p06_p07.py` for the complete implementation.

### 9.4 Checklist: Adding a New Archetype

- [ ] Create `archetypes/archetype_X/config.yaml` with `evidence_card_class` pointing to correct card
- [ ] Create `archetypes/archetype_X/evidence_card.py` with archetype-specific fields
- [ ] Create `archetypes/archetype_X/gap_patterns.py` with 10 gap patterns (X1-X10)
- [ ] Register in `archetypes/__init__.py` (`_ARCHETYPE_MODULES` etc.)
- [ ] Add `_has_X_fields()` detection to `skill_11_gap_analysis.py`
- [ ] Add X1-X10 gap analysis block to `skill_11_gap_analysis.py`
- [ ] Add X1-X10 patterns to `docs/使用手册.md` §7 Gap 模式参考
- [ ] Register in `build_data.py` archetype column (if applicable)
- [ ] Verify: `python scripts/generate_coverage_maps.py && python dashboard/build_data.py`

---

## 10. P05 Harness 开发模式（Research Plan Quality Check）

本节基于 p05 harness 验收修复会话（2026-07-21，12 条经验教训）提炼出 6 条可工程化的开发规范，适用于编写类似的"LLM 生成→评审→修正→验收"质量把关管线。

### 10.1 循环交付正确性——永远交付 best，不交付 last

**问题模式**:
```python
for iteration in range(max_iterations):
    current_plan = refine(critique)
    current_score = evaluate(current_plan)
    if current_score > best_score:
        best_score = current_score
        best_plan = current_plan

result.plan = current_plan  # ← 覆盖了 best_plan
```

**规则**: 循环内的 `best_X` 跟踪变量必须在循环结束后显式赋值给 `result.X`。引用验证、文献覆盖检查等后续步骤必须基于 `result.X`（即 best）执行。代码审查时逐行验证循环后的赋值不被后续语句覆盖。

**防护**: 在 harness_result.json 的验收检查中对比 `plan` 内容与 `iterations` 中最高分轮次的迭代记录是否一致。不一致 = best_plan 被覆盖。

### 10.2 引用验证三态模型——区分强信号和弱信号

引用验证返回 `verified`/`not_found`/`unverifiable` 三态，而非二值：

| 通道 | 验证方式 | 信号强度 | not_found 含义 |
|------|---------|---------|---------------|
| DOI / PMID | API 解析（Crossref/PubMed） | **强** | 真正的幻觉引用 → `not_found` ❌ |
| Accession (GSE/ENCSR...) | 文献搜索，max_per_source=3 | **弱** | 搜索未覆盖（GEO/ENCODE 不在文献索引中） → `unverifiable` ❓ |
| Author-Year | 文献搜索，3 查询策略，年份容差 ±1 | **中** | 可能假阴性（查询质量依赖） → `not_found` ❌（需人工复核） |

**规则**: Accession pattern `GSE\d+|GDS\d+|E-[A-Z]+-\d+|ENCSR\d+|ENCFF\d+|SRP\d+|ERP\d+|DRP\d+`

**容量上限**: `_MAX_VERIFY_PER_TYPE = {doi:15, pmid:10, accession:10, author_year:8}` 防 MCP 调用量爆增

**Author-year 查询策略**: 三查询渐进式 `[(surname+year+context_keywords,5), (surname+context_keywords,5), (surname+year,10)]`。**context_keywords 只能包含方法名（如 "scGPT"），禁止附带疾病/组织名**——被引用论文不讨论你的研究疾病，疾病关键字会污染查询。

### 10.3 MCP 调用 Delta 计数——禁止累计计数器

**问题模式**:
```python
mcp_calls += self.search_engine.search_calls  # 累计值 = 本阶段 + 前面所有阶段
mcp_calls += len(new_papers)                  # 量纲混合：次数 + 篇数
```

**规则**:
```python
def mcp_ops():
    return self.search_engine.search_calls + self.search_engine.lookup_calls

before = mcp_ops()
# ... 执行 MCP 操作 ...
mcp_calls += mcp_ops() - before  # delta
```

区分 `search_calls`（文献搜索 API 调用）和 `lookup_calls`（DOI/PMID 解析 API 调用），两者分别计数。

### 10.4 新颖性"证据不足"状态——永不 falsely clear

`papers_found=0` 有两种含义：(a) 该领域无相关工作（真 clear）；(b) 搜索策略未覆盖（搜索失败）。仅凭 API 返回值无法区分。

**规则**: `papers_found=0` → `insufficient_evidence`（非 clear）。`_aggregate_overall_verdict` 采用保守策略：any insufficient_evidence → overall insufficient_evidence。永不 falsely clear。

### 10.5 证据卡回退机制——防止零锚定幻觉

当候选方向没有标签证据卡（evidence_cards.jsonl 中 `candidate:{topic_id}` 标签不匹配）时，方案生成缺少文献锚定 → accession 幻觉的温床。

**规则**: 构建全库卡池 `all_cards_pool`；`_process_candidate` 接收 `evidence_fallback` 参数；无标签卡的候选回退到全库卡池。`literature_coverage` 记录 `evidence_source: 'fallback_pool'|'tagged'`，报告和仪表盘标注来源。

### 10.6 状态性判定必须随对象变更而复验

Phase 1.5（新颖性）和 Phase 1.6（红队）是对**方案内容**的判定。Refine 循环一旦修改方案内容，这些判定就过期了。

**规则**: refine 循环后若 `best_plan is not initial_plan`，复跑 verify_novelty + run_redteam。存储 `novelty_verdict_initial` / `novelty_verdict`（final）双版本，final 打 `reverified_post_refine: True` 标记。报告显示"初始判定 X → 最终判定 Y + 已复验"。

### 10.7 仪表盘 JS 防御性模式

| 模式 | 错误写法 | 正确写法 |
|------|---------|---------|
| 渲染嵌套对象的内部字段 | `${p}`（→ `[object Object]`） | `${typeof p === 'string' ? p : p.claim}` |
| HTML 转义 | `esc(text)`（依赖跨模块加载顺序） | `text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')` |
| 文本截断 | `.slice(0, N)` 无省略号和 title | `(text.length>N ? text.slice(0,N)+'...' : text)` + `title="${escapedText}"` |
| 多维评分对比图 | `stack:'total'` + `yAxis.max:5`（裁切） | grouped bars: `stack: undefined, barMaxWidth: 14, yAxis.max: 5` 或 radar chart |
| 数据透传 | `{known_field: src.known_field}`（丢弃未知字段） | `{...src}` 或逐字段透传（不静默丢弃） |
