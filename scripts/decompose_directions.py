"""试点：维度拆分 + 三级筛选 - 将大方向拆解为具体可落地的课题。

Phase 1: LLM 多维度分解 (疾病 × 组织/细胞 × 数据 × 方法 × 人群)
Phase 2: 十字交叉生成候选课题池
Phase 3: 文献密度检查 (MCP Semantic Scholar + PubMed)
Phase 4: 综合评分排名 (新颖性 + 可行性 + 竞争力)

Usage:
    python scripts/decompose_directions.py --projects p01_gwas_perturb_seq,p06_digital_immune
    python scripts/decompose_directions.py --projects p01_gwas_perturb_seq --dry-run  # skip MCP searches
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from archetypes import load_archetype
from shared.core.config import settings
from shared.core.llm_client import llm_complete
from shared.core.logging_setup import get_logger
from shared.mcp.registry import MCPRegistry
from shared.mcp.base.base_mcp import MCPResult

logger = get_logger("decompose_directions")


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM output, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove opening fence (``` or ```json etc.)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


@dataclass
class DimensionAxes:
    disease_phenotypes: list[str] = field(default_factory=list)
    cell_types_tissues: list[str] = field(default_factory=list)
    data_resources: list[str] = field(default_factory=list)
    methods_techniques: list[str] = field(default_factory=list)
    populations: list[str] = field(default_factory=list)


@dataclass
class CandidateTopic:
    topic_id: str
    project_id: str
    research_question: str
    disease: str = ""
    tissue: str = ""
    data_resource: str = ""
    method: str = ""
    population: str = ""
    # Generic dimension store for projects with custom axes
    dimensions: dict[str, Any] = field(default_factory=dict)
    search_query: str = ""
    literature_count: int = 0
    literature_top_papers: list[dict] = field(default_factory=list)
    density_score: float = 0.0
    novelty_score: float = 0.0
    feasibility_score: float = 0.0
    competitiveness_score: float = 0.0
    combined_score: float = 0.0
    rationale: str = ""


def resolve_project_id(short_id: str) -> str:
    if "_" in short_id:
        return short_id
    projects_dir = PROJECT_ROOT / "projects"
    for d in projects_dir.iterdir():
        if d.is_dir() and d.name.startswith(short_id):
            return d.name
    return short_id


def load_project_info(project_id: str) -> dict:
    config_path = PROJECT_ROOT / "projects" / project_id / "config.yaml"
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    s1_path = (
        PROJECT_ROOT
        / "data"
        / "l1_warm"
        / project_id
        / "checkpoints"
        / "r0_s1_direction_decompose.json"
    )
    s1_data = json.loads(s1_path.read_text(encoding="utf-8")) if s1_path.exists() else {}
    snapshot = s1_data.get("context_snapshot", {})
    s1_output = snapshot.get("last_output_direction_decompose", snapshot.get("output_s1_direction_decompose", {}))

    return {
        "project_id": project_id,
        "name": cfg.get("name", ""),
        "archetype_id": cfg.get("archetype_id", ""),
        "research_direction": cfg.get("research_direction", "").strip(),
        "sub_questions": s1_output.get("sub_questions", []),
        "key_terms": s1_output.get("key_terms", []),
        "scope_include": s1_output.get("scope_boundaries", {}).get("include", ""),
        "scope_exclude": s1_output.get("scope_boundaries", {}).get("exclude", ""),
        "decompose_config": cfg.get("decompose", {}),
    }


async def phase1_custom_dimensional_decompose(
    project_info: dict, custom_axes: dict[str, dict]
) -> dict[str, list[str]]:
    """Phase 1 variant: decompose using project-specific custom axes from config.yaml."""
    research_dir = project_info["research_direction"]
    sub_questions = project_info["sub_questions"]
    key_terms = project_info["key_terms"]
    scope_include = project_info.get("scope_include", "")
    scope_exclude = project_info.get("scope_exclude", "")

    # Build dynamic axis descriptions
    axis_specs = []
    for line_key, line_config in custom_axes.items():
        for axis_key, axis_def in line_config.items():
            if isinstance(axis_def, dict):
                label = axis_def.get("label", axis_key)
                hint = axis_def.get("values_prompt", "")
                axis_specs.append((line_key, axis_key, label, hint))

    axis_prompts = []
    for line_key, axis_key, label, hint in axis_specs:
        full_label = f"{label} ({axis_key})" if hint else label
        axis_prompts.append(f'  "{axis_key}": ["value1", "value2", ...],  // {full_label}')

    prompt = f"""You are a bioinformatics research strategist. Decompose the following research direction
