# AIscience Architecture

## Overview

AIscience is an AI agent for bioinformatics research topic selection. It runs 9 research sub-projects in parallel, each following a 12-skill pipeline under 6 archetypes.

```
main.py
└─ asyncio.gather ─ 9 × _run_one(project_id)
       └─ Orchestrator.run()
            └─ LoopEngine.run()
                 ├─ _run_scoping()     # s1, s2, s3 (or archetype-specific s3)
                 ├─ _run_inner_loop()  # s4, s5, s6, s6a, s7, s8, s9, s10
                 └─ _run_synthesis()   # s11, s12
  └─ cross_archetype_gap_scan()  # post-phase
```

Separate from the main pipeline, `scripts/p05_harness/`, `scripts/p08_harness/`, and
`scripts/p09_harness/` provide a critique-refine evaluation layer for research plans:
generate → multi-reviewer critique → novelty/red-team verify → citation verify → refine →
re-verify, with acceptance reports and dashboard integration.

## Three-Phase Data Flow

### Phase 1: Scoping (s1–s3)

Purpose: decompose research direction → normalize terminology → collect locus/gene data.

```
SkillInput (initial) → s1_direction_decompose → s2_terminology_normalize → s3_v2g_locus_collect → scoped_input
```

**Critical rule**: `_run_scoping()` MUST return the enriched `SkillInput` to the caller. The enriched input carries `key_terms`, `sub_questions`, `normalized_traits`, `locus_genes` etc. into the inner loop.

**Before fix** (bug): `_run_scoping()` returned `None`; `run()` passed the original bare `initial_input` to `_run_inner_loop()`.

### Phase 2: Inner Loop (s4–s10)

Purpose: search literature, screen papers, extract evidence cards.

Runs up to `max_inner_iterations` (default 5) per outer round. Each iteration runs all inner-loop skills sequentially. Convergence reasons: `query_exhausted`, `citation_closed`, `reflection_confirmed`.

Skill sequence: `s4 → s5 → s6 → s6a (divergent) → s7 → s8 → s9 → s10`

### Phase 3: Synthesis (s11–s12)

Purpose: analyze gaps across all collected evidence, generate hypotheses.

**Critical rule**: Synthesis reads from **L2 context** (`harness.context.l2.snapshot()`), NOT from `current_input`. After running s11/s12, outputs must be explicitly written to L2 with the correct keys so `_extract_gaps_from_l2()` / `_extract_hypotheses_from_l2()` can find them.

Required L2 keys:
- `output_s11_gap_analysis` → auto-stored by `_propagate_output`
- `identified_gaps` → manually stored after s11: `harness.context.warm_to_l2("identified_gaps", gaps_data)`
- `output_s12_hypothesis_generate` → auto-stored
- `hypotheses` → manually stored after s12: `harness.context.warm_to_l2("hypotheses", hyp_data)`

## L2 Context Mechanism

`_propagate_output(skill_output, skill_id, current_input)` does two things:
1. Stores output to L2: `harness.context.warm_to_l2(f"output_{skill_id}", new_data)`
2. Merges into current_input and returns enriched SkillInput

The L2 snapshot is used by:
- `_run_synthesis()` to build the input for s11/s12
- `_extract_gaps_from_l2()` / `_extract_hypotheses_from_l2()` to collect final results
- `_check_outer_convergence()` to compute citation and gap metrics

## Convergence

### Inner Loop
- `query_exhausted`: no new papers from s4
- `citation_closed`: citation network stops expanding
- `reflection_confirmed`: reflection loop confirms results

### Outer Loop
- `coverage_jaccard`: Jaccard similarity of coverage matrix between rounds >= threshold (default 0.70)
- `gap_yield`: gap count relative to occupied coverage cells below threshold (default < 0.30 ratio)
- `citation_closed`: citation network has DOIs and card store has cards
- `max_rounds`: default 5

## Key Files

| File | Role |
|------|------|
| `main.py` | Entry point, parallel runner, cross-scan |
| `shared/core/loop_engine.py` | Three-phase loop, data flow, convergence |
| `shared/core/orchestrator.py` | Per-project orchestrator, result collection |
| `shared/core/llm_client.py` | LLM calls via litellm, JSON parsing |
| `shared/core/config.py` | Settings (env_prefix="AISCIENCE_") |
| `shared/skills/base_skill.py` | Skill contract (SkillInput/Output, BaseSkill) |
| `shared/evidence/base_card.py` | Evidence card base schema (V2GEvidenceCard, SCFMEvidenceCard, OmicsScoreEvidenceCard) and shared fields |
| `shared/evidence/card_store.py` | LanceDB-backed card storage |
| `shared/core/harness.py` | Skill execution harness, timeout, provenance |
| `shared/core/context.py` | L0/L1/L2 context manager |

## Archetype Gap Pattern Registry

Each archetype has 10 domain-specific gap patterns (except scAI with 11):

| Archetype | Pattern IDs | Gap Analysis Block | File |
|-----------|-------------|-------------------|------|
| V2G (A) | P1-P10 | `is_v2g` | `archetypes/archetype_a_v2g/gap_patterns.py` |
| PRS (B) | B1-B10 | `is_prs` | `archetypes/archetype_b_prs/gap_patterns.py` |
| scAI (C) | C1-C11 | `is_sc_fm` | `archetypes/archetype_c_sc_ai/gap_patterns.py` |
| Omics Score (D) | D1-D10 | `is_omics_score` | `archetypes/archetype_d_omics_score/gap_patterns.py` |
| Cross-Ethnic (E) | E1-E10 | `is_cross_ethnic` | `archetypes/archetype_e_cross_ethnic/gap_patterns.py` |
| Spatial GWAS (F) | F1-F10 | `is_spatial_gwas` | `archetypes/archetype_f_spatial_gwas/gap_patterns.py` |

