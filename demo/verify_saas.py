"""Reproducible local browser evidence; never submits reports or personal locations."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
OUT=Path('output/design/saas')
BASE='http://127.0.0.1:8787'
INIT="""localStorage.setItem('denguesux:toured','true');window.metrics={cls:0,lcp:0,events:[]};new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)metrics.cls+=e.value})).observe({type:'layout-shift',buffered:true});new PerformanceObserver(l=>metrics.lcp=l.getEntries().at(-1).startTime).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(l=>l.getEntries().forEach(e=>metrics.events.push(e.duration))).observe({type:'event',buffered:true,durationThreshold:16});"""
async def ready(page,url=BASE+'/#week'):
 await page.goto(url,wait_until='domcontentloaded');await page.wait_for_selector('body.is-ready',timeout=35000)
async def stats(page):
 return await page.evaluate("({words:document.body.innerText.trim().split(/\\s+/).length,overflow:document.documentElement.scrollWidth>innerWidth,cls:metrics.cls,lcp:metrics.lcp,fcp:performance.getEntriesByName('first-contentful-paint')[0]?.startTime,interaction_proxy:Math.max(0,...metrics.events)})")
async def screenshot(page,name):
 await page.screenshot(path=str(OUT/(name+'.png')),full_page=True,animations='disabled')
async def main():
 OUT.mkdir(exist_ok=True,parents=True);checks={};screens={};errors=[]
 async with async_playwright() as p:
  b=await p.chromium.launch(args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
  for width in (1440,1280,1024,390):
   ctx=await b.new_context(viewport={'width':width,'height':900 if width>400 else 844},reduced_motion='reduce');await ctx.add_init_script(INIT);page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   await ready(page)
   for route in ('week','map','plan/jurong-west','forecast','styleguide'):
    await page.goto(BASE+'/#'+route);await page.wait_for_function('(s)=>document.title.startsWith(s)',arg={'week':'This week','map':'Map','plan/jurong-west':'Field plan','forecast':'Forecast','styleguide':'Design system'}[route]);await screenshot(page,'after-'+route.split('/')[0]+'-'+str(width));screens[f'{route}-{width}']=await stats(page)
   await page.goto(BASE+'/#map');await page.locator('[data-map-view=table]').click();await page.fill('#table-search','Bishan');checks[f'table-filter-{width}']=await page.locator('#area-table-body tr').count()==1;await page.locator('[data-sort=name]').click();checks[f'table-sort-{width}']=await page.locator('[data-sort=name]').locator('..').get_attribute('aria-sort')=='ascending';await screenshot(page,f'after-table-{width}')
   await page.keyboard.press('Control+k');await page.fill('#command-search','jrngwst');checks[f'fuzzy-{width}']=await page.locator('#command-results').inner_text();await page.keyboard.press('Enter');await page.wait_for_url('**/#map/jurong-west');checks[f'palette-route-{width}']=True
   await page.keyboard.press('g');await page.keyboard.press('f');await page.wait_for_url('**/#forecast');await page.go_back();await page.wait_for_url('**/#map/jurong-west');checks[f'back-forward-{width}']=True
   await page.goto(BASE+'/#plan/jurong-west');await page.locator('.stop-list input').first.check();checks[f'checklist-{width}']='1 of 8' in await page.locator('#stop-progress-label').inner_text()
   await page.locator('#copy-plan-link').click();await page.wait_for_selector('#share-dialog[open],#toast:not([hidden])');checks[f'share-{width}']=await page.locator('#toast').is_visible() or await page.locator('#share-dialog').is_visible()
   if await page.locator('#share-dialog').is_visible():
    await page.locator('[data-close=share-dialog]').click();await page.wait_for_selector('#share-dialog',state='hidden')
   await page.locator('#plan-notice').click();await page.wait_for_selector('#copy-notice:not([disabled])')
   for lang in ('en','zh','ms','ta'):
    await page.locator(f'[data-language={lang}]').click();await page.wait_for_selector('#notice-text');checks[f'notice-{lang}-{width}']=await page.locator('#copy-notice').is_enabled()
   await screenshot(page,f'after-notice-{width}');await page.locator('#close-notice').click()
   if width==1440:
    await page.pdf(path=str(OUT/'field-sheet.pdf'),print_background=True,prefer_css_page_size=True)
    await page.locator('[data-map-mode="3d"]').click();await page.wait_for_selector('#route-3d:not([hidden])');await page.wait_for_function("/official HDB|unavailable/.test(document.querySelector('.route-3d-status')?.textContent||'')",timeout=20000);await screenshot(page,'after-3d-1440')
   await page.goto(BASE+'/#week');await page.locator('#check-example').click();checks[f'resident-{width}']=await page.locator('#check-result').is_visible();await screenshot(page,f'after-resident-{width}')
   await page.locator('#ask-fab').click();await page.fill('#ask-input','Which areas should we check first?');await page.locator('.ask-send').click();await page.wait_for_selector('.ask-body',timeout=60000);checks[f'ask-{width}']=bool(await page.locator('.ask-body').last.inner_text());await screenshot(page,f'after-ask-{width}');await page.locator('.ask-close').click()
   await ctx.close()
  # First-run tour and replay, without the usual test opt-out.
  ctx=await b.new_context();page=await ctx.new_page();await ready(page);await page.wait_for_selector('#tour-dialog[open]');checks['first-run-tour']=True
  for i in range(3):await page.locator('#tour-next').click()
  checks['tour-opens-ask']=await page.locator('#ask-panel').is_visible();await page.locator('.ask-close').click();await page.reload();await page.wait_for_selector('body.is-ready');checks['tour-once']=not await page.locator('#tour-dialog').count();await ready(page,BASE+'/?tour=1');checks['forced-tour']=await page.locator('#tour-dialog').is_visible();await ctx.close()
  # Failures and loading on each job route.
  for route in ('week','map','plan/jurong-west','forecast'):
   ctx=await b.new_context(viewport={'width':1440,'height':900});await ctx.add_init_script(INIT);page=await ctx.new_page();gate=asyncio.Event()
   async def hold(r):await gate.wait();await r.continue_()
   await page.route('**/data/dashboard.json',hold);await page.goto(BASE+'/#'+route,wait_until='domcontentloaded');await page.wait_for_selector('body.loading-visible');await screenshot(page,'loading-'+route.split('/')[0]);gate.set();await page.wait_for_selector('body.is-ready');await ctx.close()
   ctx=await b.new_context(viewport={'width':1440,'height':900});await ctx.add_init_script(INIT);page=await ctx.new_page();await page.route('**/data/dashboard.json',lambda r:r.fulfill(status=503,body='unavailable'));await page.goto(BASE+'/#'+route);await page.wait_for_selector('body.is-error');checks['error-'+route]=await page.locator('#error-state button').is_visible();await screenshot(page,'error-'+route.split('/')[0]);await ctx.close()
  ctx=await b.new_context();await ctx.add_init_script(INIT);page=await ctx.new_page();await ready(page);await ctx.set_offline(True);checks['offline']=await page.locator('#offline-banner').is_visible();await screenshot(page,'offline');await ctx.set_offline(False);await ctx.close()
  # Comparable cold-load synthetic metrics, with measured event latency.
  metrics={}
  for label,base in [('before','http://127.0.0.1:8788'),('after',BASE)]:
   for width in (1440,390):
    ctx=await b.new_context(viewport={'width':width,'height':900 if width>400 else 844});await ctx.add_init_script(INIT);page=await ctx.new_page();cdp=await ctx.new_cdp_session(page)
    await cdp.send('Network.enable');await cdp.send('Network.setCacheDisabled',{'cacheDisabled':True});await cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':93750,'connectionType':'cellular4g'});await cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
    await ready(page,base+'/#'+('signals' if label=='before' else 'week'));await page.wait_for_timeout(800);metrics[f'{label}-{width}']=await stats(page)
    await page.locator('#check-example').click();await page.wait_for_timeout(200);metrics[f'{label}-{width}']['interaction_proxy']=(await stats(page))['interaction_proxy'];await screenshot(page,f'slow4g-{label}-{width}');await ctx.close()
  # Record real flows, once with each motion preference. No external writes.
  for motion in ('no-preference','reduce'):
   for flow,width in [('judge',1440),('coordinator',1440),('resident',390)]:
    ctx=await b.new_context(viewport={'width':width,'height':900 if width>400 else 844},reduced_motion=motion,permissions=['clipboard-read','clipboard-write'],record_video_dir=str(OUT/'videos'),record_video_size={'width':width,'height':900 if width>400 else 844});await ctx.add_init_script(INIT);page=await ctx.new_page();await ready(page)
    if flow=='judge':
     await page.wait_for_timeout(3000);await page.locator('[data-section=forecast]').click();await page.wait_for_timeout(3000);await page.locator('[data-section=week]').click();await page.wait_for_timeout(3000)
    if flow=='coordinator':
     await page.locator('.priority-row a[title="Plan a check"]').first.click();await page.locator('.stop-list input').first.check();await page.locator('#plan-notice').click();await page.wait_for_selector('#copy-notice:not([disabled])');await page.locator('#copy-notice').click();assert 'Draft: review before sending' in await page.evaluate('navigator.clipboard.readText()');await page.wait_for_timeout(1200)
    if flow=='resident':
     await page.locator('#check-example').click();await page.locator('#check-result').scroll_into_view_if_needed();await page.wait_for_timeout(1800)
    video=page.video;await ctx.close();await video.save_as(str(OUT/'videos'/f'{flow}-{motion}.webm'))
  await b.close()
 result={'checks':checks,'screens':screens,'metrics_slow4g_cpu4':metrics,'page_errors':errors};(OUT/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps({'checks':len(checks),'failed':[k for k,v in checks.items() if not v],'page_errors':errors,'metrics':metrics},indent=2))
if __name__=='__main__':asyncio.run(main())
