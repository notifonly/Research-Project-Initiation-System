from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Type

from pydantic import BaseModel

from shared.core.context import ContextManager
from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase, TokenBudget
from shared.mcp.registry import MCPRegistry

if TYPE_CHECKING:
    from shared.evidence.card_store import CardStore


class SkillInput(BaseModel):
    """Base input schema for all skills. Allows arbitrary extra fields so the
    loop engine can accumulate outputs from multiple prior skills into one input."""
    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

    project_id: str = ""
    research_direction: str = ""
    archetype: str = ""
    context_hint: str = ""


class SkillOutput(BaseModel):
    """Base output schema for all skills. Allows arbitrary extra fields."""
    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}
    skill_name: str = ""
    success: bool = True
    error: Optional[str] = None
    metrics: dict[str, Any] = {}


@dataclass
class SkillContext:
    """Runtime context passed to each skill execution."""
    project_id: str
    mcp_registry: MCPRegistry
    card_store: CardStore
    context: ContextManager
    budget: TokenBudget
    archetype_config: dict[str, Any] = field(default_factory=dict)
    scratch: dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """Base class for all skills. Each skill has: input_schema, output_schema, pre_check, execute, quality_gate, metrics."""

    name: str = "base"
    description: str = ""
    uses_llm: bool = True
    budget_phase: BudgetPhase = BudgetPhase.EXTRACTION
    input_schema: Type[SkillInput] = SkillInput
    output_schema: Type[SkillOutput] = SkillOutput

    def __init__(self) -> None:
        self.logger = get_logger()
        self._metrics: dict[str, Any] = {}

    async def pre_check(self, inp: SkillInput, ctx: SkillContext) -> bool:
        return True

    @abstractmethod
    async def execute(self, inp: SkillInput, ctx: SkillContext) -> SkillOutput:
        ...

    async def quality_gate(self, output: SkillOutput, ctx: SkillContext) -> bool:
        return output.success

    def metrics(self) -> dict[str, Any]:
        return dict(self._metrics)

    async def run(self, inp: SkillInput, ctx: SkillContext) -> SkillOutput:
        self._metrics = {}
        try:
            if not await self.pre_check(inp, ctx):
                out = self.output_schema(skill_name=self.name, success=False, error="pre_check failed")
                self._metrics["pre_check_failed"] = True
                return out
            output = await self.execute(inp, ctx)
            output.skill_name = self.name
            if not await self.quality_gate(output, ctx):
                output.success = False
                if not output.error:
                    output.error = "quality_gate failed"
                self._metrics["quality_gate_failed"] = True
            self._metrics["completed"] = True
            output.metrics.update(self._metrics)
            return output
        except Exception as e:
            self.logger.error(f"Skill {self.name} failed: {e}")
            self._metrics["error"] = str(e)
            return self.output_schema(skill_name=self.name, success=False, error=str(e))

    async def _llm(self, prompt: str, ctx: SkillContext, system: Optional[str] = None, structured: Optional[type] = None) -> Any:
        from shared.core.llm_client import llm_complete, llm_structured
        if structured:
            return await llm_structured(prompt, structured, system=system, budget=ctx.budget, phase=self.budget_phase)
        return await llm_complete(prompt, system=system, budget=ctx.budget, phase=self.budget_phase)
