"""Computed-style snapshot of every app view at several widths, for proving a stylesheet change is invisible.

Dumps, per state, the computed style of every element (and its ::before/::after) keyed by a stable DOM path,
plus a screenshot. Run once before a CSS change and once after, then compare with demo/style_diff.py.

usage: demo/.venv/bin/python demo/style_snapshot.py [BASE_URL] --out DIR
"""
import argparse
import asyncio
import gzip
import json
from pathlib import Path

from playwright.async_api import async_playwright

GL = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
DUMP = """
() => {
  const skip = el => el.closest('.leaflet-container, .maplibregl-map, canvas, svg');
  const out = {};
  const path = el => { const parts = []; for (let n = el; n && n !== document.body; n = n.parentElement) {
      let i = 0; for (let s = n; s = s.previousElementSibling;) i++; parts.unshift(n.tagName.toLowerCase() + ':' + i); } return parts.join('>'); };
  for (const el of document.querySelectorAll('body, body *')) {
    if (el !== document.body && skip(el)) continue;
    const key = (el === document.body ? 'body' : path(el)) + '|' + el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
    for (const pseudo of ['', '::before', '::after']) {
      const cs = getComputedStyle(el, pseudo || null);
      if (pseudo && cs.content === 'none') continue;
      const props = {};
      for (let i = 0; i < cs.length; i++) { const p = cs[i]; props[p] = cs.getPropertyValue(p); }
      out[key + pseudo] = props;
    }
  }
  return out;
}
"""


def states():
    s = []
    for w in (1440, 1180, 1000, 768, 390):
        s.append((f'week-{w}', '/#week', w, None))
    for w in (1440, 390):
        s.append((f'map-{w}', '/#map', w, None))
        s.append((f'plan-{w}', '/#plan/toa-payoh', w, 'plan'))
        s.append((f'forecast-{w}', '/#forecast', w, None))
        s.append((f'platform-{w}', '/#platform', w, None))
        s.append((f'poster-{w}', '/#poster/bedok', w, None))
        s.append((f'detail-{w}', '/#map/bedok', w, None))
    s.append(('map3d-1440', '/#map/3d', 1440, 'map3d'))
    s.append(('plan3d-1440', '/#plan/toa-payoh', 1440, 'plan3d'))
    s.append(('styleguide-1440', '/?dev#styleguide', 1440, None))
    s.append(('chat-1440', '/#week', 1440, 'chat'))
    s.append(('chat-390', '/#week', 390, 'chat'))
    s.append(('assistant-1440', '/#map', 1440, 'assistant'))
    s.append(('palette-1440', '/#week', 1440, 'palette'))
    s.append(('tour-1440', '/#week', 1440, 'tour'))
    s.append(('methodology-1440', '/#forecast', 1440, 'methodology'))
    s.append(('plan-print-1440', '/#plan/toa-payoh', 1440, 'print'))
    s.append(('poster-print-1440', '/#poster/bedok', 1440, 'print'))
    s.append(('help-768', '/#week', 768, 'help'))
    return s


async def act(page, action):
    if action in ('plan', 'plan3d', 'print'):
        await page.wait_for_selector('.stop-list .inspection-stop, .poster-sheet', timeout=30000)
    if action == 'plan3d':
        await page.click('[data-map-mode="3d"]')
        await page.wait_for_function("() => window.RouteFlythrough?.snapshot()?.ready === true", timeout=40000)
    if action == 'map3d':
        await page.wait_for_selector('.map-3d-host.is-ready', timeout=40000)
    if action == 'chat':
        await page.fill('#ask-input', 'Which areas are high priority this week?')
        await page.keyboard.press('Enter')
        await page.wait_for_selector('#home-conversation .chat-turn, #home-conversation .chat-message, .has-conversation', timeout=30000)
        await page.wait_for_timeout(2500)
    if action == 'assistant':
        await page.click('#ask-fab')
        await page.wait_for_timeout(600)
    if action == 'palette':
        await page.keyboard.press('Meta+k')
        await page.wait_for_timeout(500)
    if action == 'tour':
        await page.evaluate("document.querySelector('#tour-replay')?.click()")
        await page.wait_for_timeout(600)
    if action == 'methodology':
        await page.evaluate("document.querySelector('#methodology-dialog')?.showModal()")
        await page.wait_for_timeout(400)
    if action == 'help':
        await page.evaluate("document.querySelector('.help-menu')?.setAttribute('open', '')")
        await page.wait_for_timeout(400)
    if action == 'print':
        await page.emulate_media(media='print')
        await page.wait_for_timeout(400)


OLD_FILES = ["styles", "fieldwork", "flythrough", "checklist3d", "assistant", "experience", "tokens", "product", "chat-home",
             "stunning", "showcase", "polish", "insights", "map3d"]


async def old_css(page, base):
    """Serve the page with the 14 original stylesheets in place of app.css (for a baseline on today's data)."""
    async def rewrite(route):
        response = await route.fetch()
        html = await response.text()
        html = html.replace('<link rel="stylesheet" href="/app.css">', ''.join(f'<link rel="stylesheet" href="/{f}.css">' for f in OLD_FILES))
        html = html.replace('<style>@layer tokens, base, components, product, theme, views, overrides;@layer base{', '<style>').replace('}</style>', '</style>', 1)
        await route.fulfill(response=response, body=html, headers={**response.headers, 'content-type': 'text/html; charset=utf-8'})
    await page.route(base + '/', rewrite)


async def main(base, out, only=None, use_old_css=False):
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=GL)
        for name, url, width, action in states():
            if only and not any(o in name for o in only):
                continue
            context = await browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='reduce', device_scale_factor=1)
            await context.add_init_script("localStorage.setItem('denguesux:toured','true')")
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            if use_old_css:
                await old_css(page, base)
            try:
                await page.goto(base + url, wait_until='networkidle')
                await page.wait_for_function("() => window.Product?.ready === true", timeout=30000)
                await page.wait_for_timeout(900)
                if action:
                    await act(page, action)
                await page.wait_for_timeout(500)
                data = await page.evaluate(DUMP)
                with gzip.open(out / f'{name}.json.gz', 'wt') as handle:
                    json.dump(data, handle)
                await page.screenshot(path=str(out / f'{name}.png'), full_page=action not in ('plan3d', 'map3d'))
                report[name] = {'elements': len(data), 'errors': errors}
            except Exception as exc:
                report[name] = {'error': f'{type(exc).__name__}: {str(exc)[:160]}', 'errors': errors}
            await context.close()
            print(name, report[name].get('elements', report[name].get('error')), flush=True)
        await browser.close()
    (out / 'report.json').write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base', nargs='?', default='http://127.0.0.1:8787')
    parser.add_argument('--out', required=True)
    parser.add_argument('--only', nargs='*', help='Only states whose name contains one of these')
    parser.add_argument('--old-css', action='store_true', help='Load the 14 original stylesheets instead of app.css')
    args = parser.parse_args()
    asyncio.run(main(args.base, Path(args.out), args.only, args.old_css))
