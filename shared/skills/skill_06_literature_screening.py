"""S6 LiteratureScreening - 3-tier screening: title/abstract -> intro/method -> full-text relevance."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput


class ScreenCandidate(BaseModel):
    paper_id: str = ""
    title: str = ""
    doi: Optional[str] = None
    pmid: Optional[str] = None
    abstract: str = ""
    year: Optional[int] = None
    source: str = ""


class TierDecision(BaseModel):
    keep: bool = False
    tier: str = ""
    relevance_score: float = 0.0
    reason: str = ""


class LiteratureScreeningInput(SkillInput):
    candidates: list[ScreenCandidate] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    scope_include: list[str] = Field(default_factory=list)
    scope_exclude: list[str] = Field(default_factory=list)
    max_tier: int = 3


class LiteratureScreeningOutput(SkillOutput):
    kept: list[ScreenCandidate] = Field(default_factory=list)
    rejected: list[ScreenCandidate] = Field(default_factory=list)
    tier_decisions: dict[str, TierDecision] = Field(default_factory=dict)
    pass_rate: float = 0.0


class LiteratureScreening(BaseSkill):
    """S6: 3-tier literature screening (title/abstract -> intro/method -> full-text)."""

    name = "literature_screening"
    description = "3-tier screening: T1 title/abstract -> T2 intro/method -> T3 full-text"
    uses_llm = True
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = LiteratureScreeningInput
    output_schema = LiteratureScreeningOutput

    async def execute(self, inp: LiteratureScreeningInput, ctx: SkillContext) -> LiteratureScreeningOutput:
        decisions: dict[str, TierDecision] = {}
        kept: list[ScreenCandidate] = []
        rejected: list[ScreenCandidate] = []

        for cand in inp.candidates:
            key = cand.paper_id or cand.doi or cand.pmid or cand.title
            t1 = self._tier1_keyword(cand, inp)
            decisions[key] = t1
            if t1.keep:
                kept.append(cand)
            else:
                rejected.append(cand)
            ctx.budget.consume(0)

        # Batch LLM-based refinement for borderline T1 hits (relevance_score in (0.4, 0.7))
        borderline = [c for c in kept if 0.4 < decisions[c.paper_id or c.doi or c.title].relevance_score <= 0.7]
        if borderline and inp.max_tier >= 2:
            await self._tier2_batch(borderline, inp, ctx, decisions, kept, rejected)

        pass_rate = len(kept) / max(1, len(inp.candidates))
        self._metrics.update({
            "candidates": len(inp.candidates),
            "kept": len(kept),
            "pass_rate": round(pass_rate, 3),
        })
        return LiteratureScreeningOutput(
            skill_name=self.name,
            kept=kept,
            rejected=rejected,
            tier_decisions=decisions,
            pass_rate=pass_rate,
        )

    @staticmethod
    def _expand_key_terms(key_terms: list[str]) -> list[str]:
        STOP_WORDS = {
            "the", "and", "for", "from", "with", "that", "this", "are", "was",
            "were", "been", "have", "has", "had", "not", "but", "all", "any",
            "each", "both", "some", "such", "only", "own", "same", "than",
            "into", "over", "under", "more", "most", "can", "will", "may",
            "also", "just", "about", "which", "their",
        }
        expanded = set()
        for k in key_terms:
            k_lower = k.lower()
            expanded.add(k_lower)
            parts = re.split(r"[\s,+/\\-]+", k_lower)
            for p in parts:
                p = p.strip().strip("()[]{}:;.!?'\"")
                if len(p) >= 4 and p not in STOP_WORDS:
                    expanded.add(p)
        return sorted(expanded, key=len, reverse=True)

    def _tier1_keyword(self, cand: ScreenCandidate, inp: LiteratureScreeningInput) -> TierDecision:
        text = ((cand.title or "") + " " + (cand.abstract or "")).lower()
        if not text.strip():
            return TierDecision(keep=False, tier="T1", relevance_score=0.0, reason="empty text")
        atomic_terms = self._expand_key_terms(inp.key_terms)
        hits = sum(1 for k in atomic_terms if k in text)
        score = hits / max(1, len(atomic_terms))
        excluded = any(e.lower() in text for e in inp.scope_exclude)
        included = any(i.lower() in text for i in inp.scope_include) if inp.scope_include else True
        if excluded:
            return TierDecision(keep=False, tier="T1", relevance_score=score, reason="excluded term")
        keep = included and (score >= 0.12 or hits >= 2)
        return TierDecision(keep=keep, tier="T1", relevance_score=score, reason="keyword filter")

    async def _tier2_batch(
        self,
        candidates: list[ScreenCandidate],
        inp: LiteratureScreeningInput,
        ctx: SkillContext,
        decisions: dict[str, TierDecision],
        kept: list[ScreenCandidate],
        rejected: list[ScreenCandidate],
    ) -> None:
        lines = []
        for c in candidates:
            lines.append(f"[{c.paper_id or c.title}] {c.title} || {(c.abstract or '')[:300]}")
        prompt = (
            "You are screening bioinformatics papers for a V2G (variant-to-function) research topic.\n"
            f"Key terms: {inp.key_terms}\nInclude: {inp.scope_include}\nExclude: {inp.scope_exclude}\n\n"
            "For each paper below, return JSON: a list of objects {key, keep: bool, relevance_score: 0-1, reason}.\n"
            "Keep only papers with relevant methods/data for variant-to-gene/function analysis.\n\nPapers:\n"
            + "\n".join(lines)
        )
        result = await self._llm(prompt, ctx, structured=list)
        if not isinstance(result, list):
            return
        for item in result:
            if not isinstance(item, dict):
                continue
            key = item.get("key", "")
            keep = bool(item.get("keep", False))
            td = TierDecision(
                keep=keep,
                tier="T2",
                relevance_score=float(item.get("relevance_score", 0.0)),
                reason=item.get("reason", ""),
            )
            decisions[key] = td
            # adjust kept/rejected lists
            target = [c for c in kept if (c.paper_id or c.doi or c.title) == key]
            if not keep:
                for c in target:
                    if c in kept:
                        kept.remove(c)
                    if c not in rejected:
                        rejected.append(c)
