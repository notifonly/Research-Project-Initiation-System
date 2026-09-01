from __future__ import annotations

import asyncio
import io
import re
from typing import Any, Optional

import pypdf

from shared.core.config import settings
from shared.core.logging_setup import get_logger
from shared.mcp.registry import MCPRegistry

logger = get_logger("pdf_service")


class PDFDownloadService:
    """Unified PDF download with OA-first fallback chain.

    Chain order (stops at first success):
    1. Direct OA URL from paper metadata
    2. arXiv (if arXiv ID available)
    3. PubMed Central (OA subset)
    4. Europe PMC (OA subset)
    5. CORE (repository aggregator)
    6. Unpaywall DOI resolution (if email configured)
    """

    FALLBACK_SOURCES = ["arxiv", "pmc", "europe_pmc", "core"]

    def __init__(self, registry: MCPRegistry) -> None:
        self._registry = registry
        self._semaphore = asyncio.Semaphore(5)

    async def download_with_fallback(self, paper: dict[str, Any]) -> Optional[bytes]:
        oa_url = paper.get("oa_pdf_url") or paper.get("open_access_pdf_url") or paper.get("full_text_url")
        if oa_url:
            result = await self._try_direct_url(oa_url)
            if result:
                return result

        for source in self.FALLBACK_SOURCES:
            mcp = self._registry.get(source)
            if mcp is None:
                continue
            try:
                paper_id = self._extract_id(paper, source)
                if not paper_id:
                    continue
                result = await mcp.download_pdf(paper_id)
                if result.success and isinstance(result.data, bytes):
                    return result.data
            except Exception as e:
                logger.debug(f"[{source}] download failed for {paper.get('doi', '?')}: {e}")

        if settings.unpaywall_email:
            result = await self._try_unpaywall(paper.get("doi"))
            if result:
                return result

        return None

    async def extract_text(self, pdf_bytes: bytes, max_pages: int = 30) -> str:
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            parts: list[str] = []
            for page in reader.pages[:max_pages]:
                text = page.extract_text()
                if text:
                    parts.append(text)
            return "\n".join(parts)
        except Exception as e:
            logger.warning(f"PDF text extraction failed: {e}")
            return ""

    async def download_and_read(self, paper: dict[str, Any]) -> Optional[str]:
        pdf_bytes = await self.download_with_fallback(paper)
        if pdf_bytes is None:
            return None
        return await self.extract_text(pdf_bytes)

    async def batch_download_and_read(
        self, papers: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        async def _process_one(paper: dict[str, Any]) -> dict[str, Any]:
            async with self._semaphore:
                text = await self.download_and_read(paper)
                result = dict(paper)
                result["full_text"] = text
                result["full_text_source"] = "pdf" if text else "abstract"
                return result

        tasks = [_process_one(p) for p in papers]
        return await asyncio.gather(*tasks)

    async def _try_direct_url(self, url: str) -> Optional[bytes]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=settings.pdf_download_timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                if b"%PDF" in resp.content[:8]:
                    return resp.content
        except Exception:
            pass
        return None

    async def _try_unpaywall(self, doi: Optional[str]) -> Optional[bytes]:
        if not doi or not settings.unpaywall_email:
            return None
        import httpx
        try:
            url = f"https://api.unpaywall.org/v2/{doi}?email={settings.unpaywall_email}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                best_oa = (data.get("best_oa_location") or {}) or {}
                pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
                if pdf_url:
                    return await self._try_direct_url(pdf_url)
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_id(paper: dict[str, Any], source: str) -> Optional[str]:
        if source == "arxiv":
            aid = paper.get("arxiv_id")
            if aid:
                return aid
            url = paper.get("url", "")
            m = re.search(r"arxiv\.org/(?:abs|pdf)/([\d.]+(?:v\d+)?)", url)
            return m.group(1) if m else None
        if source in ("pmc", "europe_pmc"):
            return paper.get("pmcid") or paper.get("pmc_id")
        if source == "core":
            return paper.get("core_id")
        return None
