"""S9 MethodDatasetMatch - match required methods to available datasets/code repos."""

from __future__ import annotations


from pydantic import BaseModel, Field

from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput


class MethodDatasetMatchInput(SkillInput):
    required_methods: list[str] = Field(default_factory=list)
    required_datasets: list[str] = Field(default_factory=list)
    trait: str = ""
    cell_types: list[str] = Field(default_factory=list)


class Match(BaseModel):
    method_or_dataset: str = ""
    kind: str = ""
    repo: str = ""
    url: str = ""
    stars: int = 0
    notes: str = ""


class MethodDatasetMatchOutput(SkillOutput):
    matches: list[Match] = Field(default_factory=list)
    unmatched: list[str] = Field(default_factory=list)
    coverage_ratio: float = 0.0


class MethodDatasetMatch(BaseSkill):
    """S9: Match required methods/datasets to GitHub repos and Papers with Code entries."""

    name = "method_dataset_match"
    description = "Match required methods & datasets to public code repos and benchmark entries"
    uses_llm = False
    budget_phase = BudgetPhase.EXTRACTION
    input_schema = MethodDatasetMatchInput
    output_schema = MethodDatasetMatchOutput

    async def execute(self, inp: MethodDatasetMatchInput, ctx: SkillContext) -> MethodDatasetMatchOutput:
        reg = ctx.mcp_registry
        matches: list[Match] = []
        if not reg:
            return MethodDatasetMatchOutput(skill_name=self.name, unmatched=inp.required_methods + inp.required_datasets)

        gh = reg.github()
        pwc = reg.papers_with_code()

        for method in inp.required_methods:
            found = False
            try:
                resp = await pwc.search_methods(method)
                if resp.success and resp.data:
                    for m in (resp.data.get("results") or [])[:2]:
                        matches.append(Match(
                            method_or_dataset=method, kind="method",
                            repo=m.get("name", ""), url=m.get("url", ""),
                            notes=m.get("full_name", ""),
                        ))
                        found = True
            except Exception:
                pass
            if not found:
                try:
                    resp = await gh.search_repositories(method, per_page=3)
                    if resp.success and resp.data:
                        for r in (resp.data.get("items") or [])[:2]:
                            matches.append(Match(
                                method_or_dataset=method, kind="repo",
                                repo=r.get("full_name", ""), url=r.get("html_url", ""),
                                stars=r.get("stargazers_count", 0),
                            ))
                            found = True
                except Exception:
                    pass

        for ds in inp.required_datasets:
            try:
                resp = await pwc.search_datasets(ds)
                if resp.success and resp.data:
                    for d in (resp.data.get("results") or [])[:2]:
                        matches.append(Match(
                            method_or_dataset=ds, kind="dataset",
                            repo=d.get("name", ""), url=d.get("url", ""),
                            notes=d.get("full_name", ""),
                        ))
            except Exception:
                pass

        matched_keys = {m.method_or_dataset for m in matches}
        required_all = set(inp.required_methods) | set(inp.required_datasets)
        unmatched = [r for r in required_all if r not in matched_keys]
        ratio = len(required_all - set(unmatched)) / max(1, len(required_all))

        self._metrics.update({"matches": len(matches), "unmatched": len(unmatched), "coverage": ratio})
        return MethodDatasetMatchOutput(
            skill_name=self.name,
            matches=matches,
            unmatched=unmatched,
            coverage_ratio=ratio,
        )
