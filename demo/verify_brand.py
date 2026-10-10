import asyncio,json
from playwright.async_api import async_playwright
async def main():
 out=[]
 async with async_playwright() as p:
  b=await p.chromium.launch()
  for width in (1440,1280,1024,390):
   ctx=await b.new_context(viewport={'width':width,'height':900 if width>400 else 844},reduced_motion='reduce');await ctx.add_init_script("localStorage.setItem('denguesux:toured','true')");page=await ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto('http://127.0.0.1:8787/#week');await page.wait_for_selector('body.is-ready')
   for route in ('week','map','plan','plan/jurong-west','forecast'):
    await page.goto('http://127.0.0.1:8787/#'+route);await page.wait_for_function('(s)=>document.title.startsWith(s)',arg={'week':'This week','map':'Map','plan':'Field plan','plan/jurong-west':'Field plan','forecast':'Forecast'}[route]);await page.screenshot(path='output/design/saas/branded-'+route.replace('/','-')+'-'+str(width)+'.png',full_page=True,animations='disabled');out.append({'width':width,'route':route,'overflow':await page.evaluate('document.documentElement.scrollWidth>innerWidth'),'broken_images':await page.evaluate('[...document.images].filter(n=>n.getClientRects().length&&n.src.includes("/brand/")&&!n.naturalWidth).map(n=>n.src)'),'errors':errors[:]})
   await page.locator('.help-menu>summary').click();await page.locator('.help-menu [data-about]').click();await page.screenshot(path=f'output/design/saas/branded-story-{width}.png',full_page=True);await ctx.close()
  await b.close()
 open('output/design/saas/brand-verification.json','w').write(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
asyncio.run(main())