into SPECIFIC dimensional axes that can be cross-combined to generate concrete, executable research topics.

RESEARCH DIRECTION: {research_dir}

EXISTING SUB-QUESTIONS (too generic):
{chr(10).join(f"- {q}" for q in sub_questions)}

KEY TERMS: {', '.join(key_terms)}

SCOPE: include={scope_include}; exclude={scope_exclude}

TASK: For each dimension below, propose 4-8 specific, concrete candidate values.
Each value should be a specific entity (model name, dataset, paradigm), not a category.

Expected JSON structure:
{{
{chr(10).join(axis_prompts)},
    "decomposition_rationale": "why these axes and values"
}}
"""
    result_text = await llm_complete(prompt, temperature=0.3, max_tokens=6000)
    parsed = _parse_json(result_text)
    if not parsed:
        logger.error(f"Failed to parse custom Phase 1 output: {result_text[:200]}")
        return {}

    result: dict[str, list[str]] = {}
    for line_key in custom_axes:
        for axis_key in custom_axes[line_key]:
            if axis_key != "label" and isinstance(custom_axes[line_key][axis_key], dict):
                values = parsed.get(axis_key, [])
                if values:
                    result[axis_key] = values
                    logger.info(f"  {axis_key}: {len(values)} values")

    return result


async def phase1_dimensional_decompose(project_info: dict) -> DimensionAxes:
    research_dir = project_info["research_direction"]
    sub_questions = project_info["sub_questions"]
    key_terms = project_info["key_terms"]
    scope_include = project_info.get("scope_include", "")
    scope_exclude = project_info.get("scope_exclude", "")

    prompt = f"""You are a bioinformatics research strategist. Decompose the following research direction
into SPECIFIC dimensional axes that can be cross-combined to generate concrete, executable research topics.

RESEARCH DIRECTION: {research_dir}

EXISTING SUB-QUESTIONS (too generic):
{chr(10).join(f"- {q}" for q in sub_questions)}

KEY TERMS: {', '.join(key_terms)}

SCOPE: include={scope_include}; exclude={scope_exclude}

TASK: For each dimension below, propose 4-8 specific, concrete candidate values.
Focus on bioinformatics-computational research that can be done with public data.
Each value should be a specific entity (disease name, cell type, dataset, method), not a category.

Return JSON:
{{
    "disease_phenotypes": ["specific disease X", "specific disease Y", ...],
    "cell_types_tissues": ["specific cell type A", "specific tissue B", ...],
    "data_resources": ["specific dataset/cohort C", "specific database D", ...],
    "methods_techniques": ["specific method E", "specific technique F", ...],
    "populations": ["specific population G", "specific population H", ...],
    "decomposition_rationale": "why these axes and values"
}}
"""
    result_text = await llm_complete(prompt, temperature=0.3, max_tokens=3000)
    parsed = _parse_json(result_text)
    if parsed:
        axes = DimensionAxes(
            disease_phenotypes=parsed.get("disease_phenotypes", []),
            cell_types_tissues=parsed.get("cell_types_tissues", []),
            data_resources=parsed.get("data_resources", []),
            methods_techniques=parsed.get("methods_techniques", []),
            populations=parsed.get("populations", []),
        )
        logger.info(f"Phase 1: {len(axes.disease_phenotypes)} diseases, "
                     f"{len(axes.cell_types_tissues)} cell/tissues, "
                     f"{len(axes.data_resources)} data, "
                     f"{len(axes.methods_techniques)} methods, "
                     f"{len(axes.populations)} populations")
        return axes
    else:
        logger.error(f"Failed to parse Phase 1 output: {result_text[:200]}")
        return DimensionAxes()


async def phase1b_formulate_topic(
    project_info: dict, axes: DimensionAxes, disease: str, tissue: str, data: str, method: str, population: str
) -> dict:
    research_dir = project_info["research_direction"]

    prompt = f"""You are a bioinformatics research advisor. Formulate a specific, executable research question
