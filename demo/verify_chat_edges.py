"""Final state, keyboard, cancellation and source-mock captures."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/verification/chat';BASE='http://127.0.0.1:8791'
async def main():
 checks={};errors=[]
 async with async_playwright() as p:
  b=await p.chromium.launch();ctx=await b.new_context(viewport={'width':1440,'height':900},reduced_motion='reduce');await ctx.add_init_script("localStorage.setItem('denguesux:toured','true')");page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto(BASE+'/#week');await page.wait_for_selector('body.is-ready');await page.screenshot(path=str(OUT/'final-home-1440.png'),full_page=True)
  examples=json.loads((ROOT/'output/design/saas/location-status-examples.json').read_text())
  for status,point in examples.items():
   await page.evaluate('p=>{ChatHome.clear();LocationCheck.show(p)}',point);checks['real_status_'+status]=await page.locator('.location-card.status-'+status).count()==1;await page.locator('.location-card').screenshot(path=str(OUT/('status-'+status+'.png')))
  await page.get_by_role('button',name='New chat',exact=True).click();await page.fill('#ask-input','Which areas should we check first?');await page.press('#ask-input','Enter');await page.wait_for_selector('.card-top_areas');await page.reload();await page.wait_for_selector('.card-top_areas');checks['session_restores_thread']=await page.locator('.card-top_areas').count()==1
  await page.fill('#ask-input','');await page.press('#ask-input','ArrowUp');# Editing applies to the current visit; session restore keeps the thread.
  await page.get_by_role('button',name='New chat',exact=True).click();await page.fill('#ask-input','What is expected next week?');await page.press('#ask-input','Enter');await page.wait_for_selector('.card-forecast');await page.press('#ask-input','ArrowUp');checks['up_edits_last']=await page.input_value('#ask-input')=='What is expected next week?';await page.fill('#ask-input','line one');await page.press('#ask-input','Shift+Enter');checks['shift_enter_newline']='\n' in await page.input_value('#ask-input')
  await page.goto(BASE+'/?notice=zh#plan/jurong-west');await page.wait_for_selector('#notice-text');checks['brief_notice_deep_link']=await page.locator('#notice-text').get_attribute('lang')=='zh';await page.locator('#close-notice').click()
  await page.goto(BASE+'/#week');await page.get_by_role('button',name='New chat',exact=True).click();await page.route('**/api/chat/status',lambda r:r.fulfill(json={'enabled':True}))
  gate=asyncio.Event()
  async def wait_stream(route):
   await gate.wait()
   try:await route.fulfill(status=503,json={})
   except Exception:pass
  await page.route('**/api/chat/stream',wait_stream);await page.fill('#ask-input','Check the forecast');await page.press('#ask-input','Enter');await page.wait_for_selector('#chat-stop:not([hidden])');await page.press('#ask-input','Escape');await page.wait_for_function("document.body.innerText.includes('Stopped. You can ask again')");checks['escape_stops_pending_stream']=True;gate.set();await ctx.close()
  # Browser renders frozen design target, both states, in both requested viewports.
  for width in (1440,390):
   ctx=await b.new_context(viewport={'width':width,'height':900 if width>400 else 844},reduced_motion='reduce');await ctx.add_init_script("localStorage.setItem('denguesux:toured','true')");page=await ctx.new_page();await page.goto('file://'+str(ROOT/'output/design/saas/mock-this-week-chat.html'));await page.wait_for_selector('body.is-ready');await page.screenshot(path=str(OUT/f'mock-landing-{width}.png'),full_page=True);await page.locator('[data-state=Conversation]').click();await page.wait_for_selector('.card-top_areas');await page.screenshot(path=str(OUT/f'mock-conversation-{width}.png'),full_page=True);await ctx.close()
  await b.close()
 checks['no_uncaught_errors']=not errors
 (OUT/'edge-results.json').write_text(json.dumps({'checks':checks,'errors':errors},indent=2));print(json.dumps({'checks':checks,'errors':errors},indent=2));assert all(checks.values())
if __name__=='__main__':asyncio.run(main())
