from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.core.token_budget import BudgetPhase
from shared.mcp.database.ensembl import HGNCService
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput


class TerminologyNormalizeInput(SkillInput):
    raw_terms: list[str] = Field(default_factory=list)
    trait_labels: list[str] = Field(default_factory=list)
    gene_symbols: list[str] = Field(default_factory=list)
    expand_synonyms: bool = True


class TerminologyNormalizeOutput(SkillOutput):
    normalized_traits: list[dict[str, str]] = Field(default_factory=list)
    normalized_genes: list[dict[str, Any]] = Field(default_factory=list)
    efo_mappings: list[dict[str, str]] = Field(default_factory=list)
    synonym_expansions: dict[str, list[str]] = Field(default_factory=dict)


class TerminologyNormalize(BaseSkill):
    """S2: Normalize trait labels to EFO, validate gene symbols via HGNC, expand synonyms."""

    name = "terminology_normalize"
    description = "Normalize trait labels to EFO terms, validate gene symbols, expand synonyms"
    uses_llm = True
    budget_phase = BudgetPhase.SCOPING
    input_schema = TerminologyNormalizeInput
    output_schema = TerminologyNormalizeOutput

    async def execute(self, inp: TerminologyNormalizeInput, ctx: SkillContext) -> TerminologyNormalizeOutput:
        normalized_traits: list[dict[str, str]] = []
        efo_mappings: list[dict[str, str]] = []

        gwas = ctx.mcp_registry.gwas_catalog()
        for trait in inp.trait_labels:
            try:
                result = await gwas.search_efo_traits(trait, size=5)
                if result.success and result.data:
                    traits_data = result.data.get("_embedded", {}).get("efoTraits", [])
                    if traits_data:
                        t = traits_data[0]
                        normalized_traits.append({
                            "raw": trait,
                            "efo_id": t.get("shortForm", ""),
                            "efo_label": t.get("label", ""),
                            "uri": t.get("uri", ""),
                        })
                        efo_mappings.append({"trait": trait, "efo": t.get("shortForm", "")})
                        continue
            except Exception:
                pass
            normalized_traits.append({"raw": trait, "efo_id": "", "efo_label": trait, "uri": ""})

        normalized_genes: list[dict[str, Any]] = []
        for gene in inp.gene_symbols:
            valid = HGNCService.is_valid_symbol(gene)
            try:
                ensembl = ctx.mcp_registry.ensembl()
                result = await ensembl.get_gene(gene)
                if result.success and result.data:
                    normalized_genes.append({
                        "symbol": gene,
                        "valid_hgnc": valid,
                        "ensembl_id": result.data.get("id", ""),
                        "chrom": result.data.get("seq_region_name", ""),
                        "start": result.data.get("start"),
                        "end": result.data.get("end"),
                    })
                    continue
            except Exception:
                pass
            normalized_genes.append({"symbol": gene, "valid_hgnc": valid, "ensembl_id": "", "chrom": "", "start": None, "end": None})

        synonym_expansions: dict[str, list[str]] = {}
        if inp.expand_synonyms and (inp.trait_labels or inp.gene_symbols):
            prompt = f"""Expand the following bioinformatics terms with synonyms and related terms for comprehensive literature search.
Traits: {inp.trait_labels}
Genes: {inp.gene_symbols}
Return JSON: synonym_expansions mapping each original term to a list of synonyms/aliases (max 5 each)."""
            result = await self._llm(prompt, ctx, structured=dict)
            if isinstance(result, dict) and not result.get("_parse_error"):
                synonym_expansions = result.get("synonym_expansions", {})

        self._metrics.update({
            "traits_normalized": sum(1 for t in normalized_traits if t["efo_id"]),
            "genes_validated": sum(1 for g in normalized_genes if g["valid_hgnc"]),
        })
        return TerminologyNormalizeOutput(
            normalized_traits=normalized_traits,
            normalized_genes=normalized_genes,
            efo_mappings=efo_mappings,
            synonym_expansions=synonym_expansions,
        )

    async def quality_gate(self, output: TerminologyNormalizeOutput, ctx: SkillContext) -> bool:
        if not output.success:
            return False
        return len(output.normalized_traits) > 0 or len(output.normalized_genes) > 0
