"""Deep-read evidence-ledger schemas.

Adapted from the human paper-reading methodology and the automated design doc.
Core principle: every claim, fact, and judgment is traceable back to a source locator.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from shared.skills.base_skill import SkillInput, SkillOutput

# ---------------------------------------------------------------------------
# Atomic data types
# ---------------------------------------------------------------------------

class SourceLocator(BaseModel):
    """Where in the paper a piece of information was found."""
    section: str = ""
    page: Optional[int] = None
    table_or_figure: Optional[str] = None
    equation: Optional[str] = None
    quote_span: str = ""


class ExtractedFact(BaseModel):
    """A verified fact extracted from the paper. Answers "what did the paper say"."""
    fact_id: str = ""
    category: Literal["metadata", "problem", "method", "experiment", "limitation", "result"] = "method"
    statement: str = ""
    source_locator: SourceLocator = Field(default_factory=SourceLocator)
    evidence_status: Literal[
        "directly_stated", "strictly_derived", "inferred",
        "externally_supported", "author_claim", "unresolved",
    ] = "author_claim"


class AuthorClaim(BaseModel):
    """An author's claim about their work. Separated from verified facts."""
    claim_id: str = ""
    text: str = ""
    claim_origin: Literal["author", "abstract", "conclusion", "reviewer"] = "author"
    source_locator: SourceLocator = Field(default_factory=SourceLocator)


class ClaimJudgment(BaseModel):
    """Judgment of a claim's evidential support (claim-evidence audit)."""
    judgment_id: str = ""
    claim_id: str = ""  # references AuthorClaim
    subject: str = ""
    verdict: Literal["fully_supported", "partially_supported", "insufficient", "no_evidence", "conflicting"] = "insufficient"
    confidence: Literal["high", "medium", "low"] = "medium"
    supporting_evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    missing_controls: list[str] = Field(default_factory=list)
    allowed_wording: str = ""
    forbidden_wording: str = ""
    human_review_required: bool = False


class FormulaAnalysis(BaseModel):
    """Formula derivation chain with internal and external parents."""
    formula_id: str = ""
    expression_latex: str = ""
    role: Literal["training_objective", "inference", "architecture", "loss", "regularization", "other"] = "other"
    variables: list[str] = Field(default_factory=list)
    internal_parents: list[str] = Field(default_factory=list)
    external_parents: list[str] = Field(default_factory=list)
    derivation_steps: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    provenance_class: Literal["strict", "approximate", "heuristic", "theory_plus_heuristic", "unresolved"] = "unresolved"
    confidence: float = 0.5
    requires_human_review: bool = False


class ExperimentAnalysis(BaseModel):
    """Single experiment result with fairness checks."""
    experiment_id: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    dataset: str = ""
    split: str = ""
    metric: str = ""
    method_value: Optional[float] = None
    baseline_value: Optional[float] = None
    absolute_delta: Optional[float] = None
    relative_delta_pct: Optional[float] = None
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    fairness: dict[str, Any] = Field(default_factory=dict)
    source_locator: SourceLocator = Field(default_factory=SourceLocator)
    interpretation_limits: list[str] = Field(default_factory=list)


class CriticalAssessment(BaseModel):
    """Overall critical assessment of the paper."""
    credibility: Literal["high", "medium", "low"] = "medium"
    methodology_issues: list[str] = Field(default_factory=list)
    reproducibility_concerns: list[str] = Field(default_factory=list)
    contribution_level: Literal["breakthrough", "significant", "incremental", "minor"] = "incremental"
    open_problems: list[str] = Field(default_factory=list)
    overall_strength: str = ""


class QualityGateResult(BaseModel):
    """Programmatic quality gate results (not LLM)."""
    passed: bool = True
    citation_count: int = 0
    resolvable_citation_count: int = 0
    claims_with_evidence: int = 0
    claims_without_evidence: int = 0
    numerical_consistency_errors: list[str] = Field(default_factory=list)
    author_claim_mislabeled_as_fact: list[str] = Field(default_factory=list)
    human_review_triggers: list[str] = Field(default_factory=list)
    needs_human_review: bool = False


# ---------------------------------------------------------------------------
# Per-paper deep-read note (the core artifact)
# ---------------------------------------------------------------------------

class DeepReadNote(BaseModel):
    """Complete deep-reading analysis for one paper."""
    paper_id: str = ""
    paper_title: str = ""
    reading_depth: Literal["tier1", "tier2"] = "tier1"

    facts: list[ExtractedFact] = Field(default_factory=list)
    claims: list[AuthorClaim] = Field(default_factory=list)
    judgments: list[ClaimJudgment] = Field(default_factory=list)
    formulas: list[FormulaAnalysis] = Field(default_factory=list)
    experiments: list[ExperimentAnalysis] = Field(default_factory=list)
    critical_assessment: Optional[CriticalAssessment] = None

    quality_gate: QualityGateResult = Field(default_factory=QualityGateResult)
    needs_human_review: bool = False
    human_review_items: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Skill input / output
# ---------------------------------------------------------------------------

class DeepReadSkillInput(SkillInput):
    """Input for s6c_deep_read: papers to deep-read."""
    papers: list[dict[str, Any]] = Field(default_factory=list)
    max_papers: int = 5
    max_tier2_papers: int = 2
    candidate_dimensions: dict[str, Any] = Field(default_factory=dict)


class DeepReadSkillOutput(SkillOutput):
    """Output from s6c_deep_read: deep-read notes per paper."""
    notes: list[dict[str, Any]] = Field(default_factory=list)
    papers_processed: int = 0
    papers_tier2: int = 0
    papers_needing_human_review: int = 0
