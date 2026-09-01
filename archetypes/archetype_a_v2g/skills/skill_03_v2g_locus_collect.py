"""S3 V2GLocusCollect (Archetype A-specific) - collect GWAS lead loci from GWAS Catalog + Open Targets."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s3_v2g_locus_collect")


class LocusRecord(BaseModel):
    rsid: str = ""
    chrom: str = ""
    pos: Optional[int] = None
    p_value: Optional[float] = None
    beta: Optional[float] = None
    trait: str = ""
    efo: str = ""
    reported_genes: list[str] = Field(default_factory=list)
    study_accession: str = ""
    source: str = ""
    odds_ratio: Optional[float] = None


class V2GLocusCollectInput(SkillInput):
    traits: list[str] = Field(default_factory=list)
    efo_ids: list[str] = Field(default_factory=list)
    genes: list[str] = Field(default_factory=list)
    p_value_max: float = 5e-8
    max_per_trait: int = 50


class V2GLocusCollectOutput(SkillOutput):
    loci: list[LocusRecord] = Field(default_factory=list)
    distinct_rsids: list[str] = Field(default_factory=list)
    distinct_genes: list[str] = Field(default_factory=list)
    per_trait_counts: dict[str, int] = Field(default_factory=dict)


class V2GLocusCollect(BaseSkill):
    """S3 (Archetype A): Collect GWAS lead loci from GWAS Catalog and Open Targets Genetics."""

    name = "v2g_locus_collect"
    description = "Collect GWAS lead variants/loci for target traits from GWAS Catalog + Open Targets"
    uses_llm = False
    budget_phase = BudgetPhase.SCOPING
    input_schema = V2GLocusCollectInput
    output_schema = V2GLocusCollectOutput

    async def execute(self, inp: V2GLocusCollectInput, ctx: SkillContext) -> V2GLocusCollectOutput:
        reg = ctx.mcp_registry
        loci: list[LocusRecord] = []
        per_trait: dict[str, int] = {}

        if not reg:
            return V2GLocusCollectOutput(skill_name=self.name)

        gwas = reg.gwas_catalog()
        ot = reg.open_targets()

        # GWAS Catalog by trait / efo
        for trait in inp.traits:
            try:
                resp = await gwas.search_associations(trait=trait, p_value_max=inp.p_value_max)
                if resp.success and resp.data:
                    for assoc in resp.data.get("_embedded", {}).get("associations", [])[:inp.max_per_trait]:
                        loci.append(self._parse_gwas_assoc(assoc, trait, "gwas_catalog"))
                        per_trait[trait] = per_trait.get(trait, 0) + 1
            except Exception as e:
                logger.warning(f"GWAS catalog trait search failed for {trait}: {e}")

        for efo in inp.efo_ids:
            try:
                resp = await gwas.search_associations(efo=efo, p_value_max=inp.p_value_max)
                if resp.success and resp.data:
                    for assoc in resp.data.get("_embedded", {}).get("associations", [])[:inp.max_per_trait]:
                        loci.append(self._parse_gwas_assoc(assoc, efo, "gwas_catalog"))
                        per_trait[efo] = per_trait.get(efo, 0) + 1
            except Exception:
                pass

        # Open Targets by trait
        for trait in inp.traits:
            try:
                resp = await ot.search_studies(trait, size=inp.max_per_trait)
                if resp.success and resp.data:
                    studies = resp.data.get("data", {}).get("studies", {}).get("nodes", [])
                    for s in studies:
                        loci.append(LocusRecord(
                            rsid=s.get("variantId", ""),
                            chrom=s.get("chromosome", ""),
                            pos=s.get("position"),
                            p_value=s.get("pValue") or s.get("pval"),
                            beta=s.get("beta"),
                            trait=trait,
                            reported_genes=s.get("geneSymbol", "").split(",") if s.get("geneSymbol") else [],
                            study_accession=s.get("studyId", ""),
                            source="open_targets",
                        ))
                        per_trait[trait] = per_trait.get(trait, 0) + 1
            except Exception as e:
                logger.warning(f"Open Targets search failed for {trait}: {e}")

        # By gene
        for gene in inp.genes[:10]:
            try:
                resp = await gwas.search_by_gene(gene, size=20)
                if resp.success and resp.data:
                    for assoc in resp.data.get("_embedded", {}).get("associations", [])[:10]:
                        loci.append(self._parse_gwas_assoc(assoc, gene, "gwas_catalog_gene"))
            except Exception:
                pass

        # Deduplicate by rsid
        seen: set[str] = set()
        dedup: list[LocusRecord] = []
        for rec in loci:
            if rec.rsid and rec.rsid not in seen:
                seen.add(rec.rsid)
                dedup.append(rec)
        distinct_genes = sorted({g for rec in dedup for g in rec.reported_genes if g})

        self._metrics.update({
            "loci": len(dedup),
            "distinct_rsids": len(seen),
            "distinct_genes": len(distinct_genes),
        })
        return V2GLocusCollectOutput(
            skill_name=self.name,
            loci=dedup,
            distinct_rsids=sorted(seen),
            distinct_genes=distinct_genes,
            per_trait_counts=per_trait,
        )

    def _parse_gwas_assoc(self, assoc: dict[str, Any], trait: str, source: str) -> LocusRecord:
        loc = assoc.get("locus", {}) or {}
        snps = assoc.get("snps", "")
        reported = assoc.get("reportedGenes", [])
        genes: list[str] = []
        if isinstance(reported, list):
            for rg in reported:
                if isinstance(rg, dict):
                    genes.append(rg.get("geneName", "") or rg.get("geneSymbol", ""))
                elif isinstance(rg, str):
                    genes.append(rg)
        pval = assoc.get("pvalue") or assoc.get("pValue")
        return LocusRecord(
            rsid=snps,
            chrom=loc.get("chromosomeName", ""),
            pos=loc.get("chromosomePosition"),
            p_value=pval,
            beta=assoc.get("betaNum"),
            odds_ratio=assoc.get("orNum"),
            trait=trait,
            efo=assoc.get("efoTrait", ""),
            reported_genes=[g for g in genes if g],
            study_accession=assoc.get("studyAccession", ""),
            source=source,
        )
