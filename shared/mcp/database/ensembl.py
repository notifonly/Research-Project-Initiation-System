from __future__ import annotations


from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class EnsemblMCP(BaseMCP):
    """Ensembl REST API - variant, gene, regulatory region lookups for V2G."""

    name = "ensembl"
    base_url = "https://rest.ensembl.org"
    requires_api_key = False

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "AIscience/0.1"}

    async def health(self) -> MCPResult:
        return await self._request("GET", "info/ping")

    async def get_variant(self, rsid: str, species: str = "human") -> MCPResult:
        rsid_clean = rsid if rsid.startswith("rs") else f"rs{rsid}"
        return await self._request("GET", f"variation/{species}/{rsid_clean}")

    async def get_gene(self, gene_symbol: str, species: str = "human") -> MCPResult:
        return await self._request("GET", f"lookup/symbol/{species}/{gene_symbol}")

    async def get_gene_by_id(self, gene_id: str) -> MCPResult:
        return await self._request("GET", f"lookup/id/{gene_id}")

    async def get_regulatory_region(self, region: str, species: str = "human") -> MCPResult:
        return await self._request("GET", f"overlap/region/{species}/{region}", params={"feature": "regulatory"})

    async def get_phenotypes(self, gene_symbol: str, species: str = "human") -> MCPResult:
        return await self._request("GET", f"phenotype/gene/{species}/{gene_symbol}")

    async def get_ld(self, variant_id: str, population: str = "1000GENOMES:phase_3:EUR", r2_threshold: float = 0.8) -> MCPResult:
        params = {"population_name": population, "r2": r2_threshold}
        return await self._request("GET", f"variation/{variant_id}/{population}", params=params)


class HGNCService:
    """In-process HGNC gene symbol validator (offline set). Not an MCP server but a utility."""

    COMMON_GENES: set[str] = set(
        "GCK TCF7L2 KCNJ11 PPARG HNF1A HNF4A SLC30A8 CDKAL1 IRS1 FTO "
        "PNPLA3 SORT1 PCSK9 HMGCR LPA APOE BRCA1 BRCA2 TP53 EGFR KRAS "
        "PTEN MYC BCL2 VEGFA IL6 TNF ACE MTHFR APOB LDLR CETP LPL NOS3 "
        "SCN5A CFTR DMD HBB HBA1 INS LEPR MC4R GHRL ADIPOQ NOD2 ATG5 "
        "TREM2 CD33 BIN1 ABCA7 CR1 PICALM SORL1 CLU INPP5D MEFC2".split()
    )

    @classmethod
    def is_valid_symbol(cls, symbol: str) -> bool:
        return symbol.upper() in cls.COMMON_GENES

    @classmethod
    def add_symbols(cls, symbols: set[str]) -> None:
        cls.COMMON_GENES.update(s.upper() for s in symbols)
