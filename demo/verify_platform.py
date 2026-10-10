#!/usr/bin/env python3
"""Exercise DengueSUX failure, fallback and accessibility states in fresh browser contexts.

usage: demo/.venv/bin/python demo/verify_platform.py [BASE_URL] [--out DIR]

Never submits a field report, never sends a real location (geolocation is denied or
mocked to a public example block) and never posts to /api/locate with a home address.
Network failures are simulated with request interception, not by changing the server.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
GL = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']


async def ready(page, base, hash_='#signals'):
    await page.goto(base + '/' + hash_, wait_until='domcontentloaded')
    await page.wait_for_selector('body.is-ready, body.is-error', timeout=45000)
    await page.wait_for_timeout(600)


async def open_plan(page, area='Jurong West'):
    await page.evaluate("name => [...document.querySelectorAll('#area-list [data-area]')].find(b => b.getAttribute('aria-label').startsWith(name + ','))?.click()", area)
    await page.locator('#area-detail .plan-button').first.click()
    await page.wait_for_selector('#inspection-view:not([hidden]) .stop-list')


async def text(page, selector):
    return (await page.locator(selector).first.text_content() or '').strip()


async def main(base, out):
    out.mkdir(parents=True, exist_ok=True)
    results, failures = {}, []

    def check(name, ok, detail=''):
        results[name] = {'ok': bool(ok), 'detail': detail}
        if not ok:
            failures.append(name)

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=GL)

        # 1. Geolocation denied: a clear message, no location sent anywhere.
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 900}, permissions=[])
        page = await ctx.new_page()
        requests = []
        page.on('request', lambda r: requests.append(r.url))
        await ready(page, base)
        await page.evaluate("() => { navigator.geolocation.getCurrentPosition = (ok, fail) => fail({code: 1, message: 'denied'}); }")
        await page.click('#check-locate')
        message = await text(page, '#check-result')
        check('geolocation_denied_message', 'permission was not given' in message, message)
        check('geolocation_not_sent', not any('lat' in u and '/api/' in u for u in requests))

        # 2. Postal lookup unavailable (503) and not found (404) are worded differently.
        await page.route('**/api/locate?*', lambda route: route.fulfill(status=503, content_type='application/json',
                         body=json.dumps({'detail': 'Postal lookup is unavailable right now. Try “Use my location” or the example.'})))
        if await page.locator('#check-postal-form').is_visible():
            await page.fill('#check-postal', '000000')
            await page.click('#check-postal-form button')
            await page.wait_for_timeout(500)
            message = await text(page, '#check-result')
            check('postal_unavailable_message', 'unavailable' in message, message)
            await page.fill('#check-postal', '12')
            await page.click('#check-postal-form button')
            check('postal_validation_message', '6-digit' in await text(page, '#check-result'))
        else:
            check('postal_form_hidden_when_unconfigured', True, 'Postal lookup not offered by this server')
        await page.click('#check-example')
        check('example_block_result', 'cluster' in (await text(page, '#check-result')).lower())
        await page.screenshot(path=str(out / 'state-check-example.png'))

        # 3. Keyboard: choose an area from the list and keep focus on it; Escape closes the layers menu.
        await page.focus('#area-list [data-area]:nth-child(2)')
        await page.keyboard.press('Enter')
        focused = await page.evaluate("document.activeElement?.dataset?.area || document.activeElement?.className")
        check('area_selection_keeps_focus', bool(focused) and focused != 'BODY', str(focused))
        await page.click('#layers-button')
        await page.keyboard.press('Escape')
        check('escape_closes_layers', await page.locator('#layers-menu').is_hidden())
        await ctx.close()

        # 4. Inspection plan: print layout, missing footprints, blocked tiles.
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await ctx.new_page()
        await page.route('**/data/footprints.json', lambda route: route.fulfill(status=503, body='unavailable'))
        await page.route('**/onemap.gov.sg/maps/tiles/**', lambda route: route.abort())
        await ready(page, base)
        await open_plan(page)
        await page.emulate_media(media='print')
        await page.screenshot(path=str(out / 'state-plan-print.png'), full_page=True)
        hidden_in_print = await page.evaluate("getComputedStyle(document.querySelector('.stop-report')).display")
        check('print_hides_report_buttons', hidden_in_print == 'none', hidden_in_print)
        await page.emulate_media(media='screen')
        await page.click('[data-map-mode="3d"]')
        await page.wait_for_function("() => /unavailable|shapes/.test(document.querySelector('.route-3d-status')?.textContent || '')", timeout=30000)
        await page.wait_for_timeout(2500)
        status = await text(page, '.route-3d-status')
        check('missing_footprints_or_tiles_labelled', 'unavailable' in status.lower(), status)
        await page.screenshot(path=str(out / 'state-3d-missing-data.png'))
        await ctx.close()

        # 5. Reduced motion: no autoplay; Next and arrow keys move instantly and sync the checklist.
        ctx = await browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
        page = await ctx.new_page()
        await ready(page, base)
        await open_plan(page)
        await page.click('[data-map-mode="3d"]')
        await page.wait_for_function("() => /block shapes|unavailable/.test(document.querySelector('.route-3d-status')?.textContent || '')", timeout=30000)
        check('reduced_motion_play_disabled', await page.locator('[data-tour=play]').is_disabled())
        await page.click('[data-tour=next]')
        await page.keyboard.press('ArrowRight')
        stop = await text(page, '.route-tour-stop span')
        selected = await page.evaluate("document.querySelector('.inspection-stop.is-tour-selected')?.querySelector('h3')?.textContent")
        check('stop_and_checklist_in_sync', 'Stop 3 of' in stop and bool(selected) and selected in stop, f'{stop} | {selected}')
        overflow = await page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
        check('phone_no_horizontal_overflow', not overflow)
        await page.screenshot(path=str(out / 'state-3d-reduced-motion-phone.png'))
        await ctx.close()

        # 5b. Walk the whole route at 2x: completes, camera turns stay gentle, slider and checklist follow.
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await ctx.new_page()
        await ready(page, base)
        await open_plan(page, 'Bishan')
        await page.click('[data-map-mode="3d"]')
        await page.wait_for_function("() => /block shapes|unavailable/.test(document.querySelector('.route-3d-status')?.textContent || '')", timeout=30000)
        await page.click('[data-tour=speed]')
        await page.click('[data-tour=play]')
        samples, done = [], None
        for _ in range(600):
            await page.wait_for_timeout(200)
            snap = await page.evaluate('window.RouteFlythrough.snapshot()')
            samples.append((await page.evaluate('performance.now()') / 1000, snap))
            if not snap['playing'] and snap['total'] and snap['along'] >= snap['total'] - 1:
                done = snap
                break
        rates = []
        for (t1, a), (t2, b) in zip(samples, samples[1:]):
            if a['phase'] in ('walking', 'dwell') and b['phase'] in ('walking', 'dwell') and t2 > t1:
                rates.append(abs(((b['bearing'] - a['bearing'] + 540) % 360) - 180) / (t2 - t1))
        check('walk_reaches_end_of_route', done is not None and 'Route complete' in await text(page, '.route-tour-stop span'), await text(page, '.route-tour-stop span'))
        check('walk_turn_rate_bounded', bool(rates) and max(rates) <= 45, f'max {max(rates or [0]):.1f} deg/s over {len(rates)} samples')
        check('walk_slider_at_end', await page.input_value('#route-scrub-input') == '1000')
        await page.fill('#route-scrub-input', '500')
        await page.dispatch_event('#route-scrub-input', 'input')
        scrub = await text(page, '.route-scrub-text')
        selected = await page.evaluate("document.querySelector('.inspection-stop.is-tour-selected h3')?.textContent || ''")
        check('scrub_moves_view_and_checklist', scrub.startswith('0.4') and selected in await text(page, '.route-tour-stop span'), f'{scrub} | {selected}')
        await page.screenshot(path=str(out / 'state-walk-complete.png'))
        await ctx.close()

        # 6. No WebGL: the 3D tab falls back to the 2D map and checklist.
        nogl = await p.chromium.launch(args=['--disable-webgl', '--disable-3d-apis'])
        ctx = await nogl.new_context(viewport={'width': 1280, 'height': 860})
        page = await ctx.new_page()
        await ready(page, base)
        await open_plan(page)
        await page.click('[data-map-mode="3d"]')
        await page.wait_for_function("() => /unavailable/.test(document.querySelector('.route-3d-status')?.textContent || '')", timeout=30000)
        check('no_webgl_fallback', await page.locator('#inspection-map').is_visible(), await text(page, '.route-3d-status'))
        await nogl.close()

        # 7. Stale forecast: after the target week, the national cell says Unavailable instead of an old number.
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await ctx.new_page()
        await page.clock.install(time='2026-11-20T09:00:00+08:00')
        await ready(page, base)
        value = await text(page, '#national-value')
        check('stale_forecast_labelled_unavailable', value == 'Unavailable', value)
        await page.screenshot(path=str(out / 'state-stale-forecast.png'))
        await ctx.close()

        # 8. Saved data unavailable: friendly error state with retry.
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await ctx.new_page()
        await page.route('**/data/dashboard.json', lambda route: route.fulfill(status=503, body='{}'))
        await ready(page, base)
        check('api_failure_error_state', await page.locator('#error-state').is_visible(), await text(page, '#error-message'))
        await page.screenshot(path=str(out / 'state-api-failure.png'))
        await ctx.close()
        await browser.close()

    summary = {'base_url': base, 'checks': results, 'failed': failures, 'passed': len(results) - len(failures), 'total': len(results)}
    (out / 'platform_states.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', nargs='?', default='http://127.0.0.1:8787')
    parser.add_argument('--out', type=Path, default=ROOT / 'output/verification/platform')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.base.rstrip('/'), args.out)))
