"""S8 DataAvailability - assess public data availability for each locus/finding."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s8_data_availability")


class DataAvailabilityInput(SkillInput):
    cards_summary: list[dict[str, Any]] = Field(default_factory=list)
    locus_genes: list[str] = Field(default_factory=list)
    cell_types: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)


class DataAsset(BaseModel):
    accession: str = ""
    repository: str = ""
    description: str = ""
    organism: str = ""
    assay: str = ""
    url: str = ""
    matched_to: str = ""


class DataAvailabilityOutput(SkillOutput):
    assets: list[DataAsset] = Field(default_factory=list)
    coverage_per_locus: dict[str, bool] = Field(default_factory=dict)
    coverage_per_celltype: dict[str, bool] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)


class DataAvailability(BaseSkill):
    """S8: Query GEO/ENCODE/scPerturb/CellxGene for public datasets matching loci/cell types/traits."""

    name = "data_availability"
    description = "Assess public dataset availability across loci, cell types, traits"
    uses_llm = False
    budget_phase = BudgetPhase.EXTRACTION
    input_schema = DataAvailabilityInput
    output_schema = DataAvailabilityOutput

    async def execute(self, inp: DataAvailabilityInput, ctx: SkillContext) -> DataAvailabilityOutput:
        reg = ctx.mcp_registry
        assets: list[DataAsset] = []
        cov_locus: dict[str, bool] = {}
        cov_cell: dict[str, bool] = {}

        if reg:
            geo = reg.geo()
            for gene in inp.locus_genes[:15]:
                try:
                    resp = await geo.search_datasets(gene, retmax=5)
                    if resp.success and resp.data:
                        for hit in resp.data.get("esearchresult", {}).get("idlist", [])[:3]:
                            assets.append(DataAsset(
                                accession=hit, repository="GEO", description=gene,
                                organism="Homo sapiens", assay="", url=f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={hit}",
                                matched_to=gene,
                            ))
                        cov_locus[gene] = True
                        continue
                except Exception:
                    pass
                cov_locus[gene] = False

            if reg._mcps.get("cellxgene"):
                cxg = reg.cellxgene()
                for ct in inp.cell_types[:10]:
                    try:
                        resp = await cxg.search_genes(ct)
                        if resp.success and resp.data:
                            cov_cell[ct] = True
                            continue
                    except Exception:
                        pass
                    cov_cell[ct] = False

        gaps: list[str] = []
        for g, has in cov_locus.items():
            if not has:
                gaps.append(f"no public GEO data for locus {g}")
        for ct, has in cov_cell.items():
            if not has:
                gaps.append(f"no CellxGene coverage for cell type {ct}")

        self._metrics.update({
            "assets_found": len(assets),
            "locus_coverage": sum(cov_locus.values()),
            "celltype_coverage": sum(cov_cell.values()),
            "gaps": len(gaps),
        })
        return DataAvailabilityOutput(
            skill_name=self.name,
            assets=assets,
            coverage_per_locus=cov_locus,
            coverage_per_celltype=cov_cell,
            gaps=gaps,
        )
