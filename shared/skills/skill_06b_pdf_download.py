from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.mcp.literature.pdf_service import PDFDownloadService
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s6b_pdf_download")


class PDFDownloadInput(SkillInput):
    screened_papers: list[dict[str, Any]] = Field(default_factory=list)
    max_downloads: int = 10
    download_sources: list[str] = Field(default_factory=list)
    priority_keywords: list[str] = Field(default_factory=list)


class PDFDownloadOutput(SkillOutput):
    papers_with_fulltext: list[dict[str, Any]] = Field(default_factory=list)
    download_count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    total_text_chars: int = 0


class PDFDownloadSkill(BaseSkill):
    """S6b: Download full-text PDFs for top screened papers via OA-first fallback chain."""

    name = "s6b_pdf_download"
    description = "Download full-text PDFs via OA-first fallback chain for S7 evidence extraction"
    uses_llm = False
    budget_phase = BudgetPhase.DISCOVERY
    input_schema = PDFDownloadInput
    output_schema = PDFDownloadOutput

    async def execute(self, inp: PDFDownloadInput, ctx: SkillContext) -> PDFDownloadOutput:
        if not inp.screened_papers:
            logger.info("No screened papers to download")
            return PDFDownloadOutput(skill_name=self.name)

        papers = list(inp.screened_papers)
        if inp.priority_keywords:
            def _priority(p: dict) -> int:
                text = ((p.get("title") or "") + " " + (p.get("abstract") or "")).lower()
                return sum(2 if kw.lower() in text else 0 for kw in inp.priority_keywords)
            papers.sort(key=_priority, reverse=True)

        to_download = papers[: min(inp.max_downloads, self._max_download_limit())]
        rest = papers[min(inp.max_downloads, self._max_download_limit()):]

        service = PDFDownloadService(ctx.mcp_registry)
        logger.info(f"S6b downloading {len(to_download)} PDFs (max_concurrent=5)")
        enriched = await service.batch_download_and_read(to_download)

        with_text: list[dict[str, Any]] = []
        without_text: list[dict[str, Any]] = []
        total_chars = 0

        for paper in enriched:
            text = paper.get("full_text")
            if text and len(text.strip()) > 50:
                with_text.append(paper)
                total_chars += len(text)
            else:
                paper["full_text"] = None
                without_text.append(paper)

        for paper in rest:
            paper["full_text"] = None
            without_text.append(paper)

        merged = with_text + without_text
        success_rate = len(with_text) / max(1, len(to_download))

        self._metrics.update({
            "attempted": len(to_download),
            "downloaded": len(with_text),
            "success_rate": round(success_rate, 3),
            "total_chars": total_chars,
            "avg_chars": round(total_chars / max(1, len(with_text))),
        })

        return PDFDownloadOutput(
            skill_name=self.name,
            papers_with_fulltext=merged,
            download_count=len(to_download),
            success_count=len(with_text),
            success_rate=success_rate,
            total_text_chars=total_chars,
        )

    def _max_download_limit(self) -> int:
        from shared.core.config import settings
        return settings.pdf_download_max

    async def quality_gate(self, output: PDFDownloadOutput, ctx: SkillContext) -> bool:
        return output.success
