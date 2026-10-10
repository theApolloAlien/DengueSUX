#!/usr/bin/env python3
"""Verify and record the real finishing-run UI, with no presentation overlays.

Use demo/.venv/bin/python demo/record_finishing_demo.py --verify-only for fresh
desktop/phone contexts, or omit the flag to also record the fallback MP4.
The journey never submits field reports or uses a personal location/address.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "output/verification"
DEMO = ROOT / "demo"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


async def overflow(page):
    return await page.evaluate("""() => ({viewport:innerWidth,document:document.documentElement.scrollWidth,
      body:document.body.scrollWidth,overflow:document.documentElement.scrollWidth>innerWidth+1})""")


async def click(page, selector):
    target = page.locator(selector).first
    await target.scroll_into_view_if_needed()
    await target.click()


async def ready(page, url):
    await page.goto(url, wait_until="domcontentloaded")
    await page.locator('#signals-view').wait_for(state="visible", timeout=30000)
    await page.locator('#area-detail .plan-button').wait_for(state="visible", timeout=30000)


async def verify(browser, url, width, height):
    context = await browser.new_context(viewport={"width": width, "height": height},
                                        device_scale_factor=1, reduced_motion="reduce")
    page = await context.new_page()
    page.set_default_timeout(12000)
    errors, failed_requests, checks, report_writes = [], [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: failed_requests.append({"path": urlsplit(request.url).path, "failure": request.failure}))
    page.on("request", lambda request: report_writes.append(urlsplit(request.url).path)
            if request.method == "POST" and urlsplit(request.url).path == "/api/reports" else None)

    async def check(name, selector=None):
        if selector:
            assert await page.locator(selector).first.is_visible(), name
        dimensions = await overflow(page)
        checks.append({"step": name, **dimensions})
        assert not dimensions["overflow"], f"Horizontal overflow at {name}: {dimensions}"
        await page.screenshot(path=str(VERIFY / f"finishing-{width}-{name}.png"))

    result = {"viewport": {"width": width, "height": height}, "fresh_context": True, "checks": checks,
              "errors": errors, "failed_requests": failed_requests, "status": "failed"}
    try:
        await ready(page, url)
        await check("overview", "#national-briefing")
        result["source_date_text"] = await page.locator('#data-timestamp').inner_text()
        result["briefing_text"] = await page.locator('#briefing-text').inner_text()
        result["sensitive_text_found"] = bool(re.search(r"ONEMAP_TOKEN\s*=|DATABRICKS_TOKEN\s*=|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}", await page.locator('body').inner_text()))
        assert not result["sensitive_text_found"], "Sensitive-looking value visible in page text"
        if await page.locator('#change-feed').is_visible():
            await click(page, '#change-feed summary')
            await check("changes", "#change-feed[open]")
            await click(page, '#change-feed summary')
        await click(page, '#check-locate')
        await page.wait_for_function("document.querySelector('#check-result').textContent.includes('permission was not given')")
        result["geolocation_denial"] = "Handled with an example/area-list fallback; no location granted."
        await click(page, '#check-example')
        await check("example", "#check-result")
        result["example_text"] = await page.locator('#check-result').inner_text()
        if width < 700 and await page.locator('#toggle-areas').is_visible():
            await click(page, '#toggle-areas')
        await page.get_by_role("button", name="Jurong West, High priority", exact=True).click()
        await page.locator('#area-detail').scroll_into_view_if_needed()
        await check("population", "#area-detail .plan-button")
        result["area_text"] = await page.locator('#area-detail').inner_text()
        assert "10,000" in result["area_text"], "Population context missing"
        await click(page, '#cluster-play')
        assert "Historical" in await page.locator('#cluster-timeline-note').inner_text()
        await check("timeline", "#cluster-timeline")
        await click(page, '#cluster-latest')
        await click(page, '#area-detail .plan-button')
        await check("plan", "#inspection-view")
        result["plan_heading"] = await page.locator('.inspection-heading').inner_text()
        assert await page.locator('[data-outcome]').count() > 0, "Field-report controls missing"
        await click(page, '[data-map-mode="3d"]')
        await page.wait_for_function("document.querySelector('#route-3d canvas') || document.querySelector('.route-3d-status')?.textContent.includes('unavailable')", timeout=25000)
        await page.wait_for_timeout(1800)
        await check("3d", "#route-3d")
        result["three_d_status"] = await page.locator('.route-3d-status').inner_text()
        result["three_d_canvas"] = await page.locator('#route-3d canvas').count() > 0
        result["reduced_motion_play_disabled"] = await page.locator('[data-tour="play"]').is_disabled()
        await click(page, '[data-tour="next"]')
        assert "Stop 2" in await page.locator('.route-tour-stop span').inner_text()
        await click(page, '#plan-notice')
        await page.locator('#notice-text').wait_for(state="visible")
        languages = {}
        for language in ["en", "zh", "ms", "ta"]:
            await click(page, f'[data-language="{language}"]')
            await page.locator(f'#notice-text[lang="{language}"]').wait_for(state="visible")
            await page.wait_for_timeout(400)
            languages[language] = bool((await page.locator('#notice-text').inner_text()).strip())
            await check(f"notice-{language}", "#notice-dialog")
        result["notice_languages"] = languages
        await click(page, '#close-notice')
        await click(page, '#back-to-areas')
        await click(page, '.view-tab[data-view="forecast"]')
        await check("forecast", "#live-outlook")
        result["live_outlook_text"] = await page.locator('#live-outlook').inner_text()
        assert "Likely between" in result["live_outlook_text"], "Forecast range missing"
        await click(page, '.mode-button[data-mode="replay"]')
        await check("replay", "#forecast-chart")
        assert "2022" in await page.locator('#forecast-subtitle').inner_text()
        result["report_writes"] = len(report_writes)
        assert not report_writes, "The verification must not submit field reports"
        assert not errors, "Browser console or page errors occurred; see evidence"
        result["status"] = "passed"
    except Exception as error:
        result["failure"] = str(error)
        await page.screenshot(path=str(VERIFY / f"finishing-{width}-failure.png"))
    finally:
        await context.close()
    result["cancelled_requests"] = [request for request in failed_requests if request["failure"] == "net::ERR_ABORTED"]
    result["failed_requests"] = [request for request in failed_requests if request["failure"] != "net::ERR_ABORTED"]
    if result["failed_requests"]:
        result["status"] = "failed"
        result["failure"] = "Network failures occurred; see evidence"
    return result


async def record(browser, url):
    stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    raw_dir = DEMO / "raw" / f"finishing_{stamp}"
    context = await browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                        record_video_dir=str(raw_dir), record_video_size={"width": 1440, "height": 900})
    page = await context.new_page()
    page.set_default_timeout(20000)
    await ready(page, url)
    await page.wait_for_timeout(1200)
    started = time.monotonic()
    scenes = []

    async def scene(name, seconds):
        scenes.append({"scene": name, "seconds": round(time.monotonic() - started, 2)})
        await page.wait_for_timeout(seconds * 1000)

    await scene("This week at a glance: clusters, people, High areas, national range", 4)
    await click(page, '#change-feed summary')
    await scene("What changed since the saved snapshot", 3)
    await click(page, '#change-feed summary')
    await click(page, '#check-example')
    await page.locator('#check-result').scroll_into_view_if_needed()
    await scene("Check my block using the public example", 4)
    await page.get_by_role("button", name="Jurong West, High priority", exact=True).click()
    await page.locator('#area-detail').scroll_into_view_if_needed()
    await scene("Raw cluster counts with resident population context", 3)
    await click(page, '#cluster-play')
    await scene("Saved cluster snapshots; dates are never filled", 3)
    await click(page, '#cluster-latest')
    await click(page, '#area-detail .plan-button')
    await scene("Jurong West inspection plan and homes covered", 4)
    await click(page, '[data-map-mode="3d"]')
    await page.locator('#route-3d canvas').wait_for(state="visible", timeout=25000)
    await page.wait_for_timeout(1500)
    await page.locator('.inspection-map-column').scroll_into_view_if_needed()
    await scene("3D walk preview: official HDB footprints of the route and nearby blocks", 3)
    await click(page, '[data-tour="play"]')
    await scene("Walk the route: steady follow camera on the saved OneMap path, stop callouts with checklists", 16)
    if await page.locator('[data-tour="play"]').get_attribute('aria-label') == 'Pause the walking preview':
        await click(page, '[data-tour="play"]')
    await click(page, '[data-tour="fit"]')
    await scene("Whole route from above: walked part highlighted, stops and cluster blocks", 3)
    await click(page, '#plan-notice')
    await page.locator('#notice-text').wait_for(state="visible")
    for language, label in [("en", "English"), ("zh", "Chinese"), ("ms", "Malay"), ("ta", "Tamil")]:
        await click(page, f'[data-language="{language}"]')
        await page.locator(f'#notice-text[lang="{language}"]').wait_for(state="visible")
        await scene(f"Resident notice draft: {label}", 2)
    await click(page, '#close-notice')
    await click(page, '#back-to-areas')
    await click(page, '.view-tab[data-view="forecast"]')
    await page.locator('#live-outlook').scroll_into_view_if_needed()
    await scene("Live forecast ranges and publication/weather disclosure", 6)
    await click(page, '.mode-button[data-mode="replay"]')
    await page.locator('#forecast-chart').scroll_into_view_if_needed()
    await click(page, '#replay-button')
    await scene("2022 outbreak replay", 5)
    filmed_seconds = time.monotonic() - started
    video = page.video
    await context.close()
    raw_path = Path(await video.path())
    duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(raw_path)], text=True))
    target = DEMO / f"denguesux_finishing_{stamp}.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(max(0, duration - filmed_seconds)),
                    "-i", str(raw_path), "-t", str(filmed_seconds), "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(target)], check=True)
    metadata = {"recorded_at_sgt": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
                "path": str(target.relative_to(ROOT)), "duration_seconds": round(filmed_seconds, 2),
                "viewport": {"width": 1440, "height": 900}, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "method": "Real browser interactions only; no overlays, fabricated captions, report submissions or personal location.",
                "scenes": scenes}
    save(DEMO / f"denguesux_finishing_{stamp}.json", metadata)
    return metadata


async def main(args):
    VERIFY.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader"])
        results = []
        for width, height in [(1440, 900), (390, 844)]:
            results.append(await verify(browser, args.url, width, height))
        evidence = {"verified_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "url": args.url,
                    "initial_tool": "agent-browser via npx; loaded app, inspected interactive snapshot, clicked the public block example",
                    "contexts": results, "status": "passed" if all(r["status"] == "passed" for r in results) else "failed"}
        save(VERIFY / "browser.json", evidence)
        print(json.dumps({"verification": evidence["status"], "contexts": [{"viewport": r["viewport"], "status": r["status"], "failure": r.get("failure")} for r in results]}), flush=True)
        if evidence["status"] != "passed":
            await browser.close()
            raise SystemExit(1)
        if not args.verify_only:
            print(json.dumps(await record(browser, args.url), ensure_ascii=False), flush=True)
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8787")
    parser.add_argument("--verify-only", action="store_true")
    asyncio.run(main(parser.parse_args()))
