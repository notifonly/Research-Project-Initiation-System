from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AISCIENCE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=PROJECT_ROOT / "data")
    l0_cold_dir: Path = Field(default=PROJECT_ROOT / "data" / "l0_cold")
    l1_warm_dir: Path = Field(default=PROJECT_ROOT / "data" / "l1_warm")
    logs_dir: Path = Field(default=PROJECT_ROOT / "logs")

    llm_model: str = "gpt-4o-mini"
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.2

    llm_cache_enabled: bool = False
    llm_cache_ttl_seconds: int = 86400
    mcp_cache_ttl_seconds: int = 3600

    total_token_budget: int = 5_000_000
    budget_scoping: float = 0.05
    budget_discovery: float = 0.20
    budget_extraction: float = 0.45
    budget_synthesis: float = 0.25

    max_sub_agents_per_project: int = 3
    mcp_concurrency: int = 10
    request_timeout: int = 60
    max_retries: int = 3

    outer_loop_k: int = 2
    coverage_jaccard_threshold: float = 0.70
    gap_yield_threshold: float = 0.30

    enable_breakpoints: bool = False
    enable_checkpoint: bool = True

    semantic_scholar_api_key: Optional[str] = None
    ncbi_api_key: Optional[str] = None
    gwas_catalog_email: Optional[str] = None

    # Literature source API keys (all optional)
    unpaywall_email: Optional[str] = None
    core_api_key: Optional[str] = None
    arxiv_api_key: Optional[str] = None
    crossref_email: Optional[str] = None
    doaj_api_key: Optional[str] = None
    zenodo_access_token: Optional[str] = None

    # PDF download limits
    pdf_download_max: int = 10
    pdf_download_timeout: int = 30

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.l0_cold_dir, self.l1_warm_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
