# p05: scFM Architecture & AI Agent Research

## Overview

p05 pursues two research lines:
1. **scFM architectural depth**: evaluate single-cell foundation models across
   architecture families (Transformer/Mamba/Hyena/VQ-VAE/Diffusion/JEPA),
   not limited to the 6 legacy models
2. **AI Agent methods**: dynamic model selection (Router), adaptive benchmarking
   (Self-Evolving), online learning with cost constraints (Bandit)

**Language**: Python 3.11+ / YAML configs
**Archetype**: archetype_c_sc_ai
**LLM**: litellm adapter (default `gpt-4o-mini`)

## Custom Decomposition

Uses per-project custom axes instead of default disease×tissue×method×data×population.
Defined in `config.yaml` → `decompose.custom_axes`:

- **scfm_depth**: architecture_family × modality_combination × training_paradigm
  × pretraining_corpus × evaluation_paradigm
- **agent_line**: agent_paradigm × capability (with GitHub awesome-list seeding)

Regenerate candidates:

```bash
python scripts/decompose_directions.py --projects p05
```

## S6C Deep Read Skill

Replaces legacy `s6a_scfm_search`. 6 internal stages:

| Stage | Tier 1 | Tier 2 | Description |
|-------|--------|--------|-------------|
| 1 | — | — | Paper identity & source registration |
| 2+3 | ✓ | ✓ | Fact extraction + claim-evidence audit (combined LLM) |
| 6 | ✓ | ✓ | Programmatic quality gates |
| 4 | — | ✓ | Formula derivation chain + experiment analysis |
| 4-refute | — | ✓ | Formula refutation double audit (construct→refute) |
| 5 | — | ✓ | Critical assessment |

- Tier 1: all papers → stages 2+3+6
- Tier 2: top 2 papers per candidate → all stages
- Quality gates: claims must have evidence; strong verdicts require direct support
- Output flows into S7 via `deep_read_notes` → enriched cards

## Evidence Cards

`SCFMEvidenceCard` has 3 deep-read enrichment fields:
- `evidence_status`: directly_stated | inferred | author_claim | unresolved
- `evidence_strength`: fully_supported | partially_supported | insufficient | conflicting
- `deep_read_source`: paper_id of the deep-read note

S7 extraction priority:
1. `_extract_from_deep_read()` — if deep_read_note exists for the paper
2. `_extract_from_paper()` — fallback for papers without deep-read notes

## Harness Integration

```bash
# Full harness evaluation
python scripts/p05_harness/main.py

# Deep analysis only (existing candidates)
python scripts/p05_harness/main.py --deep-only

# With agent candidates
python scripts/p05_harness/main.py --candidates-file data/p05_agent_candidates.json
```

Harness evaluates both scFM and agent candidates through the full Phase 0→3 pipeline.
GENERATE_SYSTEM prompt covers both domains.

## Pipeline Commands

```bash
# Re-decompose with custom axes
python scripts/decompose_directions.py --projects p05

# Run full p05 pipeline
python main.py --only p05_sc_multiomics_ai

# Re-run S11+S12 only (LLM for S12)
python scripts/rerun_p05_p06_p07.py

# Build dashboard
python dashboard/build_data.py
```

## Key Config (config.yaml)

| Field | Value |
|-------|-------|
| `archetype_id` | archetype_c_sc_ai |
| `divergent_step.sid` | s6c_deep_read |
| `convergence.candidate_driven` | true |
| `convergence.max_candidates` | 3 |
| `parameters.deep_read.max_papers_per_candidate` | 5 |
| `parameters.deep_read.max_tier2_papers` | 2 |
| `parameters.deep_read.formula_confidence_threshold` | 0.85 |

## Key Files

| What | Where |
|------|-------|
| Config | `config.yaml` |
| Evidence card schema | `archetypes/archetype_c_sc_ai/evidence_card.py` |
| S7 scfm card extract | `archetypes/archetype_c_sc_ai/skills/skill_07_scfm_card_extract.py` |
| Gap patterns | `archetypes/archetype_c_sc_ai/gap_patterns.py` |
| Agent candidates | `data/p05_agent_candidates.json` |
| Decompose candidates | `data/decompose_pilot_results.json` (p05 entry) |
| Harness entry | `scripts/p05_harness/main.py` |
| Harness runner | `scripts/p05_harness/loop_runner.py` |
| Dashboard tab | `dashboard/js/tabs/p05.js` |

## Related Docs

- `docs/session_2026-07-14_p05_candidate_driven.md`
- `docs/session_2026-07-15_p05_harness_engineering.md`
- `docs/session_2026-07-16_p05_mamba_architecture_gap.md`
- `docs/session_2026-07-17_p05_harness_improvement.md`
- `docs/session_2026-07-19_p05_comprehensive_fix.md`
- `docs/session_2026-07-21_p05_deep_read_implementation.md`
- `docs/p05_research_survey_v1.md`
- Awesome list: https://github.com/OmicsML/awesome-foundation-model-single-cell-papers
