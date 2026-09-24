"""Capture Devpost gallery screenshots (3:2, 2x) from the running DengueSUX prototype.

Run the app first (see README), then:
    demo/.venv/bin/python deck/gallery/capture_real.py
Screens are taken through the real UI controls; nothing in the app is modified.
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8787"
OUT = Path(__file__).resolve().parent / "real"
OUT.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1500, "height": 1000}, device_scale_factor=2)
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=OUT / "1_area_signals.png")

        await page.locator(".plan-button").first.click()
        await page.locator(".inspection-stop").first.wait_for()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2500)
        await page.screenshot(path=OUT / "2_inspection_plan.png")

        await page.locator("#plan-notice").click()
        await page.locator('[data-language="zh"]').click()
        await page.wait_for_timeout(1200)
        await page.screenshot(path=OUT / "3_resident_notice.png")
        await page.locator("#close-notice").click()
        await page.locator("#back-to-areas").click()
        await page.wait_for_timeout(800)

        await page.locator("#ask-fab").click()
        count = await page.locator(".ask-bot").count()
        await page.locator("#ask-input").fill("Why is Jurong East High?")
        await page.locator("#ask-input").press("Enter")
        await page.wait_for_function(f"document.querySelectorAll('.ask-bot').length > {count}")
        await page.locator(".ask-bot").last.locator(".ask-body").wait_for()
        await page.wait_for_timeout(1000)
        await page.screenshot(path=OUT / "4_ask_denguesux.png")
        await page.locator(".ask-close").click()

        await page.locator('.rail-button[data-view="forecast"]').click()
        await page.wait_for_timeout(1500)
        await page.mouse.wheel(0, 260)
        await page.wait_for_timeout(1200)
        await page.screenshot(path=OUT / "5_forecast_replay.png")
        await browser.close()
    for f in sorted(OUT.glob("*.png")):
        print(f, f.stat().st_size)


asyncio.run(main())
