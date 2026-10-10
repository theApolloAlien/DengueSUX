"""Focused chat/privacy regression with public example locations and recorded flows."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/verification/chat';BASE='http://127.0.0.1:8791'
DATA=json.loads((ROOT/'output/web/dashboard.json').read_text())
BLOCK=next(b for a in DATA['inspection']['areas'].values() for b in a.get('cluster_blocks',[]) if b.get('postal'))
INIT="""localStorage.setItem('denguesux:toured','true');window.testMetrics={cls:0};new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)testMetrics.cls+=e.value})).observe({type:'layout-shift',buffered:true});"""
async def ready(page,url=BASE+'/#week'):
 await page.goto(url,wait_until='domcontentloaded');await page.wait_for_selector('body.is-ready',timeout=30000)
async def shoot(page,name):await page.screenshot(path=str(OUT/(name+'.png')),full_page=True,animations='disabled')
async def main():
 OUT.mkdir(parents=True,exist_ok=True);checks={};errors=[];console=[]
 def check(name,value):
  checks[name]=bool(value)
  if not value:raise AssertionError(name)
 async with async_playwright() as p:
  browser=await p.chromium.launch()
  for width in (1440,1024,390):
   ctx=await browser.new_context(viewport={'width':width,'height':900 if width>400 else 844},reduced_motion='reduce',record_video_dir=str(OUT/'videos'),record_video_size={'width':width,'height':900 if width>400 else 844})
   await ctx.add_init_script(INIT);page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
   await ready(page);await page.locator('.home-neighbourhood').wait_for();await shoot(page,f'landing-{width}')
   check(f'landing_no_overflow_{width}',await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
   check(f'outlook_has_no_decoration_{width}',await page.locator('.week-outlook img').count()==0)
   check(f'one_composer_{width}',await page.locator('#ask-input').count()==1)
   # A real public example postal lookup goes to OneMap directly. Server fallback is blocked.
   await page.route('**/api/locate**',lambda r:r.abort())
   if width==1440:
    await page.fill('#ask-input',BLOCK['postal']);await page.press('#ask-input','Enter')
    try:await page.wait_for_selector('.location-card',timeout=18000);checks['real_onemap_browser_lookup']=True
    except Exception:
     checks['real_onemap_browser_lookup']=False;checks['onemap_failure_copy']=await page.locator('.chat-answer-body').last.inner_text()
     await page.get_by_role('button',name='New chat',exact=True).click();await page.get_by_role('button',name='Try an example',exact=True).click()
   else:await page.get_by_role('button',name='Try an example',exact=True).click()
   await page.wait_for_selector('.location-card');await shoot(page,f'location-{width}')
   check(f'conversation_no_overflow_{width}',await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
   await page.get_by_role('button',name='Remember this place',exact=True).click()
   check(f'remembered_{width}',await page.get_by_role('button',name='Remembered on this device',exact=True).count()==1)
   await page.get_by_role('button',name='Report breeding',exact=True).click();await page.wait_for_selector('#care-dialog[open]');check(f'report_handoff_{width}',await page.locator('#care-dialog input[type=file]').count()==0 and 'myENV' in await page.locator('#care-dialog').inner_text());await page.locator('#care-dialog button[aria-label=Close]').click()
   await page.fill('#ask-input','Plan a route here');await page.press('#ask-input','Enter');await page.wait_for_selector('.card-plan',timeout=10000)
   check(f'local_followup_plan_{width}',await page.locator('.card-plan').count()==1)
   await page.locator('.card-plan a').click();await page.wait_for_selector('#inspection-view:not([hidden]) .stop-list');await shoot(page,f'plan-{width}')
   await page.locator('#ask-fab').click();check(f'shared_thread_{width}',await page.locator('#ask-panel .location-card').count()==1 and await page.locator('#ask-panel .card-plan').count()==1)
   await page.locator('#close-chat').click();await page.goto(BASE+'/#week');await page.get_by_role('button',name='New chat',exact=True).click()
   check(f'saved_place_greeting_{width}',await page.locator('#saved-places [data-recheck]').count()==1)
   await page.locator('#saved-places').get_by_role('button',name='Forget all',exact=True).click();check(f'forget_all_{width}',await page.locator('#saved-places [data-recheck]').count()==0)
   await page.get_by_role('button',name='I have a fever, what now?',exact=True).click();await page.wait_for_selector('.feeling-unwell');check(f'fixed_seven_warning_signs_{width}',await page.locator('.feeling-unwell li').count()==7);await shoot(page,f'care-{width}')
   await page.get_by_role('button',name='New chat',exact=True).click();await page.select_option('#chat-language','zh');await page.get_by_role('button',name='写一份中文居民通知',exact=True).click();await page.wait_for_selector('.card-notice');check(f'chinese_notice_{width}',await page.locator('.notice-draft').get_attribute('lang')=='zh')
   await page.get_by_role('button',name='新对话',exact=True).click();await page.select_option('#chat-language','en');await page.goto(BASE+'/#map');await page.locator('.aedes-toggle input').check();check(f'aedes_toggle_{width}',await page.locator('.aedes-toggle input').is_checked());await shoot(page,f'aedes-{width}')
   await ctx.close()
  # Privacy request-body interception and fallback. Test-only public location fixture.
  ctx=await browser.new_context(viewport={'width':1440,'height':900},reduced_motion='reduce');await ctx.add_init_script(INIT);page=await ctx.new_page();wire=[];page.on('pageerror',lambda e:errors.append(str(e)))
  async def mock(route):
   url=route.request.url
   if 'onemap.gov.sg/api/common/elastic/search' in url:
    await route.fulfill(json={'results':[{'POSTAL':BLOCK['postal'],'LATITUDE':str(BLOCK['latitude']),'LONGITUDE':str(BLOCK['longitude']),'BLK_NO':BLOCK['block'],'ROAD_NAME':BLOCK['street']}]})
   elif '/api/chat/status' in url:await route.fulfill(json={'enabled':True})
   elif '/api/chat' in url:
    wire.append({'url':url,'body':route.request.post_data_json})
    if url.endswith('/stream'):await route.fulfill(status=503,json={})
    else:await route.fulfill(json={'answer':'Test fixture response','cards':[],'sources':[]})
   elif '/api/locate' in url:await route.abort()
   else:await route.continue_()
  await page.route('**/*',mock);await ready(page);await page.fill('#ask-input','邮编'+BLOCK['postal']+'附近');await page.press('#ask-input','Enter');await page.wait_for_selector('.location-card');check('postal_never_calls_chat',len(wire)==0)
  await page.fill('#ask-input','What is the outlook?');await page.press('#ask-input','Enter');await page.wait_for_function("document.querySelector('.chat-answer-body:last-child')&&document.body.innerText.includes('Test fixture response')")
  raw=json.dumps(wire);check('postal_and_coordinates_absent_from_request_bodies',all(str(v) not in raw for v in (BLOCK['postal'],BLOCK['latitude'],BLOCK['longitude'])))
  check('stream_failure_uses_nonstreaming',len(wire)==2 and wire[-1]['url'].endswith('/api/chat'))
  stored=await page.evaluate("sessionStorage.getItem('denguesux:conversation')");check('session_transcript_contains_no_location',all(str(v) not in stored for v in (BLOCK['postal'],BLOCK['latitude'],BLOCK['longitude'])))
  await page.fill('#ask-input','I have a fever');await page.press('#ask-input','Enter');await page.wait_for_selector('.feeling-unwell');check('medical_bypasses_model',len(wire)==2)
  await page.fill('#ask-input','1.312312, 103.812323');await page.press('#ask-input','Enter');check('coordinates_bypass_model',len(wire)==2)
  await ctx.close()
  # Throttled load and real motion, first ten seconds recorded.
  ctx=await browser.new_context(viewport={'width':1440,'height':900},record_video_dir=str(OUT/'videos'));await ctx.add_init_script(INIT);page=await ctx.new_page();cdp=await ctx.new_cdp_session(page)
  await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':90000});await cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
  await page.goto(BASE+'/#week',wait_until='domcontentloaded');await page.wait_for_selector('body.loading-visible',timeout=10000);await shoot(page,'loading-throttled');await page.wait_for_selector('body.is-ready',timeout=45000);await shoot(page,'loaded-throttled');check('throttled_ready',await page.locator('#ask-input').is_visible());checks['throttled_cls']=await page.evaluate('testMetrics.cls');await ctx.close()
  # Real offline portable export, no network, cards and medical guidance.
  ctx=await browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce');await ctx.add_init_script(INIT);await ctx.route('https://**/*',lambda r:r.abort());await ctx.route('http://**/*',lambda r:r.abort());page=await ctx.new_page();await ready(page,'file://'+str(ROOT/'output/denguesux.html'));await page.get_by_role('button',name='Try an example',exact=True).click();await page.wait_for_selector('.location-card');await page.fill('#ask-input','I have a fever');await page.press('#ask-input','Enter');await page.wait_for_selector('.feeling-unwell');check('portable_cards_work_offline',True);await shoot(page,'portable-offline');await ctx.close()
  await browser.close()
 check('no_uncaught_browser_errors',not errors)
 (OUT/'results.json').write_text(json.dumps({'checks':checks,'errors':errors,'console_errors':console},indent=2));print(json.dumps({'checks':checks,'errors':errors,'console_errors':console},indent=2))
if __name__=='__main__':asyncio.run(main())
