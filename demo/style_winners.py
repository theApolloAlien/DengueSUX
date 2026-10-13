"""For every unexpected difference in a demo/style_diff.py report, find the declaration that won under the OLD
stylesheets (specificity, then order, !important first) and write a hoist list the migration can replay.

usage: demo/.venv/bin/python demo/style_winners.py BASE_URL DIFF_JSON --out hoist.json
The page is loaded with the 14 original stylesheets swapped in for app.css, so the answer is "what used to win".
"""
import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

OLD_FILES = ["styles", "fieldwork", "flythrough", "checklist3d", "assistant", "experience", "tokens", "product", "chat-home",
             "stunning", "showcase", "polish", "insights", "map3d"]
GL = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
STATES = {}  # name -> (url, width, action), copied from style_snapshot
import importlib.util, sys
spec = importlib.util.spec_from_file_location("snap", Path(__file__).with_name("style_snapshot.py"))
snap = importlib.util.module_from_spec(spec); spec.loader.exec_module(snap)
for name, url, width, action in snap.states():
    STATES[name] = (url, width, action)

WINNER = """
([targets]) => {
  const specificity = sel => { let a=0,b=0,c=0; const s = sel.replace(/::?[a-z-]+(\\([^)]*\\))?/g, m => { if (m.startsWith('::')) { c++; } else if (!/^:(not|is|where|has)\\(/.test(m)) { b++; } return ''; });
    a += (s.match(/#[\\w-]+/g)||[]).length; b += (s.match(/\\.[\\w-]+|\\[[^\\]]+\\]/g)||[]).length; c += (s.match(/(^|[\\s>+~])[a-z][\\w-]*/gi)||[]).length; return a*10000+b*100+c; };
  const resolve = key => { const path = key.split('|')[0]; if (path === 'body') return document.body; let el = document.body;
    for (const part of path.split('>')) { const i = Number(part.split(':')[1]); el = el.children[i]; if (!el) return null; } return el; };
  const out = [];
  let order = 0;
  const rules = [];
  const visit = (list, media, file) => { for (const r of list) { if (r instanceof CSSStyleRule) rules.push({r, media, file, order: order++});
    else if (r instanceof CSSMediaRule) { if (matchMedia(r.conditionText).matches) visit(r.cssRules, (media ? media + ' and ' : '') + r.conditionText, file); }
    else if (r instanceof CSSSupportsRule || (window.CSSLayerBlockRule && r instanceof CSSLayerBlockRule) || (window.CSSContainerRule && r instanceof CSSContainerRule)) visit(r.cssRules, media, file); } };
  for (const sheet of document.styleSheets) { let file = (sheet.href || 'inline').split('/').pop(); try { visit(sheet.cssRules, '', file); } catch (e) {} }
  for (const [key, prop] of targets) {
    const pseudo = key.endsWith('::before') ? '::before' : key.endsWith('::after') ? '::after' : '';
    const el = resolve(pseudo ? key.slice(0, -pseudo.length) : key); if (!el) { out.push({key, prop, missing: true}); continue; }
    let best = null;
    // Longhands set through a shorthand that holds var() stay unexpanded in the CSSOM; look at the shorthand itself then.
    const SHORT = {'border-top-color':['border-color','border-top','border'],'border-right-color':['border-color','border-right','border'],'border-bottom-color':['border-color','border-bottom','border'],'border-left-color':['border-color','border-left','border'],
      'border-inline-start-color':['border-color','border'],'border-inline-end-color':['border-color','border'],'border-block-start-color':['border-color','border'],'border-block-end-color':['border-color','border'],
      'border-top-width':['border-width','border-top','border'],'border-bottom-width':['border-width','border-bottom','border'],'border-left-width':['border-width','border-left','border'],'border-right-width':['border-width','border-right','border'],
      'border-top-left-radius':['border-radius'],'border-top-right-radius':['border-radius'],'border-bottom-left-radius':['border-radius'],'border-bottom-right-radius':['border-radius'],'border-start-start-radius':['border-radius'],'border-start-end-radius':['border-radius'],'border-end-start-radius':['border-radius'],'border-end-end-radius':['border-radius'],
      'padding-top':['padding','padding-block'],'padding-bottom':['padding','padding-block'],'padding-left':['padding','padding-inline'],'padding-right':['padding','padding-inline'],'padding-inline-start':['padding','padding-inline'],'padding-inline-end':['padding','padding-inline'],'padding-block-start':['padding','padding-block'],'padding-block-end':['padding','padding-block'],
      'margin-top':['margin','margin-block'],'margin-bottom':['margin','margin-block'],'margin-left':['margin','margin-inline'],'margin-right':['margin','margin-inline'],'margin-inline-start':['margin','margin-inline'],'margin-inline-end':['margin','margin-inline'],'margin-block-start':['margin','margin-block'],'margin-block-end':['margin','margin-block'],
      'row-gap':['gap'],'column-gap':['gap'],'background-color':['background'],'background-image':['background'],'font-size':['font'],'font-weight':['font'],'font-family':['font'],'line-height':['font'],
      'top':['inset'],'left':['inset'],'right':['inset'],'bottom':['inset'],'flex-grow':['flex'],'flex-shrink':['flex'],'flex-basis':['flex'],'grid-template-columns':['grid','grid-template'],'grid-template-rows':['grid','grid-template'],
      'outline-color':['outline'],'outline-width':['outline'],'text-decoration-color':['text-decoration'],'animation-duration':['animation'],'transition-duration':['transition'],'overflow-x':['overflow'],'overflow-y':['overflow'],'inset-inline-start':['inset'],'inset-inline-end':['inset']};
    for (const {r, media, file, order} of rules) {
      let value = r.style.getPropertyValue(prop), used = prop;
      if (!value) { for (const sh of (SHORT[prop] || [])) { const v = r.style.getPropertyValue(sh); if (v) { value = v; used = sh; break; } } }
      if (!value) continue;
      const important = r.style.getPropertyPriority(used) === 'important';
      let matched = null;
      for (const part of r.selectorText.split(/,(?![^(]*\\))/)) { const sel = part.trim(); const base = sel.replace(/::?(before|after)$/, '');
        const wantsPseudo = /::?(before|after)$/.test(sel); if ((pseudo && !wantsPseudo) || (!pseudo && wantsPseudo)) continue;
        try { if (el.matches(base || '*')) { const sp = specificity(sel); if (!matched || sp > matched.sp) matched = {sel, sp}; } } catch (e) {} }
      if (!matched) continue;
      const cand = {selector: r.selectorText, matched: matched.sel, sp: matched.sp, important, order, value, media, file, used};
      if (!best || (cand.important && !best.important) || (cand.important === best.important && (cand.sp > best.sp || (cand.sp === best.sp && cand.order > best.order)))) best = cand;
    }
    out.push({key, prop, winner: best});
  }
  return out;
}
"""


