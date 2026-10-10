"""Targeted edge contracts for the product shell; entirely local browser contexts."""
import asyncio,json,subprocess
from pathlib import Path
from playwright.async_api import async_playwright
BASE='http://127.0.0.1:8787'
OUT=Path('output/design/saas')
async def main():
 checks={};errors=[]
 async with async_playwright() as p:
  b=await p.chromium.launch()
  ctx=await b.new_context(viewport={'width':1440,'height':900},reduced_motion='reduce');await ctx.add_init_script("localStorage.setItem('denguesux:toured','true')");page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
  await page.goto(BASE+'/#map/jurong-west');await page.wait_for_selector('body.is-ready');checks['shared-area-preserved']='Jurong West' in await page.locator('#area-detail').inner_text()
  await page.locator('#area-search').fill('no-such-area');checks['empty-search']=await page.locator('#area-list .empty-list').is_visible();await page.locator('[data-reset-search]').click();checks['empty-reset']=await page.locator('#area-list [data-area]').count()==55
  await page.goto(BASE+'/#forecast');await page.locator('.forecast-history>summary').click();await page.locator('[data-mode=replay]').first.click();await page.locator('#forecast-week').press('End');checks['replay-slider']=await page.locator('#forecast-week').input_value()=='51';await page.locator('#replay-button').click();await page.locator('[data-section=week]').click();await page.goto(BASE+'/#forecast');checks['replay-pauses']=await page.locator('#replay-button').get_attribute('aria-pressed')=='false'
  await page.goto(BASE+'/#plan/bishan');await page.wait_for_selector('.print-route',state='attached');checks['print-all-stops']=await page.locator('.print-route circle').count()==await page.locator('.stop-list>li').count()
  await page.locator('#plan-area').click();await page.locator('#command-search').fill('plan a check in bukit batok');await page.keyboard.press('Enter');await page.wait_for_url('**/#plan/bukit-batok');checks['plan-picker']=True
  await page.pdf(path=str(OUT/'field-sheet-bukit-batok.pdf'),print_background=True,prefer_css_page_size=True)
  await page.goto(BASE+'/#plan/unknown-area');checks['invalid-area']=await page.locator('#route-error').is_visible()
  await page.goto(BASE+'/#map/%ZZ');checks['malformed-link-safe']=await page.locator('#route-error').is_visible()
  await page.goto(BASE+'/#week');await page.keyboard.press('Control+k');await page.locator('#command-search').fill('Ask: current outlook');await page.keyboard.press('ArrowUp');await page.keyboard.press('Enter');checks['ask-prefill']='current outlook' in await page.locator('#ask-input').input_value()
  await page.locator('.help-menu>summary').click();await page.locator('#shortcuts-open').click();checks['shortcuts']=await page.locator('#shortcuts-dialog').is_visible();await page.keyboard.press('Escape');checks['dialog-escape']=not await page.locator('#shortcuts-dialog').is_visible()
  await page.locator('#sidebar-collapse').click();checks['sidebar-collapse']=await page.locator('body.sidebar-collapsed').count()==1;await page.locator('#sidebar-collapse').click()
  # Postal network capabilities withheld exactly as on Databricks.
  await page.route('**/api/locate/status',lambda r:r.fulfill(content_type='application/json',body='{"postal":false}'));await page.reload();await page.wait_for_selector('body.is-ready');checks['hosted-postal-hidden']=not await page.locator('#check-postal-form').is_visible();await page.unroute('**/api/locate/status')
  # A missing forecast never becomes zero and never gets a current-outlook claim.
  data=json.loads(Path('output/web/dashboard.json').read_text());data['model']['current_forecast']={'available':False};await page.route('**/data/dashboard.json',lambda r:r.fulfill(content_type='application/json',body=json.dumps(data)));await page.reload();await page.wait_for_selector('body.is-ready');checks['missing-forecast']='unavailable' in (await page.locator('.week-outlook').inner_text()).lower();await page.unroute('**/data/dashboard.json')
  await ctx.close()
  # Blocked storage is non-fatal. A first-time deep link must not be hijacked by the tour.
  ctx=await b.new_context();await ctx.add_init_script("Storage.prototype.getItem=()=>{throw Error('blocked')};Storage.prototype.setItem=()=>{throw Error('blocked')}");page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(BASE+'/#plan/jurong-west');await page.wait_for_selector('body.is-ready');checks['storage-denied']=await page.locator('#inspection-view').is_visible();checks['first-time-deep-link']=await page.locator('#tour-dialog').count()==0;await ctx.close()
  # Export under file://, with external network blocked. Local embedded data stays useful.
  ctx=await b.new_context(viewport={'width':390,'height':844},reduced_motion='reduce');await ctx.add_init_script("try{localStorage.setItem('denguesux:toured','true')}catch{}");page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  await page.route('http**://**/*',lambda r:r.abort());await page.goto(Path('output/denguesux.html').resolve().as_uri()+'#week');await page.wait_for_selector('body.is-ready');checks['portable-ready']=await page.locator('.week-outlook').is_visible();checks['portable-logo']=await page.locator('.brand-mark img').evaluate('(n)=>n.complete&&n.naturalWidth>0');await page.locator('[data-section=map]').click();await page.wait_for_selector('#signals-view:not([hidden])');checks['portable-map']=await page.locator('#signals-view').is_visible();await page.locator('#toggle-areas').click();await page.locator('#area-search').fill('nothing-matches');checks['portable-empty-art']=await page.locator('#area-list .spot').evaluate('(n)=>n.complete&&n.naturalWidth>0');await page.locator('#close-areas').click();await page.screenshot(path=str(OUT/'portable-390.png'),full_page=True);await ctx.close()
  # Final rendered overview and print sheet after the print-map repair.
  ctx=await b.new_context(viewport={'width':1440,'height':900},reduced_motion='reduce');await ctx.add_init_script("localStorage.setItem('denguesux:toured','true')");page=await ctx.new_page();await page.goto(BASE+'/#plan/jurong-west');await page.wait_for_selector('body.is-ready');await page.pdf(path=str(OUT/'field-sheet.pdf'),print_background=True,prefer_css_page_size=True)
  for width in (1440,1024,390):
   await page.set_viewport_size({'width':width,'height':900 if width>400 else 844})
   for route in ('week','map','plan/jurong-west','forecast'):
    await page.goto(BASE+'/#'+route);await page.screenshot(path=str(OUT/f'after-{route.split("/")[0]}-{width}.png'),full_page=True,animations='disabled')
  await ctx.close();await b.close()
 result={'checks':checks,'console_and_page_errors':errors};(OUT/'edge-checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));assert all(checks.values()) and not errors
asyncio.run(main())
