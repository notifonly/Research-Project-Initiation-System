from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


from shared.core.checkpoint import CheckpointManager
from shared.core.config import settings
from shared.core.context import ContextManager
from shared.core.harness import BreakpointHandler, BreakpointType, Harness
from shared.core.logging_setup import get_logger, setup_logging
from shared.core.loop_engine import LoopEngine, OuterLoopResult
from shared.core.llm_client import llm_complete
from shared.core.token_budget import TokenBudget
from shared.evidence.card_store import CardStore
from shared.evidence.coverage_matrix import CoverageMatrix
from shared.mcp.registry import MCPRegistry
from shared.skills import SHARED_SKILLS
from shared.skills.base_skill import BaseSkill, SkillInput


@dataclass
class ProjectResult:
    project_id: str
    archetype_id: str
    success: bool
    converged: bool = False
    convergence_reasons: list[str] = field(default_factory=list)
    total_cards: int = 0
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    budget_snapshot: dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0
    error: Optional[str] = None
    output_path: Optional[str] = None


class Orchestrator:
    """Per-project orchestrator: loads archetype, builds runtime, drives loop engine.

    Lifecycle:
    1. Load project config + archetype template
    2. Initialize runtime (MCPRegistry, CardStore, ContextManager, TokenBudget, CheckpointManager)
    3. Instantiate skills from archetype skill_sequence (shared + archetype-specific)
    4. Build Harness + LoopEngine
    5. Run the loop engine
    6. Generate final report and save to output/
    """

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        archetype_id: str,
        research_direction: str,
        global_semaphore: Optional[asyncio.Semaphore] = None,
        breakpoint_handler: Optional[BreakpointHandler] = None,
        project_config: Optional[dict[str, Any]] = None,
        extra_skills: Optional[dict[str, type[BaseSkill]]] = None,
    ) -> None:
        self.project_id = project_id
        self.project_dir = project_dir
        self.archetype_id = archetype_id
        self.research_direction = research_direction
        self.global_semaphore = global_semaphore
        self.breakpoint_handler = breakpoint_handler
        self.project_config = project_config or {}
        self.extra_skills = extra_skills or {}
        self.output_dir = project_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger(project_id)

        self.mcp_registry: Optional[MCPRegistry] = None
        self.card_store: Optional[CardStore] = None
        self.context: Optional[ContextManager] = None
        self.budget: Optional[TokenBudget] = None
        self.checkpoint_mgr: Optional[CheckpointManager] = None
        self.harness: Optional[Harness] = None
        self.loop_engine: Optional[LoopEngine] = None
        self.coverage_matrix: Optional[CoverageMatrix] = None
        self.template: Any = None
        self._skill_instances: dict[str, BaseSkill] = {}

    async def run(self) -> ProjectResult:
        t0 = time.monotonic()
        setup_logging(self.project_id)
        self.logger.info(f"Starting orchestrator for project {self.project_id} (archetype: {self.archetype_id})")

        try:
            self._load_archetype()
            self._init_runtime()
            self._instantiate_skills()
            self._build_loop_engine()

            assert self.harness is not None
            assert self.loop_engine is not None
            assert self.mcp_registry is not None
            assert self.card_store is not None
            assert self.context is not None
            assert self.budget is not None

            if not await self._check_llm_health():
                self.logger.warning("LLM health check failed; pipeline may produce no cards/gaps/hypotheses")

            initial_input = SkillInput(
                **{
                    "project_id": self.project_id,
                    "research_direction": self.research_direction,
                    "archetype_id": self.archetype_id,
                }
            )

            self.logger.info(f"Running loop engine with skill sequence: {self.template.config['skill_sequence']}")
            outer_result = await self.loop_engine.run(initial_input)

            self.harness.fire_breakpoint(
                BreakpointType.BP7_FINAL_MAP,
                "final",
                data=outer_result.final_coverage_summary,
            )

            result = ProjectResult(
                project_id=self.project_id,
                archetype_id=self.archetype_id,
                success=True,
                converged=outer_result.converged,
                convergence_reasons=[r.value for r in outer_result.reasons],
                total_cards=outer_result.total_cards,
                coverage_summary=outer_result.final_coverage_summary,
                gaps=outer_result.final_gaps,
                hypotheses=outer_result.final_hypotheses,
                budget_snapshot=outer_result.budget_snapshot,
                duration_s=time.monotonic() - t0,
            )
            self._save_report(result, outer_result)
            self.logger.info(
                f"Project {self.project_id} completed: "
                f"{result.total_cards} cards, converged={result.converged}, "
                f"duration={result.duration_s:.1f}s"
            )
            return result

        except Exception as e:
            import traceback

            self.logger.error(f"Orchestrator failed: {e}\n{traceback.format_exc()}")
            return ProjectResult(
                project_id=self.project_id,
                archetype_id=self.archetype_id,
                success=False,
                error=str(e),
                duration_s=time.monotonic() - t0,
            )
        finally:
            await self._cleanup()

    def _load_archetype(self) -> None:
        from archetypes import load_archetype

        self.template = load_archetype(self.archetype_id)
        self._merge_project_config()
        self.logger.info(f"Loaded archetype: {self.template.name} ({self.archetype_id})")

    def _merge_project_config(self) -> None:
        """Deep-merge project_config into the archetype template config.

        Supports overriding/extending: parameters, skill_sequence, mcp_priorities,
        convergence, breakpoints, coverage_axes, and any scalar field.
        Lists (skill_sequence, breakpoints) are replaced if provided.
        Dicts (parameters, mcp_priorities, convergence) are deep-merged.
        """
        if not self.project_config:
            return
        cfg = self.template.config
        for key, val in self.project_config.items():
            if key in ("parameters", "mcp_priorities", "convergence") and isinstance(val, dict):
                base = cfg.get(key, {})
                if not isinstance(base, dict):
                    base = {}
                merged = {**base, **val}
                for subk, subv in val.items():
                    if isinstance(subv, dict) and isinstance(base.get(subk), dict):
                        merged[subk] = {**base[subk], **subv}
                cfg[key] = merged
            elif key in ("skill_sequence", "breakpoints", "coverage_axes") and isinstance(val, list):
                cfg[key] = val
            else:
                cfg[key] = val
        self.template.config = cfg

    def _init_runtime(self) -> None:
        self.mcp_registry = MCPRegistry(self.project_id, semaphore=self.global_semaphore)
        self.card_store = CardStore(self.project_id)
        self.context = ContextManager(self.project_id, l1_store=self.card_store)
        self.budget = TokenBudget(project_id=self.project_id)
        self.checkpoint_mgr = CheckpointManager(self.project_id)
        axes = self.template.config.get("coverage_axes") if self.template else None
        self.coverage_matrix = CoverageMatrix(axes=axes)
        self.logger.info("Runtime initialized (MCP registry, card store, context, budget, checkpoints)")

    def _instantiate_skills(self) -> None:
        skill_sequence: list[str] = self.template.config.get("skill_sequence", [])
        archetype_skills: dict[str, type] = self.template.skills or {}
        for sid in skill_sequence:
            skill_cls: Optional[type[BaseSkill]] = None
            if sid in self.extra_skills:
                skill_cls = self.extra_skills[sid]
            elif sid in SHARED_SKILLS:
                skill_cls = SHARED_SKILLS[sid]
            elif sid in archetype_skills:
                skill_cls = archetype_skills[sid]
            if skill_cls is None:
                self.logger.warning(f"Skill {sid} not found in shared or archetype skills, will skip")
                continue
            try:
                instance = skill_cls()
                self._skill_instances[sid] = instance
                self.logger.info(f"Instantiated skill: {sid} ({instance.__class__.__name__})")
            except Exception as e:
                self.logger.error(f"Failed to instantiate skill {sid}: {e}")

    def _build_loop_engine(self) -> None:
        convergence_config = self.template.config.get("convergence", {})
        params = self.template.config.get("parameters", {})
        max_inner = params.get("max_inner_iterations", 7)
        max_outer = params.get("max_outer_rounds", 5)

        assert self.mcp_registry is not None
        assert self.card_store is not None
        assert self.context is not None
        assert self.budget is not None
        assert self.checkpoint_mgr is not None
        assert self.coverage_matrix is not None

        self.harness = Harness(
            project_id=self.project_id,
            mcp_registry=self.mcp_registry,
            card_store=self.card_store,
            context=self.context,
            budget=self.budget,
            archetype_config={**self.template.config, "_gap_patterns": self.template.gap_patterns, "_evidence_card_class": self.template.evidence_card_class},
            max_sub_agents=settings.max_sub_agents_per_project,
            breakpoint_handler=self.breakpoint_handler,
        )

        self.loop_engine = LoopEngine(
            project_id=self.project_id,
            skill_sequence=self.template.config.get("skill_sequence", []),
            skill_instances=self._skill_instances,
            harness=self.harness,
            checkpoint_mgr=self.checkpoint_mgr,
            coverage_matrix=self.coverage_matrix,
            convergence_config=convergence_config,
            max_inner_iterations=max_inner,
            max_outer_rounds=max_outer,
            evidence_card_class=self.template.evidence_card_class if self.template else None,
        )

    def _save_report(self, result: ProjectResult, outer_result: OuterLoopResult) -> None:
        report = {
            "project_id": result.project_id,
            "archetype_id": result.archetype_id,
            "research_direction": self.research_direction,
            "success": result.success,
            "converged": result.converged,
            "convergence_reasons": result.convergence_reasons,
            "total_cards": result.total_cards,
            "coverage_summary": result.coverage_summary,
            "gaps": result.gaps,
            "hypotheses": result.hypotheses,
            "budget": result.budget_snapshot,
            "duration_s": round(result.duration_s, 2),
            "inner_loop_rounds": [
                {
                    "round": ri,
                    "iteration": ir.iteration,
                    "converged": ir.converged,
                    "reason": ir.reason.value if ir.reason else None,
                    "cards_added": ir.cards_added,
                    "queries_run": ir.queries_run,
                    "new_citations": ir.new_citations,
                    "errors": ir.errors,
                }
                for ri, ir in enumerate(outer_result.inner_results)
            ],
        }

        report_path = self.output_dir / "final_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        result.output_path = str(report_path)

        summary_path = self.output_dir / "summary.json"
        summary = {
            "project_id": result.project_id,
            "archetype_id": result.archetype_id,
            "converged": result.converged,
            "total_cards": result.total_cards,
            "gap_count": len(result.gaps),
            "hypothesis_count": len(result.hypotheses),
            "coverage_cells": result.coverage_summary.get("total_cells", 0),
            "duration_s": round(result.duration_s, 2),
            "budget_used": result.budget_snapshot.get("total_used", 0),
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        self._save_evidence_cards_export()
        self._save_coverage_map()

    def _save_evidence_cards_export(self) -> None:
        if self.card_store is None:
            return
        rows = self.card_store.all_rows()
        export_path = self.output_dir / "evidence_cards.jsonl"
        with export_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def _save_coverage_map(self) -> None:
        if self.coverage_matrix is None:
            return
        cells = self.coverage_matrix.all_cells()
        cmap: list[dict[str, Any]] = []
        axes = self.coverage_matrix.AXES
        for key, cell in cells.items():
            entry = {ax: val for ax, val in zip(axes, key)}
            entry.update({
                "card_count": cell.card_count,
                "has_fine_mapping": cell.has_fine_mapping,
                "has_colocalization": cell.has_colocalization,
                "has_replication": cell.has_replication,
                "data_available": cell.data_available,
            })
            cmap.append(entry)
        cmap_path = self.output_dir / "coverage_map.json"
        cmap_path.write_text(json.dumps(cmap, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    async def _check_llm_health(self) -> bool:
        try:
            result = await llm_complete("Respond with exactly the word HEALTHY", system="You are a health check probe. Reply with only the word HEALTHY.")
            if result and "HEALTHY" in str(result):
                self.logger.info("LLM health check passed")
                return True
            self.logger.warning(f"LLM health check returned unexpected response: {str(result)[:100]}")
            return False
        except Exception as e:
            self.logger.warning(f"LLM health check failed: {e}")
            return False

    async def _cleanup(self) -> None:
        if self.mcp_registry is not None:
            try:
                await self.mcp_registry.aclose_all()
            except Exception as e:
                self.logger.warning(f"MCP cleanup error: {e}")
        if self.context is not None:
            try:
                self.context.flush_l2_snapshot("final")
            except Exception:
                pass
