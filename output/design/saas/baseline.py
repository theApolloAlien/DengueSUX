import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
OUT=Path('output/design/saas')
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch()
  result={}
  for width in (1440,1024,390):
   ctx=await browser.new_context(viewport={'width':width,'height':900 if width>400 else 844})
   page=await ctx.new_page()
   await page.add_init_script("window.metrics={cls:0,lcp:0};new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)metrics.cls+=e.value})).observe({type:'layout-shift',buffered:true});new PerformanceObserver(l=>metrics.lcp=l.getEntries().at(-1).startTime).observe({type:'largest-contentful-paint',buffered:true})")
   await page.goto('http://127.0.0.1:8788')
   await page.wait_for_selector('body.is-ready')
   for name in ('signals','forecast','plan','notice','resident','ask'):
    if name=='forecast': await page.locator('.view-tab[data-view=forecast]').click()
    if name=='plan':
     await page.locator('.view-tab[data-view=signals]').click()
     await page.locator('#area-detail .plan-button').click()
    if name=='notice': await page.locator('#plan-notice').click();await page.wait_for_selector('.notice-text')
    if name=='resident':
     await page.locator('#close-notice').click();await page.locator('#back-to-areas').click();await page.locator('#check-example').click()
    if name=='ask': await page.locator('#ask-fab').click()
    await page.screenshot(path=str(OUT/f'before-{name}-{width}.png'),full_page=True,animations="disabled")
    result[f'{name}-{width}']=await page.evaluate("({words:document.body.innerText.trim().split(/\\s+/).length,overflow:document.documentElement.scrollWidth>innerWidth,...metrics,fcp:performance.getEntriesByName('first-contentful-paint')[0]?.startTime})")
   await ctx.close()
  ctx=await browser.new_context(viewport={'width':1440,'height':900})
  page=await ctx.new_page();cdp=await ctx.new_cdp_session(page)
  await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':93750,'connectionType':'cellular4g'})
  await page.goto('http://127.0.0.1:8788',wait_until='domcontentloaded');await page.screenshot(path=str(OUT/'before-loading.png'))
  await page.wait_for_selector('body.is-ready');result['fast4g']=await page.evaluate("performance.getEntriesByType('resource').filter(x=>x.name.includes('dashboard')).map(x=>({name:x.name,duration:x.duration,bytes:x.transferSize}))")
  await browser.close();(OUT/'before-metrics.json').write_text(json.dumps(result,indent=2))
asyncio.run(main())
