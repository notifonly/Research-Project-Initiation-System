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
OUT_DIR = ROOT / "assets"
OUT_FILE = OUT_DIR / "dashboard_overview.png"


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    url = DASHBOARD_HTML.resolve().as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
        )
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector("#main", state="visible")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(OUT_FILE), full_page=False)
        await browser.close()

    print(f"Saved dashboard screenshot: {OUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
