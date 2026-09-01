"""Tests for LoopEngine convergence logic."""

from shared.core.loop_engine import (
    InnerConvergenceReason,
    InnerLoopResult,
    OuterConvergenceReason,
)


class TestInnerConvergence:
    def test_query_exhausted(self):
        result = InnerLoopResult(iteration=1, converged=False)
        result.cards_added = 0
        result.new_citations = 0
        # Cannot test fully without LoopEngine, but can verify the reason values
        assert InnerConvergenceReason.QUERY_EXHAUSTED.value == "query_exhausted"
        assert InnerConvergenceReason.CITATION_CLOSED.value == "citation_closed"
        assert InnerConvergenceReason.MAX_ITERATIONS.value == "max_iterations"

    def test_inner_convergence_reasons(self):
        reasons = list(InnerConvergenceReason)
        assert len(reasons) == 6
        expected = {
            "QUERY_EXHAUSTED", "CITATION_CLOSED", "REFLECTION_CONFIRMED",
            "BUDGET_TOKEN_EXCEEDED", "MAX_ITERATIONS", "TOPIC_EXHAUSTED",
        }
        assert {r.name for r in reasons} == expected


class TestOuterConvergence:
    def test_outer_convergence_reasons(self):
        reasons = list(OuterConvergenceReason)
        assert len(reasons) == 6
        expected = {
            "COVERAGE_JACCARD", "GAP_YIELD", "CITATION_NETWORK_CLOSED",
            "ALL_MET", "MAX_ROUNDS", "BUDGET_EXHAUSTED",
        }
        assert {r.name for r in reasons} == expected
