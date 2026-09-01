"""Capture AIscience dashboard screenshots with Playwright.

Requires the optional `playwright` package and a Chromium install:

    python -m pip install playwright
    python -m playwright install chromium

Usage:
    python scripts/capture_dashboard_screenshot.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_HTML = ROOT / "dashboard" / "index_standalone.html"
OUT_DIR = ROOT / "assets" / "screenshots"
OUT_FILE = OUT_DIR / "dashboard_overview.png"

TABS = [
    ("overview", "dashboard_overview.png"),
    ("evidence", "dashboard_evidence.png"),
    ("gaps", "dashboard_gaps.png"),
    ("hypotheses", "dashboard_hypotheses.png"),
    ("pipeline", "dashboard_pipeline.png"),
    ("compare", "dashboard_compare.png"),
    ("proposals", "dashboard_proposals.png"),
    ("decompose", "dashboard_decompose.png"),
    ("p05", "dashboard_p05.png"),
    ("p08", "dashboard_p08.png"),
    ("p09", "dashboard_p09.png"),
]


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    url = DASHBOARD_HTML.resolve().as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
        )
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector("#main", state="visible")
        await page.wait_for_timeout(2000)
        await page.click("#btn-enter")
        await page.wait_for_selector("nav.tabs button[data-tab='overview']", state="visible")
        await page.wait_for_timeout(1500)

        for tab_id, filename in TABS:
            await page.click(f'nav.tabs button[data-tab="{tab_id}"]')
            await page.wait_for_selector(f"#tab-{tab_id}.active", state="visible")
            await page.wait_for_timeout(1800)
            await page.screenshot(
                path=str(OUT_DIR / filename),
                full_page=True,
            )
            print(f"Saved {filename}")

        # Keep a dark-mode overview for visual contrast.
        await page.click("#themeBtn")
        await page.wait_for_timeout(800)
        await page.screenshot(
            path=str(OUT_DIR / "dashboard_overview_dark.png"),
            full_page=True,
        )
        print("Saved dashboard_overview_dark.png")
        await browser.close()

    print(f"Screenshots saved to: {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