by combining dimensions from a broad research direction.

BROAD DIRECTION: {research_dir}

DIMENSIONS TO COMBINE:
- Disease/Phenotype: {disease}
- Tissue/Cell Type: {tissue}
- Data Resource: {data}
- Method/Technique: {method}
- Population: {population}

Return JSON:
{{
    "research_question": "A specific, publishable research question in 1-2 sentences",
    "search_query": "A concise keyword query for literature search (5-10 words)",
    "rationale": "Why this combination makes a viable research topic (1-2 sentences)"
}}
"""
    result_text = await llm_complete(prompt, temperature=0.4, max_tokens=500)
    parsed = _parse_json(result_text)
    if parsed:
        return parsed
    question = f"Investigate {disease} using {method} in {tissue} with {data} for {population}"
    query = f"{disease} {method} {tissue}"
    return {"research_question": question, "search_query": query, "rationale": "Cross-dimension topic"}


DISEASE_TISSUE_COMPAT: dict[str, set[str]] = {
    "NSCLC": {"lung", "lung_epithelium", "immune", "PBMC", "T_cell", "tumor_microenvironment"},
    "lung cancer": {"lung", "lung_epithelium", "immune", "PBMC", "tumor_microenvironment"},
    "hepatocellular carcinoma": {"liver", "hepatocyte", "liver_tumor", "PBMC"},
    "liver cirrhosis": {"liver", "hepatocyte", "fibroblast", "HSC"},
    "Alzheimer": {"brain_cortex", "microglia", "astrocyte", "neuron", "hippocampus"},
    "Parkinson": {"brain", "substantia_nigra", "neuron", "microglia"},
    "type 2 diabetes": {"pancreas", "islet", "beta_cell", "adipose", "liver"},
    "atherosclerosis": {"artery", "endothelial", "macrophage", "smooth_muscle", "PBMC"},
    "breast cancer": {"breast", "mammary", "tumor_microenvironment", "immune"},
    "rheumatoid arthritis": {"synovium", "fibroblast", "T_cell", "B_cell", "PBMC"},
    "multiple sclerosis": {"brain", "microglia", "oligodendrocyte", "T_cell"},
}
COMPAT_FALLBACK: set[str] = {"PBMC", "immune", "blood", "whole_blood", "cell_line"}


def _check_coherence(disease: str, tissue: str) -> tuple[bool, str]:
    disease_lower = disease.lower()
    tissue_lower = tissue.lower()
    for d_key, compat in DISEASE_TISSUE_COMPAT.items():
        if d_key in disease_lower:
            is_compat = any(tc in tissue_lower for tc in compat)
            if is_compat:
                return True, ""
            return False, f"{d_key} incompatible with {tissue} (expected: {compat})"
    if any(fb.lower() in tissue_lower for fb in COMPAT_FALLBACK):
        return True, ""
    return True, ""


async def _llm_coherence_check(
    disease: str, tissue: str, method: str
) -> tuple[bool, str]:
    prompt = f"""You are a bioinformatics research reviewer. Evaluate whether the following
disease-tissue-method combination is scientifically coherent for a single-cell multi-omics research topic.

Combination:
- Disease: {disease}
- Tissue/Cell Type: {tissue}
- Method: {method}

