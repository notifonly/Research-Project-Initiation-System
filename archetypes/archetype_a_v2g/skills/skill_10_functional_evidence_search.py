"""S10 FunctionalEvidenceSearch (Archetype A-specific) - search functional evidence (eQTL/pQTL/coloc) via Open Targets L2G."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s10_functional_evidence_search")


class FunctionalEvidence(BaseModel):
    variant_id: str = ""
    gene: str = ""
    study_id: str = ""
    l2g_score: Optional[float] = None
    coloc_score: Optional[float] = None
    qtl_type: str = ""
    tissue: str = ""
    source: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class FunctionalEvidenceSearchInput(SkillInput):
    study_ids: list[str] = Field(default_factory=list)
    variant_ids: list[str] = Field(default_factory=list)
    genes: list[str] = Field(default_factory=list)


class FunctionalEvidenceSearchOutput(SkillOutput):
    evidence: list[FunctionalEvidence] = Field(default_factory=list)
    coloc_count: int = 0
    l2g_count: int = 0
    per_gene: dict[str, int] = Field(default_factory=dict)


class FunctionalEvidenceSearch(BaseSkill):
    """S10 (Archetype A): Search functional evidence (L2G, colocalization, QTL) via Open Targets."""

    name = "functional_evidence_search"
    description = "Search functional evidence (L2G, coloc, QTL) via Open Targets Genetics"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = FunctionalEvidenceSearchInput
    output_schema = FunctionalEvidenceSearchOutput

    async def execute(self, inp: FunctionalEvidenceSearchInput, ctx: SkillContext) -> FunctionalEvidenceSearchOutput:
        reg = ctx.mcp_registry
        if not reg:
            return FunctionalEvidenceSearchOutput(skill_name=self.name)
        ot = reg.open_targets()
        evidence: list[FunctionalEvidence] = []
        per_gene: dict[str, int] = {}
        coloc_count = 0
        l2g_count = 0

        # L2G + coloc for each study x variant
        pairs: list[tuple[str, str]] = []
        for sid in inp.study_ids[:10]:
            for vid in inp.variant_ids[:20]:
                pairs.append((sid, vid))

        for sid, vid in pairs[:50]:
            try:
                resp = await ot.locus_to_gene(sid, vid, page_size=20)
                if resp.success and resp.data:
                    nodes = resp.data.get("data", {}).get("locusToGene", {}).get("nodes", [])
                    for n in nodes:
                        gene = n.get("gene", {}).get("symbol", "")
                        score = n.get("score")
                        fe = FunctionalEvidence(
                            variant_id=vid, gene=gene, study_id=sid,
                            l2g_score=score, qtl_type="L2G", source="open_targets",
                            raw=n,
                        )
                        evidence.append(fe)
                        l2g_count += 1
                        if gene:
                            per_gene[gene] = per_gene.get(gene, 0) + 1
            except Exception as e:
                logger.debug(f"L2G failed for {sid}/{vid}: {e}")

            try:
                resp = await ot.colocalization(sid, vid)
                if resp.success and resp.data:
                    nodes = resp.data.get("data", {}).get("colocalisation", {}).get("nodes", [])
                    for n in nodes:
                        gene = n.get("gene", {}).get("symbol", "")
                        score = n.get("h4")
                        evidence.append(FunctionalEvidence(
                            variant_id=vid, gene=gene, study_id=sid,
                            coloc_score=score, qtl_type="coloc",
                            tissue=n.get("tissueName", ""), source="open_targets",
                            raw=n,
                        ))
                        coloc_count += 1
                        if gene:
                            per_gene[gene] = per_gene.get(gene, 0) + 1
            except Exception:
                pass

        # Gene-based study search
        for gene in inp.genes[:10]:
            try:
                resp = await ot.search_by_gene(gene, size=15)
                if resp.success and resp.data:
                    nodes = resp.data.get("data", {}).get("studies", {}).get("nodes", [])
                    for s in nodes:
                        evidence.append(FunctionalEvidence(
                            gene=gene, study_id=s.get("studyId", ""),
                            variant_id=s.get("variantId", ""),
                            qtl_type="gene_study", source="open_targets",
                            raw=s,
                        ))
            except Exception:
                pass

        self._metrics.update({
            "evidence_items": len(evidence),
            "coloc": coloc_count,
            "l2g": l2g_count,
        })
        return FunctionalEvidenceSearchOutput(
            skill_name=self.name,
            evidence=evidence,
            coloc_count=coloc_count,
            l2g_count=l2g_count,
            per_gene=per_gene,
        )
