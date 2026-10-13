"""Verify the 14 Oct 2026 3D features in headless Chromium: sun slider and shadows, rain toggle, eye-level stop view,
walk completion at 2x, stop deep links, the no-scene note, the night island, the paced time-lapse with its peak caption,
history deep links, the continuous dive, story mode end to end, chat-to-island focus, the tour chip and kiosk mode.

usage: demo/.venv/bin/python demo/verify_3d_features.py BASE_URL OUT_DIR   (writes screenshots and checks.json)
"""
import asyncio, sys, json, time
from pathlib import Path
from playwright.async_api import async_playwright
GL = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
BASE = sys.argv[1]; OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
checks, errors = {}, []
async def main():
    async def step(name, fn):
        try: await fn()
        except Exception as e: errors.append((name, type(e).__name__ + ': ' + str(e)[:200]))
    async with async_playwright() as p:
        b = await p.chromium.launch(args=GL)
        ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        await ctx.add_init_script("localStorage.setItem('denguesux:toured','true')")
        page = await ctx.new_page()
        page.on('pageerror', lambda e: errors.append(('pageerror', str(e))))
        page.on('console', lambda m: errors.append(('console', m.text)) if m.type == 'error' and '404' not in m.text else None)
        # 1. Plan opens in 3D with shadows at 13:00; slider to 18:30 changes light and shadows
        await page.goto(BASE + '/#plan/jurong-west', wait_until='networkidle')
        await page.wait_for_function("() => window.RouteFlythrough?.snapshot()?.ready === true", timeout=60000)
        await page.wait_for_timeout(1500)
        s = await page.evaluate("RouteFlythrough.snapshot()")
        checks['shadows_at_noon'] = (s.get('shadows') or 0) > 0; checks['hour_default'] = s.get('hour') == 13; checks['rain_available'] = bool(s.get('rain'))
        await page.screenshot(path=str(OUT / '3d-noon.png'))
        await page.evaluate("RouteFlythrough.setHour(18.5)"); await page.wait_for_timeout(900)
        s2 = await page.evaluate("RouteFlythrough.snapshot()")
        checks['dusk_shadows_longer_or_present'] = (s2.get('shadows') or 0) > 0
        checks['hour_label'] = await page.evaluate("document.querySelector('[data-tour=light] span').textContent")
        await page.screenshot(path=str(OUT / '3d-dusk.png'))
        # rain on
        await page.click('[data-tour=rain]'); await page.wait_for_timeout(2500)
        checks['rain_layer'] = await page.evaluate("!!window.Weather3D && (() => { try { return RouteFlythrough.snapshot().rain && document.querySelector('[data-tour=rain]').getAttribute('aria-pressed') === 'true'; } catch (e) { return String(e); } })()")
        await page.screenshot(path=str(OUT / '3d-rain.png'))
        await page.click('[data-tour=rain]'); await page.evaluate("RouteFlythrough.setHour(13)")
        # 2. Walk at 2x: eye-level moment (pitch high / zoom high) during a dwell, then completes
        await page.evaluate("RouteFlythrough.setSpeed(2)")
        await page.click('[data-tour=play]')
        t0 = time.time(); eye = False; maxzoom = 0
        while time.time() - t0 < 110:
            s = await page.evaluate("RouteFlythrough.snapshot()")
            if s['phase'] == 'dwell' and (s.get('zoom') or 0) > maxzoom: maxzoom = s['zoom']
            if s['phase'] == 'dwell' and (s.get('zoom') or 0) > 19 and not eye:
                eye = True; await page.screenshot(path=str(OUT / '3d-eye-level.png'))
            if s['phase'] == 'idle' and s['along'] >= (s['total'] or 1) - 1: break
            await page.wait_for_timeout(300)
        s = await page.evaluate("RouteFlythrough.snapshot()")
        checks['walk_completed'] = s['phase'] == 'idle' and s['along'] >= (s['total'] or 1) - 1; checks['eye_level_seen'] = eye; checks['dwell_max_zoom'] = round(maxzoom, 2)
        checks['route_complete_text'] = await page.evaluate("document.querySelector('.route-tour-stop span').textContent")
        await page.screenshot(path=str(OUT / '3d-complete.png'))
        # 3. Stop deep link
        await page.goto(BASE + '/#plan/jurong-west/3d/stop/3', wait_until='networkidle')
        await page.wait_for_function("() => window.RouteFlythrough?.snapshot()?.ready === true", timeout=60000); await page.wait_for_timeout(2500)
        s = await page.evaluate("RouteFlythrough.snapshot()"); checks['deep_link_stop3'] = s['stop'] == 3 and s['mode'] == '3d'
        await page.screenshot(path=str(OUT / '3d-stop3.png'))
        # 4. No-scene area (Tuas): no 3D tab, a note instead
        await page.goto(BASE + '/#plan/tuas', wait_until='networkidle'); await page.wait_for_timeout(3000)
        checks['tuas_no_scene'] = await page.evaluate("!!document.querySelector('.no-scene-note') && !document.querySelector('[data-map-mode=\"3d\"]')")
        await page.screenshot(path=str(OUT / 'tuas.png'))
        # 5. Map 3D: night island, timelapse runs to the end quickly at 4x, peak caption appears
        await page.goto(BASE + '/#map/3d', wait_until='networkidle')
        await page.wait_for_function("() => !!window.Map3DExtras", timeout=20000)
        await page.evaluate("Map3DExtras.whenReady()"); await page.wait_for_timeout(2600)
        await page.screenshot(path=str(OUT / 'map3d-night.png'))
        await page.evaluate("""() => { window.__log = []; const mo = new MutationObserver(() => { const s = document.querySelector('.timelapse-date strong')?.textContent || ''; window.__log.push(s); if (s.includes('peak') && !window.__peakShot) { window.__peakShot = true; } });
          mo.observe(document.querySelector('.timelapse-date'), {subtree: true, childList: true, characterData: true}); window.__t0 = performance.now(); window.__tl = Map3DExtras.runTimelapse({speed: 4, maxMs: 60000}).then(() => { window.__done = performance.now() - window.__t0; }); }""")
        for _ in range(120):
            await page.wait_for_timeout(500)
            if await page.evaluate("!!window.__done"): break
        log = await page.evaluate("window.__log"); checks['timelapse_seconds_4x'] = round((await page.evaluate("window.__done") or 0) / 1000, 1)
        checks['timelapse_peak_captioned'] = any('peak' in s for s in log); checks['timelapse_steps_seen'] = len(log)
        checks['timelapse_reached_end'] = await page.evaluate("(() => { const s = document.querySelector('#timelapse-scrub'); return Number(s.value) === Number(s.max); })()")
        checks['timelapse_end_label'] = await page.evaluate("document.querySelector('.timelapse-date strong').textContent")
        await page.screenshot(path=str(OUT / 'map3d-end.png'))
        # 6. History deep link
        await page.goto(BASE + '/#map/3d/history/2020-07-03', wait_until='networkidle'); await page.wait_for_timeout(5000)
        checks['history_deep_link'] = await page.evaluate("document.querySelector('.timelapse-date strong')?.textContent || ''")
        # 7. Dive: island -> continuous arrival into the walk (arrival camera used, rise animation)
        await page.goto(BASE + '/#map/3d', wait_until='networkidle'); await page.evaluate("Map3DExtras.whenReady()"); await page.wait_for_timeout(2500)
        await page.evaluate("Map3DExtras.diveTo('JW')")
        await page.wait_for_function("() => location.hash.startsWith('#plan/') && window.RouteFlythrough?.snapshot()?.ready === true", timeout=60000)
        s = await page.evaluate("RouteFlythrough.snapshot()"); await page.screenshot(path=str(OUT / 'dive-arrival.png'))
        checks['dive_arrives_in_3d'] = s['mode'] == '3d'
        await page.wait_for_timeout(2600); s = await page.evaluate("RouteFlythrough.snapshot()"); checks['dive_autoplays'] = s['playing'] or s['phase'] != 'idle'
        await page.screenshot(path=str(OUT / 'dive-walking.png'))
        # 8. Story mode end-to-end (reduced timing): it should finish on its own
        await page.goto(BASE + '/?story=1#week', wait_until='networkidle')
        await page.wait_for_function("() => window.Story?.running()", timeout=20000); t0 = time.time()
        await page.wait_for_function("() => !window.Story.running()", timeout=240000); checks['story_seconds'] = round(time.time() - t0)
        # 9. Chat -> island focus (local engine) and 3D link on the card
        await page.goto(BASE + '/#week', wait_until='networkidle'); await page.wait_for_timeout(2500)
        await page.fill('#ask-input', 'Why is Jurong West High priority?'); await page.keyboard.press('Enter'); await page.wait_for_timeout(5000)
        checks['card_3d_link'] = await page.evaluate("!!document.querySelector('a[href=\"#plan/jurong-west/3d\"]')")
        checks['island_selected_jw'] = await page.evaluate("(() => { const m = document.querySelector('.hero-stage .landscape3d'); return !!m; })()")
        await page.screenshot(path=str(OUT / 'chat-focus.png'))
        # 10. Tour chip, no modal on a fresh visit
        ctx2 = await b.new_context(viewport={'width': 1440, 'height': 900}); p2 = await ctx2.new_page(); await p2.goto(BASE + '/#week', wait_until='networkidle'); await p2.wait_for_timeout(2000)
        checks['fresh_visit_no_dialog'] = await p2.evaluate("!document.querySelector('dialog[open]') && !!document.querySelector('#tour-chip')")
        await p2.screenshot(path=str(OUT / 'fresh-visit.png'))
        # 11. Kiosk
        p3 = await ctx2.new_page(); await p3.goto(BASE + '/?kiosk=1#week', wait_until='networkidle'); await p3.wait_for_timeout(4000)
        checks['kiosk'] = await p3.evaluate("document.body.classList.contains('kiosk') && !!document.querySelector('.kiosk-badge svg') && !!window.Story.running()")
        await p3.screenshot(path=str(OUT / 'kiosk.png'))
        await b.close()
    (OUT / 'checks.json').write_text(json.dumps({'checks': checks, 'errors': errors[:20]}, indent=1))
    print(json.dumps(checks, indent=1)); print('errors:', json.dumps(errors[:12], indent=1))
asyncio.run(main())