Detection uses `c.archetype` string (not field values), because converted cards may have all archetype-specific fields as `None`. Generic patterns (P3, P9, P10) apply to ALL archetypes.

## Checkpoint System Coverage

The checkpoint system in `loop_engine.py` has asymmetric coverage across the 3-phase loop:

| Phase | Skills | Checkpoint Type | Coverage |
|-------|--------|----------------|----------|
| Scoping | S1-S3 | `r{round}_{sid}.json` | Per-skill, individual |
| Inner Loop | S4-S10 (含 s6a/s6b) | `r{round}_inner_loop.json` | Aggregate only (no per-skill) |
| Synthesis | S11-S12 | `r{round}_{sid}.json` | Per-skill, individual |

**Implication for `build_data.py`**: `compute_pipeline_progress()` must detect `*inner_loop*` files to correctly mark S3-S10 as completed. Without this, inner-loop skills are always counted as incomplete, causing progress to under-report (e.g. 5/13 = 38% instead of 100%).

## Dashboard Architecture

### Rendering Conventions

| Convention | Where | Rule |
|-----------|-------|------|
| Literature links | All `paper_*` fields | Use `litLink(l)` / `litAnchor(l, maxLen)`, priority: `paper_url` → `doi` → `pmid` |
| Chart legends (≥5 series) | `gaps.js`, `hypotheses.js`, `proposals.js`, `overview.js` | `legend: { type: 'scroll' }`, `grid.bottom` ≥ 55px |
| Legend labels | All 7-series charts | Use `p.name_en` (English short name), not `p.name` (Chinese) |
| Single-series charts | `hypotheses.js` boxplot | Remove redundant legend |
| Table scrolling | All tab JS files | Wrap tables in `<div class="table-wrap">` for horizontal scroll |
| Sticky table headers | `evidence.js` literature table | Use `.sticky-table` CSS class |
| Dark mode borders | `styles.css` | Minimum `#475569` on `#0f172a`/`#1e293b` backgrounds (≥3:1 contrast) |
| Mobile breakpoints | `styles.css` | Include both `@media (max-width: 768px)` and `@media (max-width: 480px)` |
| Text truncation | All JS inline strings | Always use ellipsis + `title` attribute, never bare `.slice(0,N)` |

```
dashboard/
├── index.html              # Shell loads CSS + JS modules
├── css/styles.css          # All styling + landing page + skeleton states
├── js/
│   ├── charts.js           # Shared ECharts helpers (initChart, fontColor, textColor)
│   ├── app.js              # Core: App.DATA state, theme toggle, tab routing, export
│   └── tabs/
│       ├── overview.js     # Project radar chart, progress bars, detail cards
│       ├── evidence.js     # Card distribution, year histogram, literature table
│       ├── gaps.js         # Gap heatmap, detail modal with supporting cards
│       ├── hypotheses.js   # Scatter plot, enhanced modal with rationale/methods/datasets
│       ├── pipeline.js     # Step flow, budget bars, phase allocation
│       ├── compare.js      # 2-3 project selection, 6-dim radar comparison
│       ├── proposals.js    # Data-driven thesis suggestion matrix
│       ├── decompose.js    # Dimensional decomposition: heatmap, bell-curve, axes overview, top-15 table
│       ├── p05.js          # P05 scFM research-plan quality
│       ├── p08.js          # P08 cross-ethnic research-plan quality
│       └── p09.js          # P09 spatial-GWAS research-plan quality
├── data.json               # Aggregated data (built by build_data.py)
├── build_data.py           # Reads 9 project outputs → data.json
└── index_standalone.html   # Self-contained with inline data (no server needed)
```

## Data Build Pipeline

```
build_data.py
  ├─ load_project_config()         # Read config.yaml research_direction
  ├─ load_summary()                # Read summary.json per project
  ├─ load_gaps()                   # Read final_report.json gaps
  ├─ load_hypotheses()             # Read final_report.json hypotheses
  ├─ load_cards_literature()       # Extract dedup papers from evidence_cards.jsonl
  ├─ compute_pipeline_progress()   # Check checkpoints + output files
  ├─ compute_cross_patterns()      # Calculate pattern×project from gap data
  ├─ generate_thesis_suggestions() # Cluster hypotheses by novelty×feasibility
  ├─ load_decompose_results()      # Read data/decompose_pilot_results.json
  └─ → data.json (aggregated evidence cards, gaps, hypotheses, papers, harness dimensions)

Offline scripts:
  scripts/generate_coverage_maps.py  # Read cards.jsonl → coverage_map.json (zero LLM)
  scripts/rerun_p04_gap.py           # Re-run S11+S12 for p04 (LLM for S12)
  scripts/rerun_p05_p06_p07.py       # Convert schema + re-run S11+S12 for p05-p07
  scripts/decompose_directions.py    # 4-phase dimensional decomposition + PubMed density + scoring
  scripts/p05_harness/main.py        # P05 critique-refine research-plan harness
  scripts/p08_harness/main.py        # P08 cross-ethnic research-plan harness
  scripts/p09_harness/main.py        # P09 spatial-GWAS research-plan harness
```
