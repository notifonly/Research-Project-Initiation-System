"""Capture a single P09 passed research-proposal case study.

The output is a long, self-contained image containing the proposal summary,
technical roadmap, red-team review, critique, scoring history, and citation
checks from the highest-scoring P09 candidate.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_HTML = ROOT / "dashboard" / "index_standalone.html"
OUT_FILE = ROOT / "assets" / "screenshots" / "p09_passed_case_study.png"


async def main() -> None:
    OUT_FILE.parent.mkdir(exist_ok=True)
    url = DASHBOARD_HTML.resolve().as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector("#main", state="visible")
        await page.click("#btn-enter")
        await page.wait_for_selector("nav.tabs button[data-tab='p09']", state="visible")

        await page.click("nav.tabs button[data-tab='p09']")
        await page.wait_for_selector("#tab-p09.active", state="visible")
        await page.wait_for_timeout(1500)

        await page.locator("#p09-table-wrap .stat-card.cursor").first.click()
        await page.wait_for_selector("#modalContent", state="visible")
        await page.wait_for_timeout(800)

        await page.evaluate(
            """
            () => {
              const overlay = document.getElementById('modalOverlay');
              const content = document.getElementById('modalContent');
              if (overlay) {
                overlay.style.overflow = 'visible';
                overlay.style.maxHeight = 'none';
              }
              if (content) {
                content.style.maxHeight = 'none';
                content.style.overflow = 'visible';
              }
              document.querySelectorAll('#modalContent details').forEach((d) => {
                d.open = true;
              });
            }
            """
        )
        await page.wait_for_timeout(500)
        await page.locator("#modalContent").screenshot(path=str(OUT_FILE))
        await browser.close()

    print(f"Saved P09 case study screenshot: {OUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
