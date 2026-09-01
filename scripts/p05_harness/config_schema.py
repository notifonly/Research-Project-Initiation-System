"""Pydantic schema for P05 harness config.yaml validation."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class MCPConfig(BaseModel):
    search_sources: list[str] = Field(
        default=["semantic_scholar", "pubmed", "biorxiv", "arxiv"],
        description="MCP search sources in priority order",
    )
    max_per_source: int = Field(default=10, ge=1, le=100, description="Max results per source")
    year_range: str = Field(default="2022-", description="Year filter, e.g. '2022-' or '2022-2024'")
    recent_boost_year: int = Field(default=2024, ge=2000, le=2100)
    code_sources: list[str] = Field(
        default=["github", "huggingface", "papers_with_code"],
        description="Code repository sources",
    )


class LoopConfig(BaseModel):
    max_iterations: int = Field(default=3, ge=1, le=10, description="Max critique-refine iterations")
    pass_threshold: float = Field(default=4.0, ge=1.0, le=5.0, description="Pass/fail score cutoff")
    min_dimension_score: float = Field(default=3.0, ge=1.0, le=5.0, description="Min per-dimension score")
    stagnation_limit: int = Field(default=2, ge=1, le=5, description="Rounds unchanged before early exit")
    max_concurrent_candidates: int = Field(default=3, ge=1, le=20, description="Max parallel candidates")


class NoveltyCheckConfig(BaseModel):
    enabled: bool = True
    max_claims: int = Field(default=5, ge=1, le=20)
    queries_per_claim: int = Field(default=4, ge=1, le=10)
    top_k_papers: int = Field(default=15, ge=1, le=50)
    max_per_source: int = Field(default=10, ge=1, le=50)
    recent_boost_year: int = Field(default=2024, ge=2000, le=2100)
    reposition_max_attempts: int = Field(default=1, ge=0, le=5)


class RubricDimension(BaseModel):
    weight: float = Field(ge=0.0, le=1.0)
    label_zh: str = Field(min_length=1)
    label_en: str = Field(min_length=1)


_VALID_RUBRIC_KEYS = frozenset({
    "literature_coverage", "technical_feasibility", "innovation_clarity",
    "data_accessibility", "gap_alignment", "evaluation_rigor",
})


class RubricConfig(BaseModel):
    literature_coverage: RubricDimension = Field(
        default=RubricDimension(weight=0.20, label_zh="文献覆盖度", label_en="Literature Coverage")
    )
    technical_feasibility: RubricDimension = Field(
        default=RubricDimension(weight=0.20, label_zh="技术可行性", label_en="Technical Feasibility")
    )
    innovation_clarity: RubricDimension = Field(
        default=RubricDimension(weight=0.20, label_zh="创新性清晰度", label_en="Innovation Clarity")
    )
    data_accessibility: RubricDimension = Field(
        default=RubricDimension(weight=0.15, label_zh="数据可及性", label_en="Data Accessibility")
    )
    gap_alignment: RubricDimension = Field(
        default=RubricDimension(weight=0.10, label_zh="缺口对齐度", label_en="Gap Alignment")
    )
    evaluation_rigor: RubricDimension = Field(
        default=RubricDimension(weight=0.15, label_zh="评估严谨性", label_en="Evaluation Rigor")
    )

    @model_validator(mode="after")
    def _check_weights_sum(self) -> RubricConfig:
        total = sum(
            getattr(self, k).weight
            for k in _VALID_RUBRIC_KEYS
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Rubric dimension weights must sum to 1.0, got {total:.3f}")
        return self


class CandidatesConfig(BaseModel):
    deep_analysis_count: int = Field(default=10, ge=1, le=100)
    top_n_by_score: bool = True


class OutputConfig(BaseModel):
    dir: str = Field(default="data/harness_output", description="Output directory relative to project root")


class HarnessConfig(BaseModel):
    """Validated schema for scripts/p05_harness/config.yaml."""

    project_id: str = Field(default="p05_sc_multiomics_ai", min_length=1)
    harness_name: str = Field(default="P05 Research Plan Quality Harness", min_length=1)

    mcp: MCPConfig = Field(default_factory=MCPConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    novelty_check: NoveltyCheckConfig = Field(default_factory=NoveltyCheckConfig)
    rubric: RubricConfig = Field(default_factory=RubricConfig)
    candidates: CandidatesConfig = Field(default_factory=CandidatesConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


_CONFIG_MANIFEST = {
    "project_id": {"type": "str", "required": True, "desc": "Project identifier"},
    "harness_name": {"type": "str", "required": True, "desc": "Display name for this harness run"},
    "mcp.search_sources": {"type": "list[str]", "valid": ["semantic_scholar", "pubmed", "biorxiv", "arxiv"], "desc": "Prioritized search sources"},
    "mcp.max_per_source": {"type": "int", "range": "1-100", "desc": "Max papers per source per search"},
    "mcp.year_range": {"type": "str", "example": "2022-", "desc": "Year filter range"},
    "mcp.recent_boost_year": {"type": "int", "range": "2000-2100", "desc": "Papers from this year get recency boost"},
    "mcp.code_sources": {"type": "list[str]", "desc": "Code repo search sources"},
    "loop.max_iterations": {"type": "int", "range": "1-10", "desc": "Max critique-refine iterations per candidate"},
    "loop.pass_threshold": {"type": "float", "range": "1.0-5.0", "desc": "Weighted score pass cutoff"},
    "loop.min_dimension_score": {"type": "float", "range": "1.0-5.0", "desc": "Per-dimension minimum score to pass"},
    "loop.stagnation_limit": {"type": "int", "range": "1-5", "desc": "Rounds with no improvement before early exit"},
    "loop.max_concurrent_candidates": {"type": "int", "range": "1-20", "desc": "Max parallel candidate processing"},
    "novelty_check.enabled": {"type": "bool", "desc": "Enable adversarial novelty verification (Phase 1.5)"},
    "novelty_check.max_claims": {"type": "int", "range": "1-20", "desc": "Max innovation claims to extract"},
    "novelty_check.queries_per_claim": {"type": "int", "range": "1-10", "desc": "Search queries per claim"},
    "novelty_check.top_k_papers": {"type": "int", "range": "1-50", "desc": "Top papers to check overlap against"},
    "novelty_check.max_per_source": {"type": "int", "range": "1-50", "desc": "Max papers per source in novelty search"},
    "novelty_check.recent_boost_year": {"type": "int", "range": "2000-2100", "desc": "Recent year for novelty boost"},
    "novelty_check.reposition_max_attempts": {"type": "int", "range": "0-5", "desc": "Max repositioning retries if scooped"},
    "rubric.<dim>.weight": {"type": "float", "range": "0.0-1.0", "desc": "Dimension weight (must sum to 1.0 across 6 dims)"},
    "rubric.<dim>.label_zh": {"type": "str", "desc": "Chinese dimension label"},
    "rubric.<dim>.label_en": {"type": "str", "desc": "English dimension label"},
    "candidates.deep_analysis_count": {"type": "int", "range": "1-100", "desc": "Number of top candidates for deep analysis"},
    "candidates.top_n_by_score": {"type": "bool", "desc": "Sort candidates by combined score descending"},
    "output.dir": {"type": "str", "desc": "Output directory relative to project root"},
}


def load_harness_config(config_path: str | None = None) -> HarnessConfig:
    """Load and validate the harness config from YAML.

    Returns a validated HarnessConfig or raises ValidationError.
    """
    import yaml
    from pathlib import Path

    if config_path is None:
        from shared.core.config import PROJECT_ROOT
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return HarnessConfig(**raw)


def get_config_manifest() -> dict:
    """Return the human-readable config key manifest for documentation."""
    return dict(_CONFIG_MANIFEST)


__all__ = [
    "HarnessConfig", "MCPConfig", "LoopConfig", "NoveltyCheckConfig",
    "RubricConfig", "RubricDimension", "CandidatesConfig", "OutputConfig",
    "load_harness_config", "get_config_manifest",
]