async def main(base, diff, out, current=False):
    report = json.loads(Path(diff).read_text())
    hoists, seen = [], set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=GL)
        for name, item in report.items():
            targets = [(ex["element_key"], prop) for prop, exs in item.get("examples", {}).items() for ex in exs if "element_key" in ex]
            if not targets or name not in STATES:
                continue
            url, width, action = STATES[name]
            context = await browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='reduce')
            await context.add_init_script("localStorage.setItem('denguesux:toured','true')")
            await context.route('**/*', lambda route: route.continue_())
            page = await context.new_page()
            # Serve the old stylesheets: rewrite the document so app.css becomes the 14 original links.
            async def rewrite(route):
                response = await route.fetch()
                html = await response.text()
                links = ''.join(f'<link rel="stylesheet" href="/{f}.css">' for f in OLD_FILES)
                html = html.replace('<link rel="stylesheet" href="/app.css">', links)
                await route.fulfill(response=response, body=html, headers={**response.headers, 'content-type': 'text/html; charset=utf-8'})
            if not current:
                await page.route(base + '/', rewrite)
            await page.goto(base + url, wait_until='networkidle')
            await page.wait_for_function("() => window.Product?.ready === true", timeout=30000)
            await page.wait_for_timeout(900)
            if action:
                await snap.act(page, action)
            await page.wait_for_timeout(500)
            results = await page.evaluate(WINNER, [targets])
            for res in results:
                w = res.get("winner")
                if not w:
                    continue
                sig = (w["selector"], w["media"], w.get("used") or res["prop"], w["value"])
                if sig in seen:
                    continue
                seen.add(sig)
                hoists.append({"state": name, "element": res["key"].split("|", 1)[1][:80], "prop": w.get("used") or res["prop"], "value": w["value"], "order": w["order"],
                               "important": w["important"], "selector": w["selector"], "media": w["media"], "file": w["file"]})
            await context.close()
            print(name, len(results), "targets", flush=True)
        await browser.close()
    Path(out).write_text(json.dumps(hoists, indent=1))
    print("hoists", len(hoists))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('diff')
    parser.add_argument('--out', required=True)
    parser.add_argument('--current', action='store_true', help='Use the stylesheet the page links now (the after side)')
    args = parser.parse_args()
    asyncio.run(main(args.base, args.diff, args.out, args.current))
