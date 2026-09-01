from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from shared.core.config import settings


class BudgetPhase(str, Enum):
    SCOPING = "scoping"
    DISCOVERY = "discovery"
    EXTRACTION = "extraction"
    SYNTHESIS = "synthesis"


@dataclass
class BudgetAllocation:
    total: int
    scoping: int
    discovery: int
    extraction: int
    synthesis: int

    @classmethod
    def from_settings(cls) -> "BudgetAllocation":
        t = settings.total_token_budget
        return cls(
            total=t,
            scoping=int(t * settings.budget_scoping),
            discovery=int(t * settings.budget_discovery),
            extraction=int(t * settings.budget_extraction),
            synthesis=int(t * settings.budget_synthesis),
        )


@dataclass
class PhaseUsage:
    allocated: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.allocated - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.allocated

    def consume(self, tokens: int) -> None:
        self.used += tokens


@dataclass
class TokenBudget:
    project_id: str
    allocation: BudgetAllocation = field(default_factory=BudgetAllocation.from_settings)
    phases: dict[BudgetPhase, PhaseUsage] = field(default_factory=dict)
    current_phase: BudgetPhase = BudgetPhase.SCOPING
    total_used: int = 0

    def __post_init__(self) -> None:
        if not self.phases:
            self.phases = {
                BudgetPhase.SCOPING: PhaseUsage(self.allocation.scoping),
                BudgetPhase.DISCOVERY: PhaseUsage(self.allocation.discovery),
                BudgetPhase.EXTRACTION: PhaseUsage(self.allocation.extraction),
                BudgetPhase.SYNTHESIS: PhaseUsage(self.allocation.synthesis),
            }

    def set_phase(self, phase: BudgetPhase) -> None:
        self.current_phase = phase

    def consume(self, tokens: int, phase: Optional[BudgetPhase] = None) -> None:
        p = phase or self.current_phase
        self.phases[p].consume(tokens)
        self.total_used += tokens

    @property
    def remaining(self) -> int:
        return max(0, self.allocation.total - self.total_used)

    @property
    def exhausted(self) -> bool:
        return self.total_used >= self.allocation.total

    @property
    def current_phase_exhausted(self) -> bool:
        return self.phases[self.current_phase].exhausted

    def phase_remaining(self, phase: Optional[BudgetPhase] = None) -> int:
        return self.phases[phase or self.current_phase].remaining

    def snapshot(self) -> dict:
        return {
            "project_id": self.project_id,
            "total_used": self.total_used,
            "total_budget": self.allocation.total,
            "remaining": self.remaining,
            "current_phase": self.current_phase.value,
            "phases": {
                p.value: {"allocated": pu.allocated, "used": pu.used, "remaining": pu.remaining}
                for p, pu in self.phases.items()
            },
        }
