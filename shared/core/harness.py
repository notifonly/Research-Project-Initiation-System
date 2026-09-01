from __future__ import annotations

import asyncio
import json
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from shared.core.config import settings
from shared.core.context import ContextManager
from shared.core.logging_setup import get_logger
from shared.core.provenance import ProvenancePipeline, ProvenanceResult
from shared.core.token_budget import TokenBudget
from shared.mcp.registry import MCPRegistry
if TYPE_CHECKING:
    from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

if TYPE_CHECKING:
    from shared.evidence.base_card import BaseEvidenceCard
    from shared.evidence.card_store import CardStore

logger = get_logger()


class BreakpointType(str, Enum):
    BP1_DIRECTION_DECOMPOSE = "bp1_direction_decompose"
    BP2_LOCUS_TERMINOLOGY = "bp2_locus_terminology"
    BP3_L1_TO_L2 = "bp3_l1_to_l2"
    BP4_READING_LIST = "bp4_reading_list"
    BP5_EVIDENCE_CARD_OVERVIEW = "bp5_evidence_card_overview"
    BP6_GAP_HYPOTHESIS = "bp6_gap_hypothesis"
    BP7_FINAL_MAP = "bp7_final_map"


@dataclass
class BreakpointEvent:
    bp_type: BreakpointType
    project_id: str
    step_name: str
    data: dict[str, Any] = field(default_factory=dict)
    decision: str = "continue"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bp_type": self.bp_type.value,
            "project_id": self.project_id,
            "step_name": self.step_name,
            "data": self.data,
            "decision": self.decision,
        }


BreakpointHandler = Callable[[BreakpointEvent], "BreakpointEvent"]


class SubAgentError(Exception):
    pass


class SubAgentTimeoutError(SubAgentError):
    pass


class MCPFailureError(SubAgentError):
    pass


class LLMParseError(SubAgentError):
    pass


@dataclass
class SubAgentResult:
    agent_id: str
    success: bool
    output: Optional[SkillOutput] = None
    error: Optional[str] = None
    error_type: str = ""
    duration_s: float = 0.0
    tokens_used: int = 0


