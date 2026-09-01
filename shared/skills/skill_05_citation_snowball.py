"""S5 CitationSnowball - expand reading list via forward/backward citation traversal."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s5_citation_snowball")


class CitationPaper(BaseModel):
    paper_id: str = ""
    title: str = ""
    doi: Optional[str] = None
    year: Optional[int] = None
    authors: list[str] = Field(default_factory=list)
    venue: str = ""
    direction: str = ""
    citation_count: int = 0


class CitationSnowballInput(SkillInput):
    seed_paper_ids: list[str] = Field(default_factory=list)
    seed_dois: list[str] = Field(default_factory=list)
    max_depth: int = 2
    max_per_seed: int = 10
    direction: str = Field(default="both", description="forward | backward | both")
    min_year: Optional[int] = None


class CitationSnowballOutput(SkillOutput):
    forward_hits: list[CitationPaper] = Field(default_factory=list)
    backward_hits: list[CitationPaper] = Field(default_factory=list)
    new_paper_ids: list[str] = Field(default_factory=list)
    total_explored: int = 0


class CitationSnowballSkill(BaseSkill):
    name = "s5_citation_snowball"
    description = "Expand reading list via forward/backward citation traversal on Semantic Scholar."
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = CitationSnowballInput
    output_schema = CitationSnowballOutput

    async def pre_check(self, inp: SkillInput, ctx: SkillContext) -> bool:
        csi: CitationSnowballInput = inp  # type: ignore
        if not csi.seed_paper_ids and not csi.seed_dois:
            logger.warning("citation snowball: no seed papers provided")
            return False
        return True

    async def execute(self, inp: SkillInput, ctx: SkillContext) -> SkillOutput:
        csi: CitationSnowballInput = inp  # type: ignore
        mcp = ctx.mcp_registry.semantic_scholar() if ctx.mcp_registry else None

        _mcp_errors = 0

        async def _gather_forward(paper_id: str) -> list[CitationPaper]:
            nonlocal _mcp_errors
            if not mcp:
                return []
            try:
                resp = await mcp.get_citations(paper_id, limit=csi.max_per_seed)
                if not resp.success or not resp.data:
                    _mcp_errors += 1
                    return []
                items = resp.data.get("data")
                if not items:
                    return []
                out: list[CitationPaper] = []
                for c in items:
                    paper = c.get("citingPaper", {})
                    year = paper.get("year")
                    if csi.min_year and year and year < csi.min_year:
                        continue
                    out.append(
                        CitationPaper(
                            paper_id=paper.get("paperId", ""),
                            title=paper.get("title", ""),
                            doi=(paper.get("externalIds") or {}).get("DOI"),
                            year=year,
                            authors=[a.get("name", "") for a in (paper.get("authors") or [])],
                            venue=paper.get("venue", ""),
                            direction="forward",
                            citation_count=paper.get("citationCount", 0),
                        )
                    )
                return out
            except Exception as e:
                _mcp_errors += 1
                logger.error(f"forward citation gather failed for {paper_id}: {e}")
                return []

        async def _gather_backward(paper_id: str) -> list[CitationPaper]:
            nonlocal _mcp_errors
            if not mcp:
                return []
            try:
                resp = await mcp.get_references(paper_id, limit=csi.max_per_seed)
                if not resp.success or not resp.data:
                    _mcp_errors += 1
                    return []
                items = resp.data.get("data")
                if not items:
                    return []
                out: list[CitationPaper] = []
                for r in items:
                    paper = r.get("citedPaper", {})
                    year = paper.get("year")
                    if csi.min_year and year and year < csi.min_year:
                        continue
                    out.append(
                        CitationPaper(
                            paper_id=paper.get("paperId", ""),
                            title=paper.get("title", ""),
                            doi=(paper.get("externalIds") or {}).get("DOI"),
                            year=year,
                            authors=[a.get("name", "") for a in (paper.get("authors") or [])],
                            venue=paper.get("venue", ""),
                            direction="backward",
                            citation_count=paper.get("citationCount", 0),
                        )
                    )
                return out
            except Exception as e:
                _mcp_errors += 1
                logger.error(f"backward citation gather failed for {paper_id}: {e}")
                return []

        seeds = list(csi.seed_paper_ids)
        if csi.seed_dois and mcp:
            for doi in csi.seed_dois:
                try:
                    resp = await mcp.find_by_doi(doi)
                    if resp.success and resp.data and resp.data.get("paperId"):
                        seeds.append(resp.data["paperId"])
                except Exception:
                    pass

        resolved_seeds: list[str] = []
        for seed in seeds:
            if not seed:
                continue
            if re.match(r'^\d{1,12}$', seed):
                resolved_seeds.append(f"PMID:{seed}")
            elif re.match(r'^[0-9a-fA-F]{30,50}$', seed):
                resolved_seeds.append(seed)
            else:
                resolved_seeds.append(seed)
        seeds = resolved_seeds

        seed_batch = seeds[: csi.max_depth * 5]
        forward_tasks: list[Any] = []
        backward_tasks: list[Any] = []
        if csi.direction in ("forward", "both"):
            forward_tasks = [_gather_forward(s) for s in seed_batch]
        if csi.direction in ("backward", "both"):
            backward_tasks = [_gather_backward(s) for s in seed_batch]

        forward_results = await asyncio.gather(*forward_tasks) if forward_tasks else []
        backward_results = await asyncio.gather(*backward_tasks) if backward_tasks else []

        seen: set[str] = set(seeds)
        new_ids: list[str] = []
        dedup_forward: list[CitationPaper] = []
        dedup_backward: list[CitationPaper] = []
        for p in [pp for batch in forward_results for pp in batch]:
            if p.paper_id and p.paper_id not in seen:
                seen.add(p.paper_id)
                dedup_forward.append(p)
                new_ids.append(p.paper_id)
        for p in [pp for batch in backward_results for pp in batch]:
            if p.paper_id and p.paper_id not in seen:
                seen.add(p.paper_id)
                dedup_backward.append(p)
                new_ids.append(p.paper_id)

        self._metrics.update({
            "new_citations": len(new_ids),
            "forward_hits": len(dedup_forward),
            "backward_hits": len(dedup_backward),
            "mcp_errors": _mcp_errors,
        })

        return CitationSnowballOutput(
            skill_name=self.name,
            forward_hits=dedup_forward,
            backward_hits=dedup_backward,
            new_paper_ids=new_ids,
            total_explored=len(seeds),
        )

    async def quality_gate(self, output: SkillOutput, ctx: SkillContext) -> bool:
        cso: CitationSnowballOutput = output  # type: ignore
        if output.success is False:
            return False
        mcp_errors = self._metrics.get("mcp_errors", 0)
        total_queries = (self._metrics.get("forward_hits", 0) + self._metrics.get("backward_hits", 0)) + mcp_errors
        if mcp_errors > 0 and total_queries > 0 and mcp_errors >= total_queries * 0.8:
            logger.warning(f"citation snowball: {mcp_errors}/{total_queries} MCP errors (likely rate limited), passing to not block pipeline")
            self._metrics["quality_gate_degraded"] = True
            return True
        return len(cso.new_paper_ids) > 0