Is this combination biologically plausible and scientifically meaningful?
Consider: does the disease affect or involve this tissue? Can the method work on this tissue?
Return JSON: {{"coherent": true/false, "reason": "brief explanation in 1 sentence"}}"""
    try:
        raw = await llm_complete(prompt, temperature=0.1, max_tokens=150)
        parsed = _parse_json(raw)
        if parsed:
            coherent = bool(parsed.get("coherent", True))
            reason = parsed.get("reason", "")
            return coherent, reason
    except Exception:
        pass
    return True, "LLM check skipped"


async def phase3_literature_check(
    topic: CandidateTopic, registry: Optional[MCPRegistry], dry_run: bool = False
) -> CandidateTopic:
    if dry_run or registry is None:
        topic.literature_count = 0
        topic.density_score = 0.5
        return topic

    pm = registry.pubmed()
    total_count = 0

    await asyncio.sleep(0.35)

    disease_key = topic.disease.split("(")[0].strip()[:50]
    tissue_key = topic.tissue.split(" ")[0].rstrip(",.")[:15]
    method_key = topic.method.split("(")[0].strip().split(" ")[0]

    search_queries: list[str] = []
    if method_key:
        search_queries.append(f"{method_key} {disease_key}".strip())
    tissue_query = f"{disease_key} {tissue_key}".strip()
    if tissue_query not in search_queries:
        search_queries.append(tissue_query)
    if disease_key not in search_queries:
        search_queries.append(disease_key)

    for sq in search_queries:
        for attempt in range(2):
            try:
                pm_result = await pm.search(sq, retmax=3)
                if pm_result.success and pm_result.data:
                    pm_data = pm_result.data.get("esearchresult", {})
                    count = int(pm_data.get("count", "0"))
                    total_count = max(total_count, count)
                    logger.info(f"PubMed: {sq[:60]}... -> {count} results")
                break
            except Exception as e:
                logger.debug(f"PubMed attempt {attempt+1} failed for '{sq[:50]}': {e}")
                await asyncio.sleep(1.0)
        await asyncio.sleep(0.35)

    topic.literature_count = total_count

    if total_count <= 5:
        topic.density_score = 0.15
    elif total_count <= 30:
        topic.density_score = 0.5
    elif total_count <= 200:
        topic.density_score = 0.9
    elif total_count <= 1000:
        topic.density_score = 0.7
    elif total_count <= 5000:
        topic.density_score = 0.4
    elif total_count <= 20000:
        topic.density_score = 0.30
    elif total_count <= 100000:
        topic.density_score = 0.20
    else:
        topic.density_score = 0.10

    topic.feasibility_score = min(1.0, total_count / 80.0) if total_count > 0 else 0.05
    topic.competitiveness_score = min(1.0, total_count / 5000.0) if total_count > 5 else 0.02
    topic.novelty_score = max(0.1, 1.0 - topic.competitiveness_score) if total_count > 5 else 0.6

    topic.combined_score = (
        topic.density_score * 0.40
        + topic.novelty_score * 0.35
        + topic.feasibility_score * 0.25
    )

    return topic


async def process_project_custom(
    project_info: dict, custom_axes: dict[str, dict], dry_run: bool = False
) -> dict:
    """Process a project using custom decomposition axes from config.yaml."""
    project_id = project_info["project_id"]
    logger.info(f"  Using custom decomposition axes for {project_id}")

    axes_by_line = await phase1_custom_dimensional_decompose(project_info, custom_axes)
    if not axes_by_line:
        logger.error(f"  Custom Phase 1 failed for {project_id}")
        return {"project_id": project_id, "error": "Phase 1 custom failed", "candidates": []}

    registry = None if dry_run else MCPRegistry(project_id)
    candidates: list[CandidateTopic] = []
    global_topic_idx = 0
    max_candidates = 50

    lines = list(custom_axes.items())
    n_lines = max(len(lines), 1)
    per_line = max_candidates // n_lines

    # Build per-line candidates with stratified sampling
    for line_key, line_config in lines:
        axis_keys = [k for k in line_config if isinstance(line_config[k], dict)]
        if not axis_keys:
            continue

        axis_values = [axes_by_line.get(k, [])[:8] for k in axis_keys]
        if not axis_values or not any(axis_values):
            continue

        line_topic_idx = 0
        n_axes = len(axis_values)

        if n_axes == 1:
            for val in axis_values[0]:
                if line_topic_idx >= per_line:
                    break
                dims = {axis_keys[0]: val}
                topic = CandidateTopic(
                    topic_id=f"{project_id}_T{global_topic_idx:03d}",
                    project_id=project_id,
                    research_question=f"Investigate {val} in single-cell genomics",
                    dimensions=dims,
                    search_query=str(val)[:200],
                    rationale=f"Custom decomposition: {line_key}",
                )
                candidates.append(topic)
                global_topic_idx += 1
                line_topic_idx += 1
        else:
            primary_vals = axis_values[0]
            secondary_axes = axis_values[1:]
            per_primary = max(1, per_line // max(len(primary_vals), 1))

            for pi, primary_val in enumerate(primary_vals):
                if line_topic_idx >= per_line:
                    break
                for offset in range(per_primary):
                    if line_topic_idx >= per_line:
                        break
                    combo = [primary_val]
                    for j, sec_vals in enumerate(secondary_axes):
                        si = (pi * 3 + offset * (j + 2)) % max(len(sec_vals), 1)
                        combo.append(sec_vals[si])
                    dims = dict(zip(axis_keys, combo))
                    parts = [str(v) for v in combo if v]
                    search_query = " ".join(parts[:4]) if parts else ""
                    topic = CandidateTopic(
                        topic_id=f"{project_id}_T{global_topic_idx:03d}",
                        project_id=project_id,
                        research_question=f"Investigate {', '.join(parts[:3])} in single-cell genomics",
                        dimensions=dims,
                        search_query=search_query,
                        rationale=f"Custom decomposition: {line_key}",
                    )
                    if isinstance(search_query, str) and search_query.strip():
                        topic = await phase3_literature_check_custom(topic, registry, dry_run, search_query)
                    candidates.append(topic)
                    global_topic_idx += 1
                    line_topic_idx += 1

    if registry:
        await registry.aclose_all()

    candidates.sort(key=lambda c: c.combined_score, reverse=True)

    return {
        "project_id": project_id,
        "dimensions": axes_by_line,
        "custom_axes": True,
        "total_candidates": len(candidates),
        "candidates": [
            {
                "topic_id": c.topic_id,
                "research_question": c.research_question,
                "dimensions": c.dimensions,
                "scores": {
                    "combined": round(c.combined_score, 3),
                    "density": round(c.density_score, 3),
                    "novelty": round(c.novelty_score, 3),
                    "feasibility": round(c.feasibility_score, 3),
                    "competitiveness": round(c.competitiveness_score, 3),
                },
                "literature_count": c.literature_count,
                "literature_unchecked": c.literature_count == -1,
                "combined_score": round(c.combined_score, 3),
                "top_papers": c.literature_top_papers[:3],
                "search_query": c.search_query,
                "rationale": c.rationale,
            }
            for c in candidates
        ],
    }


async def phase3_literature_check_custom(
    topic: CandidateTopic, registry: Optional[MCPRegistry], dry_run: bool, search_query: str
) -> CandidateTopic:
    """Literature check for custom-axes candidates (uses search_query as PubMed query)."""
    if dry_run or registry is None:
        topic.literature_count = 0
        topic.density_score = 0.5
        return topic

    pm = registry.pubmed()
    total_count = 0
    for attempt in range(2):
        try:
            await asyncio.sleep(0.35)
            pm_result = await pm.search(search_query, retmax=3)
            if pm_result.success and pm_result.data:
                pm_data = pm_result.data.get("esearchresult", {})
                total_count = int(pm_data.get("count", "0"))
            break
        except Exception as e:
            logger.debug(f"PubMed custom attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1.0)

    topic.literature_count = total_count
    topic.density_score = 0.5  # neutral default for custom axes
    topic.feasibility_score = min(1.0, total_count / 80.0) if total_count > 0 else 0.05
    topic.competitiveness_score = min(1.0, total_count / 5000.0) if total_count > 5 else 0.02
    topic.novelty_score = max(0.1, 1.0 - topic.competitiveness_score) if total_count > 5 else 0.6
    topic.combined_score = topic.density_score * 0.40 + topic.novelty_score * 0.35 + topic.feasibility_score * 0.25
    return topic


async def process_project(
    project_id: str, dry_run: bool = False
) -> dict:
    logger.info(f"\n{'='*60}")
    project_id = resolve_project_id(project_id)
    logger.info(f"Processing: {project_id}")

    project_info = load_project_info(project_id)
    logger.info(f"  Direction: {project_info['research_direction'][:80]}...")

    decompose_config = project_info.get("decompose_config", {})
    custom_axes = decompose_config.get("custom_axes")

    if custom_axes:
        return await process_project_custom(project_info, custom_axes, dry_run)

    axes = await phase1_dimensional_decompose(project_info)
    if not axes.disease_phenotypes:
        logger.error(f"  Phase 1 failed for {project_id}")
        return {"project_id": project_id, "error": "Phase 1 failed", "candidates": []}

    registry = None if dry_run else MCPRegistry(project_id)

    candidates: list[CandidateTopic] = []
    topic_idx = 0
    max_candidates = 40
    max_search = 30  # literature-search the first 30 (was 20, to cover more diversity)

    diseases_all = axes.disease_phenotypes[:8]
    tissues_all = axes.cell_types_tissues[:8]
    methods_all = axes.methods_techniques[:5]
    populations_all = axes.populations[:4]

    sem = asyncio.Semaphore(3)

    async def process_one(disease: str, tissue: str, method: str, pop: str) -> Optional[CandidateTopic]:
        nonlocal topic_idx
        async with sem:
            topic_idx_local = topic_idx
            topic_idx += 1
            if topic_idx_local >= max_candidates:
                return None

            data = axes.data_resources[topic_idx_local % len(axes.data_resources)] if axes.data_resources else "public"
            tissue_keyword = tissue.split(" ")[0].rstrip(",.") if " " in tissue else tissue[:20]
            topic_info = await phase1b_formulate_topic(project_info, axes, disease, tissue, data, method, pop)

            topic = CandidateTopic(
                topic_id=f"{project_id}_T{topic_idx_local:03d}",
                project_id=project_id,
                research_question=topic_info.get("research_question", ""),
                disease=disease,
                tissue=tissue,
                data_resource=data,
                method=method,
                population=pop,
                search_query=f"{disease.split('(')[0].strip()[:40]} {tissue_keyword}",
                rationale=topic_info.get("rationale", ""),
            )

            coherent, reason = _check_coherence(disease, tissue)
            if not coherent:
                coherent, llm_reason = await _llm_coherence_check(disease, tissue, method)
                if not coherent:
                    logger.info(f"  SKIPPED incoherent: {disease} x {tissue} x {method} ({llm_reason[:60]})")
                    return None

            topic = await phase3_literature_check(topic, registry, dry_run) if topic_idx_local < max_search else topic
            if topic_idx_local >= max_search:
                topic.density_score = 0.5
                topic.combined_score = 0.3
                topic.literature_count = -1
            return topic

    tasks = []
    # Stratified allocation: each disease gets max_candidates/n_diseases candidates,
    # with methods and tissues rotated to ensure balanced coverage.
    n_diseases = max(len(diseases_all), 1)
    n_methods = max(len(methods_all), 1)
    n_tissues = max(len(tissues_all), 1)
    n_pops = max(len(populations_all), 1)
    per_disease = max(1, max_candidates // n_diseases)
    combo_list: list[tuple] = []
    for di, disease in enumerate(diseases_all):
        if len(combo_list) >= max_candidates:
            break
        for offset in range(per_disease + 1):
            if len(combo_list) >= max_candidates:
                break
            mi = (di + offset) % n_methods
            ti = (di + offset * 3) % n_tissues
            pi = (di + offset * 5) % n_pops
            entry = (di, ti, mi, pi, disease, tissues_all[ti], methods_all[mi], populations_all[pi])
            if entry not in combo_list:
                combo_list.append(entry)
    # Fill remaining slots with cross-disease rotation
    offset_base = per_disease + 1
    while len(combo_list) < max_candidates:
        di = len(combo_list) % n_diseases
        mi = (offset_base) % n_methods
        ti = (offset_base * 2) % n_tissues
        pi = (offset_base * 3) % n_pops
        entry = (di, ti, mi, pi, diseases_all[di], tissues_all[ti], methods_all[mi], populations_all[pi])
        if entry not in combo_list:
            combo_list.append(entry)
        offset_base += 1

    for combo in combo_list[:max_candidates]:
        tasks.append(process_one(combo[4], combo[5], combo[6], combo[7]))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            logger.warning(f"  Candidate {i} failed: {r}")
    candidates = [r for r in results if r is not None and not isinstance(r, BaseException)]

    candidates.sort(key=lambda c: c.combined_score, reverse=True)

    if registry:
        await registry.aclose_all()

    return {
        "project_id": project_id,
        "dimensions": {
            "disease_phenotypes": axes.disease_phenotypes,
            "cell_types_tissues": axes.cell_types_tissues,
            "data_resources": axes.data_resources,
            "methods_techniques": axes.methods_techniques,
            "populations": axes.populations,
        },
        "total_candidates": len(candidates),
        "candidates": [
            {
                "topic_id": c.topic_id,
                "research_question": c.research_question,
                "dimensions": {
                    "disease": c.disease,
                    "tissue": c.tissue,
                    "data_resource": c.data_resource,
                    "method": c.method,
                    "population": c.population,
                },
                "scores": {
                    "combined": round(c.combined_score, 3),
                    "density": round(c.density_score, 3),
                    "novelty": round(c.novelty_score, 3),
                    "feasibility": round(c.feasibility_score, 3),
                    "competitiveness": round(c.competitiveness_score, 3),
                },
                "literature_count": c.literature_count,
                "literature_unchecked": c.literature_count == -1,
                "combined_score": round(c.combined_score, 3),
                "top_papers": c.literature_top_papers[:3],
                "search_query": c.search_query,
                "rationale": c.rationale,
            }
            for c in candidates
        ],
    }


async def main():
    parser = argparse.ArgumentParser(description="Dimension decomposition and topic screening")
    parser.add_argument("--projects", type=str, default="p01_gwas_perturb_seq,p06_digital_immune",
                        help="comma-separated project ids")
    parser.add_argument("--dry-run", action="store_true",
                        help="skip MCP literature searches (LLM only)")
    args = parser.parse_args()

    settings.ensure_dirs()
    project_ids = [p.strip() for p in args.projects.split(",")]

    results = []
    for pid in project_ids:
        result = await process_project(pid, dry_run=args.dry_run)
        results.append(result)

    output_path = PROJECT_ROOT / "data" / "decompose_pilot_results.json"
    existing = {}
    if output_path.exists():
        try:
            existing_list = json.loads(output_path.read_text(encoding="utf-8"))
            for e in existing_list:
                existing[e["project_id"]] = e
        except (json.JSONDecodeError, IOError):
            pass
    for r in results:
        existing[r["project_id"]] = r
    merged = list(existing.values())
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in results:
        _safe_print(f"\n{'='*60}")
        _safe_print(f"Project: {r['project_id']}  |  Candidates: {r.get('total_candidates', 0)}")
        if "dimensions" in r:
            dims = r["dimensions"]
            _safe_print(f"  Diseases: {', '.join(dims.get('disease_phenotypes', [])[:5])}")
            _safe_print(f"  Tissues:  {', '.join(dims.get('cell_types_tissues', [])[:5])}")
            _safe_print(f"  Methods:  {', '.join(dims.get('methods_techniques', [])[:4])}")
            _safe_print(f"  Data:     {', '.join(dims.get('data_resources', [])[:4])}")
        _safe_print(f"\n  Top-10 candidates:")
        for i, c in enumerate(r.get("candidates", [])[:10]):
            _safe_print(f"  {i+1}. [{c['scores']['combined']:.3f}] {c['research_question'][:100]}")
            dims = c.get("dimensions", {})
            _safe_print(f"      disease={dims.get('disease','')} | tissue={dims.get('tissue','')} | "
                       f"method={dims.get('method','')} | lit={c['literature_count']}")

    _safe_print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