class SubAgent:
    """Isolated execution unit for a single skill invocation.

    Each sub-agent has its own scratch directory, context snapshot, and
    fault isolation boundary. Failures in one sub-agent do not crash siblings.
    """

    def __init__(
        self,
        agent_id: str,
        project_id: str,
        skill: BaseSkill,
        scratch_dir: Path,
        timeout_s: float = 120.0,
    ) -> None:
        self.agent_id = agent_id
        self.project_id = project_id
        self.skill = skill
        self.scratch_dir = scratch_dir
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s
        self.logger = get_logger(project_id)

    async def run(self, inp: SkillInput, ctx: SkillContext) -> SubAgentResult:
        import time

        t0 = time.monotonic()
        try:
            output = await asyncio.wait_for(
                self.skill.run(inp, ctx),
                timeout=self.timeout_s,
            )
            elapsed = time.monotonic() - t0
            if not output.success:
                return SubAgentResult(
                    agent_id=self.agent_id,
                    success=False,
                    output=output,
                    error=output.error or "skill returned failure",
                    error_type="skill_failure",
                    duration_s=elapsed,
                )
            self._persist_scratch(output)
            return SubAgentResult(
                agent_id=self.agent_id,
                success=True,
                output=output,
                duration_s=elapsed,
            )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            self.logger.error(f"SubAgent {self.agent_id} timed out after {self.timeout_s}s")
            return SubAgentResult(
                agent_id=self.agent_id,
                success=False,
                error=f"Timeout after {self.timeout_s}s",
                error_type="timeout",
                duration_s=elapsed,
            )
        except Exception as e:
            elapsed = time.monotonic() - t0
            err_type = self._classify_error(e)
            self.logger.error(
                f"SubAgent {self.agent_id} failed ({err_type}): {e}\n{traceback.format_exc()}"
            )
            return SubAgentResult(
                agent_id=self.agent_id,
                success=False,
                error=str(e),
                error_type=err_type,
                duration_s=elapsed,
            )

    @staticmethod
    def _classify_error(e: Exception) -> str:
        msg = str(e).lower()
        if "timeout" in msg or "timed out" in msg:
            return "timeout"
        if "mcp" in msg or "httpx" in msg or "connection" in msg:
            return "mcp_failure"
        if "json" in msg or "parse" in msg or "decode" in msg:
            return "llm_parse"
        return "unknown"

    def _persist_scratch(self, output: SkillOutput) -> None:
        try:
            snap_path = self.scratch_dir / f"{self.agent_id}_output.json"
            snap_path.write_text(
                json.dumps(
                    {
                        "agent_id": self.agent_id,
                        "skill_name": output.skill_name,
                        "success": output.success,
                        "metrics": output.metrics,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass


class Harness:
    """The harness layer: sub-agent isolation, fault handling, breakpoints, provenance.

    Responsibilities:
    1. Spawn sub-agents for skill execution with isolation + fault tolerance
    2. Fire breakpoints at defined points and wait for human decision (if enabled)
    3. Run provenance pipeline on extracted evidence cards
    4. Manage scratch directories for sub-agent artifacts
    """

    def __init__(
        self,
        project_id: str,
        mcp_registry: MCPRegistry,
        card_store: CardStore,
        context: ContextManager,
        budget: TokenBudget,
        archetype_config: dict[str, Any],
        max_sub_agents: int = 3,
        breakpoint_handler: Optional[BreakpointHandler] = None,
    ) -> None:
        self.project_id = project_id
        self.mcp_registry = mcp_registry
        self.card_store = card_store
        self.context = context
        self.budget = budget
        self.archetype_config = archetype_config
        self.max_sub_agents = max_sub_agents
        self.breakpoint_handler = breakpoint_handler
        self.scratch_root = settings.l0_cold_dir / project_id / "sub_agents"
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        self.provenance = ProvenancePipeline()
        self._sub_agent_counter = 0
        self._semaphore = asyncio.Semaphore(max_sub_agents)
        self.logger = get_logger(project_id)

    def make_skill_context(self, scratch: Optional[dict[str, Any]] = None) -> SkillContext:
        from shared.skills.base_skill import SkillContext
        return SkillContext(
            project_id=self.project_id,
            mcp_registry=self.mcp_registry,
            card_store=self.card_store,
            context=self.context,
            budget=self.budget,
            archetype_config=self.archetype_config,
            scratch=scratch or {},
        )

    async def run_skill(
        self,
        skill: BaseSkill,
        inp: SkillInput,
        scratch: Optional[dict[str, Any]] = None,
        timeout_s: float = 120.0,
    ) -> SubAgentResult:
        self._sub_agent_counter += 1
        agent_id = f"{skill.name}_{self._sub_agent_counter:04d}"
        sub_agent = SubAgent(
            agent_id=agent_id,
            project_id=self.project_id,
            skill=skill,
            scratch_dir=self.scratch_root / agent_id,
            timeout_s=timeout_s,
        )
        ctx = self.make_skill_context(scratch)
        async with self._semaphore:
            result = await sub_agent.run(inp, ctx)
        if result.success and result.output:
            self.context.warm_to_l2(f"last_output_{skill.name}", result.output.model_dump())
        return result

    async def run_skills_parallel(
        self,
        skills_and_inputs: list[tuple[BaseSkill, SkillInput]],
        scratch: Optional[dict[str, Any]] = None,
        timeout_s: float = 120.0,
    ) -> list[SubAgentResult]:
        tasks = []
        for skill, inp in skills_and_inputs:
            tasks.append(self.run_skill(skill, inp, scratch, timeout_s))
        return await asyncio.gather(*tasks)

    def fire_breakpoint(
        self,
        bp_type: BreakpointType,
        step_name: str,
        data: Optional[dict[str, Any]] = None,
    ) -> BreakpointEvent:
        event = BreakpointEvent(
            bp_type=bp_type,
            project_id=self.project_id,
            step_name=step_name,
            data=data or {},
        )
        if not settings.enable_breakpoints:
            event.decision = "continue"
            return event
        if self.breakpoint_handler is not None:
            try:
                event = self.breakpoint_handler(event)
            except Exception as e:
                self.logger.warning(f"Breakpoint handler error: {e}")
                event.decision = "continue"
        else:
            self.logger.info(f"Breakpoint {bp_type.value} hit (no handler, auto-continue)")
            event.decision = "continue"
        self._log_breakpoint(event)
        return event

    def _log_breakpoint(self, event: BreakpointEvent) -> None:
        bp_path = self.scratch_root.parent / "breakpoints.jsonl"
        try:
            with bp_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def run_provenance(self, cards: list[BaseEvidenceCard]) -> list[ProvenanceResult]:
        if not cards:
            return []
        results = self.provenance.validate_batch(cards)
        error_count = sum(
            1 for r in results for i in r.issues if i.severity == "error"
        )
        warning_count = sum(
            1 for r in results for i in r.issues if i.severity == "warning"
        )
        self.logger.info(
            f"Provenance: {len(results)} cards, {error_count} errors, {warning_count} warnings"
        )
        self._persist_provenance(results)
        return results

    def _persist_provenance(self, results: list[ProvenanceResult]) -> None:
        prov_path = self.scratch_root.parent / "provenance_report.json"
        try:
            prov_path.write_text(
                json.dumps(
                    [r.to_dict() for r in results],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def set_provenance_llm_backtrace(self, fn: Callable[..., Any]) -> None:
        self.provenance.set_llm_backtrace(fn)
