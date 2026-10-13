"""Record the in-app story mode as the Demo Day fallback video (WebM, 1440x900).

usage: demo/.venv/bin/python demo/record_story.py [BASE_URL] [--seconds 100]
"""
import argparse
import asyncio
import datetime as dt
import shutil
from pathlib import Path

from playwright.async_api import async_playwright

GL = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
ROOT = Path(__file__).resolve().parents[1]


async def main(base, seconds):
    raw = ROOT / 'demo/raw_story'
    shutil.rmtree(raw, ignore_errors=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=GL)
        context = await browser.new_context(viewport={'width': 1440, 'height': 900}, record_video_dir=str(raw), record_video_size={'width': 1440, 'height': 900})
        await context.add_init_script("localStorage.setItem('denguesux:toured','true')")
        page = await context.new_page()
        await page.goto(base + '/?story=1#week', wait_until='networkidle')
        await page.wait_for_timeout(seconds * 1000)
        video = page.video
        await context.close()
        await browser.close()
        source = Path(await video.path())
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    target = ROOT / f'demo/denguesux_story_{stamp}.webm'
    source.replace(target)
    shutil.rmtree(raw, ignore_errors=True)
    print(target)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('base', nargs='?', default='http://127.0.0.1:8765')
    ap.add_argument('--seconds', type=int, default=100)
    args = ap.parse_args()
    asyncio.run(main(args.base, args.seconds))
