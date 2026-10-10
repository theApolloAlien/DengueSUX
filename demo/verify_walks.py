"""Verify the 3D release in headless Chromium: a 3D walk or flyover for all 55 areas, the 3D checklist
illustrations, the 3D landscapes, the forecast chart and deep links. Writes JSON results and screenshots.

usage: demo/.venv/bin/python demo/verify_walks.py [BASE_URL] [--out DIR]
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

GL = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
ROOT = Path(__file__).resolve().parents[1]


def slug(name):
    return re.sub(r'-$', '', re.sub(r'[^a-z0-9]+', '-', name.lower()))


async def page_for(browser, base, width=1440, height=900, **kwargs):
    context = await browser.new_context(viewport={'width': width, 'height': height}, **kwargs)
    await context.add_init_script("localStorage.setItem('denguesux:toured','true')")
    page = await context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    return context, page, errors


async def main(base, out):
    out.mkdir(parents=True, exist_ok=True)
    areas = json.loads((ROOT / 'output/web/current.json').read_text())['areas']
    results, checks = {}, {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=GL)
        # Every planning area: the field plan opens in 3D on desktop and builds a walk or a flyover.
        context, page, errors = await page_for(browser, base)
        await page.goto(base + '/#week', wait_until='networkidle')
        for area in areas:
            await page.evaluate("h => { location.hash = h; }", '#plan/' + slug(area['name']))
            try:
                await page.wait_for_function("() => window.RouteFlythrough?.snapshot()?.ready === true", timeout=30000)
                snap = await page.evaluate("RouteFlythrough.snapshot()")
                ok = bool(snap['total']) and (snap['tour'] or snap['stops'] > 1)
                results[area['code']] = {'name': area['name'], 'ok': ok, 'mode': 'flyover' if snap['tour'] else 'walk', 'stops': snap['stops'],
                                         'route_m': round(snap['total']), 'parks_and_water': snap['landuse']}
            except Exception as exc:  # recorded, not raised: one area must not hide the others
                results[area['code']] = {'name': area['name'], 'ok': False, 'error': type(exc).__name__}
        checks['all_areas_3d'] = all(r['ok'] for r in results.values())
        checks['area_errors'] = [e for e in errors if 'Transition was aborted' not in e]
        # One walk end to end at double speed: pauses at a stop with a 3D illustration and a highlight on the block.
        await page.evaluate("h => { location.hash = h; }", '#plan/toa-payoh')
        await page.wait_for_function("() => RouteFlythrough.snapshot()?.ready === true", timeout=30000)
        await page.click('[data-tour=speed]')
        await page.click('[data-tour=play]')
        await page.wait_for_function("() => RouteFlythrough.snapshot().phase === 'dwell' && RouteFlythrough.snapshot().stop >= 2", timeout=60000)
        snap = await page.evaluate("RouteFlythrough.snapshot()")
        checks['walk_pauses_with_illustration'] = bool(snap['look']) and snap['bands'] == snap['look']
        await page.wait_for_function("() => document.querySelector('.route-stop-card canvas')", timeout=15000)
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(out / 'walk-stop-card-1440.png'))
        await page.click('[data-tour=play]')  # pause
        # Checklist thumbnails open the animated illustration dialog.
        await page.locator('.look-thumb').first.click()
        await page.wait_for_function("() => document.querySelector('#look-dialog[open] canvas')", timeout=20000)
        await page.wait_for_timeout(1500)
        checks['illustration_dialog'] = await page.evaluate("document.querySelectorAll('#look-dialog [role=tab]').length") >= 3
        await page.screenshot(path=str(out / 'illustration-dialog-1440.png'))
        await page.keyboard.press('Escape')
        # Flyover for an area with no verified place to walk.
        await page.evaluate("h => { location.hash = h; }", '#plan/tuas')
        await page.wait_for_function("() => RouteFlythrough.snapshot()?.ready === true && RouteFlythrough.snapshot().tour", timeout=30000)
        await page.click('[data-tour=play]')
        await page.wait_for_timeout(3000)
        checks['flyover_moves'] = (await page.evaluate("RouteFlythrough.snapshot().along")) > 0
        await page.screenshot(path=str(out / 'flyover-tuas-1440.png'))
        # Home hero landscape, then the Map's 3D view; the map deep link from Forecast must not throw.
        await page.goto(base + '/#week', wait_until='networkidle')
        await page.wait_for_selector('.hero-stage.is-ready', timeout=30000)
        await page.wait_for_timeout(1500)
        checks['hero_3d'] = await page.evaluate("!!document.querySelector('.hero-stage canvas')")
        checks['home_overflow'] = await page.evaluate("document.documentElement.scrollWidth > innerWidth")
        await page.screenshot(path=str(out / 'home-hero-1440.png'))
        await page.goto(base + '/#forecast', wait_until='networkidle')
        checks['forecast_chart'] = await page.evaluate("!!document.querySelector('.outlook-chart svg polyline.oc-actual')")
        before = len(errors)
        await page.evaluate("location.hash = '#map/bedok'")
        await page.wait_for_function("() => document.title.startsWith('Map / Bedok')", timeout=10000)
        checks['deep_link_from_hidden_map'] = len([e for e in errors[before:] if 'LatLng' in e]) == 0
        await page.click('[data-map-view="3d"]')
        await page.wait_for_selector('.map-3d-host.is-ready', timeout=30000)
        await page.wait_for_timeout(1200)
        checks['map_3d'] = True
        await page.screenshot(path=str(out / 'map-3d-1440.png'))
        checks['errors'] = [e for e in errors if 'Transition was aborted' not in e]
        await context.close()
        # Phone: hero and a walk plan (2D by default there), no horizontal overflow.
        context, page, errors = await page_for(browser, base, 390, 844, is_mobile=True, has_touch=True)
        await page.goto(base + '/#week', wait_until='networkidle')
        await page.wait_for_selector('.hero-stage.is-ready', timeout=30000)
        await page.wait_for_timeout(1200)
        checks['phone_overflow'] = await page.evaluate("document.documentElement.scrollWidth > innerWidth")
        await page.screenshot(path=str(out / 'home-hero-390.png'))
        await page.goto(base + '/#plan/bedok', wait_until='networkidle')
        await page.wait_for_selector('.stop-list .inspection-stop', timeout=20000)
        checks['phone_plan_overflow'] = await page.evaluate("document.documentElement.scrollWidth > innerWidth")
        checks['phone_errors'] = [e for e in errors if 'Transition was aborted' not in e]
        await context.close()
        await browser.close()
    passed = (checks['all_areas_3d'] and checks['walk_pauses_with_illustration'] and checks['illustration_dialog'] and checks['flyover_moves']
              and checks['hero_3d'] and checks['forecast_chart'] and checks['deep_link_from_hidden_map'] and checks['map_3d']
              and not checks['home_overflow'] and not checks['phone_overflow'] and not checks['phone_plan_overflow']
              and not checks['errors'] and not checks['phone_errors'] and not checks['area_errors'])
    report = {'passed': passed, 'checks': checks, 'areas': results,
              'summary': {'areas': len(results), 'walks': sum(r.get('mode') == 'walk' for r in results.values()),
                          'flyovers': sum(r.get('mode') == 'flyover' for r in results.values()), 'failed': [c for c, r in results.items() if not r['ok']]}}
    (out / 'walks_verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'passed': passed, **report['summary'], **{k: v for k, v in checks.items() if k not in ('errors', 'phone_errors', 'area_errors')},
                      'errors': checks['errors'][:3] + checks['phone_errors'][:3] + checks['area_errors'][:3]}, indent=2))
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base', nargs='?', default='http://127.0.0.1:8787')
    parser.add_argument('--out', default=str(ROOT / 'output/verification/walks'))
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(main(args.base.rstrip('/'), Path(args.out))) else 1)
