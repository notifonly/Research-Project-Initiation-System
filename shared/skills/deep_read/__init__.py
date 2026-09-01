"""Deep-reading skill: evidence-ledger schemas, quality gates, expression mapper."""

from shared.skills.deep_read.schemas import (
    SourceLocator,
    ExtractedFact,
    AuthorClaim,
    ClaimJudgment,
    FormulaAnalysis,
    ExperimentAnalysis,
    CriticalAssessment,
    QualityGateResult,
    DeepReadNote,
    DeepReadSkillInput,
    DeepReadSkillOutput,
)
from shared.skills.deep_read.quality_gates import (
    validate_deep_read_note,
    GateResult,
)
from shared.skills.deep_read.expression_mapper import (
    get_allowed_wording,
    EXPRESSION_RULES,
)

__all__ = [
    "SourceLocator",
    "ExtractedFact",
    "AuthorClaim",
    "ClaimJudgment",
    "FormulaAnalysis",
    "ExperimentAnalysis",
    "CriticalAssessment",
    "QualityGateResult",
    "DeepReadNote",
    "DeepReadSkillInput",
    "DeepReadSkillOutput",
    "validate_deep_read_note",
    "GateResult",
    "get_allowed_wording",
    "EXPRESSION_RULES",
]
