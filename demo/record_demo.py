#!/usr/bin/env python3
"""Record the live, unmodified DengueSUX UI.

Setup: python3 -m venv demo/.venv
       demo/.venv/bin/pip install playwright
       demo/.venv/bin/python -m playwright install chromium
Run:   demo/.venv/bin/python demo/record_demo.py
Probe: demo/.venv/bin/python demo/record_demo.py --rehearsal

All page changes are temporary presentation overlays. Real UI controls drive
every app interaction. FFmpeg removes only the prewarming lead-in, and encodes
the Playwright video as 1440x900 H.264 at 30 fps. No app files are written.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo"
URL = "http://127.0.0.1:8787"

OVERLAYS = r"""() => {
  const style = document.createElement('style');
  style.textContent = `
    #demo-overlay-root { position:fixed; inset:0; margin:0; padding:0; border:0;
      width:100vw; height:100vh; max-width:none; max-height:none; overflow:visible;
      background:transparent; pointer-events:none; z-index:99999; }
    #demo-overlay-root::backdrop { background:transparent; pointer-events:none; }
    #demo-caption { position:fixed; left:50%; bottom:28px; transform:translateX(-50%);
      width:max-content; max-width:70%; padding:12px 20px; border-radius:10px;
      background:rgba(22,63,53,.92); color:#fff; font:400 22px/1.4 'DM Sans',system-ui,sans-serif;
      text-align:center; pointer-events:none; z-index:99999; opacity:0;
      transition:opacity 250ms ease; box-shadow:0 5px 22px #0002; }
    #demo-caption[data-position=top] { top:24px; bottom:auto; }
    #demo-caption strong { display:block; font-weight:700; white-space:nowrap; }
    #demo-caption span { display:block; font-weight:400; opacity:.86; white-space:nowrap; }
    #demo-cursor { position:fixed; left:0; top:0; width:25px; height:31px;
      z-index:100002; pointer-events:none; filter:drop-shadow(0 2px 2px #0005); }
    #demo-ring { position:fixed; outline:2px solid #d65239; outline-offset:4px;
      border-radius:7px; pointer-events:none; z-index:100001;
      animation:demo-pulse 300ms ease-in-out; }
    @keyframes demo-pulse { 0%,100% { transform:scale(1); } 50% { transform:scale(1.045); } }
    #demo-preroll { position:fixed; inset:0; background:#163f35; z-index:100004; }
    #demo-sync { position:fixed; left:0; top:0; width:16px; height:16px;
      background:#ff00ff; z-index:100005; pointer-events:none; }
    #demo-end { position:fixed; inset:0; display:flex; flex-direction:column;
      align-items:center; justify-content:center; gap:22px; background:#163f35;
      color:white; z-index:100003; pointer-events:none; font-family:'DM Sans',system-ui,sans-serif;
      opacity:0; transition:opacity 250ms ease; }
    #demo-end strong { font-size:45px; letter-spacing:-1px; font-weight:700; }
    #demo-end span { font-size:24px; color:#d8e4dc; font-weight:400; }
  `;
  document.head.append(style);
  const root=document.createElement('div');root.id='demo-overlay-root';
  root.setAttribute('popover','manual');document.body.append(root);root.showPopover();
  const cap = document.createElement('div'); cap.id='demo-caption';
  cap.innerHTML='<strong></strong><span></span>';
  const cursor = document.createElement('div'); cursor.id='demo-cursor';
  cursor.innerHTML='<svg viewBox="0 0 25 31"><path d="M3 2 L3 25 L9 19 L14 29 L19 26 L14 17 L23 17 Z" fill="#163f35" stroke="white" stroke-width="2" stroke-linejoin="round"/></svg>';
  cursor.style.transform='translate(800px, 200px)';
  root.append(cap,cursor);
  let lastDialog=null;
  const portal = () => {
    const dialog=document.querySelector('dialog[open]');
    if(dialog!==lastDialog) {
      lastDialog=dialog; root.hidePopover();root.showPopover();
    }
  };
  new MutationObserver(portal).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open']});
  document.addEventListener('mousemove',e=>{
    cursor.style.transform=`translate(${e.clientX}px,${e.clientY}px)`;
  },true);
  window.demoCaption = (title,subtitle,position,duration) => {
    clearTimeout(window.demoCaptionTimer);
    portal(); cap.querySelector('strong').textContent=title;
    cap.querySelector('span').textContent=subtitle;
    cap.dataset.position=position; cap.style.opacity='1';
    window.demoCaptionTimer=setTimeout(()=>cap.style.opacity='0',duration);
  };
  window.demoAvoid = rect => {
    if(cap.style.opacity!=='1') return;
    const c=cap.getBoundingClientRect();
    if(c.left<rect.x+rect.width+12 && c.right>rect.x-12 &&
       c.top<rect.y+rect.height+12 && c.bottom>rect.y-12) {
      cap.dataset.position=c.top>innerHeight/2?'top':'bottom';
    }
  };
  const pre=document.createElement('div'); pre.id='demo-preroll';
  const sync=document.createElement('div'); sync.id='demo-sync';
  document.body.append(pre,sync);
}"""


def app_hashes():
    files = list((ROOT / "app").rglob("*")) + [ROOT / "app.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files if p.is_file() and "__pycache__" not in p.parts}


def ensure_server():
    try:
        with urllib.request.urlopen(URL, timeout=3) as response:
            if response.status == 200:
                return
    except OSError:
        pass
    log = (OUT / "server.log").open("w")
    subprocess.Popen([str(ROOT / ".venv/bin/uvicorn"), "app:app", "--port", "8787"],
                     cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(100):
        try:
            with urllib.request.urlopen(URL, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(.2)
    raise RuntimeError("App did not start; see demo/server.log")


class Demo:
    def __init__(self, page, rehearsal=False):
        self.page = page
        self.rehearsal = rehearsal
        self.scenes = []
        self.captions = []
        self.shots = OUT / ("rehearsal_frames" if rehearsal else "frames")
        self.shots.mkdir(exist_ok=True)

    async def hold(self, seconds):
        await self.page.wait_for_timeout(seconds * (150 if self.rehearsal else 1000))

    async def now(self):
        return await self.page.evaluate("performance.now() / 1000")

    async def scene(self, number, title):
        self.scene_started = await self.now()
        self.scenes.append({"scene": number, "title": title, "page_time": self.scene_started})
        print(f"Scene {number}: {title}", flush=True)

    async def finish(self, minimum):
        elapsed = await self.now() - self.scene_started
        target = minimum * (.15 if self.rehearsal else 1)
        if elapsed < target:
            await self.page.wait_for_timeout((target - elapsed) * 1000)

    async def caption(self, title, subtitle, position="bottom"):
        stamp = await self.now()
        self.captions.append({"title": title, "subtitle": subtitle, "page_time": stamp, "duration": 4.8})
        await self.page.evaluate("a=>window.demoCaption(...a)", [title, subtitle, position, 4550])
        await self.page.wait_for_timeout(300)
        await self.shot(f"{self.scenes[-1]['scene']:02d}-caption-{len(self.captions):02d}")

    async def shot(self, name):
        await self.page.screenshot(path=str(self.shots / f"{name}.png"))

    async def click(self, target):
        loc = self.page.locator(target) if isinstance(target, str) else target
        await loc.wait_for(state="visible")
        await loc.scroll_into_view_if_needed()
        await self.page.wait_for_timeout(180)
        box = await loc.bounding_box()
        assert box, f"No click bounds for {target}"
        await self.page.evaluate("r=>window.demoAvoid(r)", box)
        await self.page.mouse.move(box["x"] + box["width"] / 2,
                                   box["y"] + box["height"] / 2, steps=30)
        await self.page.evaluate("""r=>{
          document.getElementById('demo-ring')?.remove();
          const ring=document.createElement('div');ring.id='demo-ring';
          Object.assign(ring.style,{left:r.x+'px',top:r.y+'px',width:r.width+'px',height:r.height+'px'});
          document.getElementById('demo-overlay-root').append(ring);
        }""", box)
        await self.page.wait_for_timeout(350)
        await self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await self.page.wait_for_timeout(150)
        await self.page.evaluate("document.getElementById('demo-ring')?.remove()")
        await self.page.wait_for_timeout(320)

    async def scroll(self, target_y, duration=1800):
        await self.page.evaluate("""({y,duration})=>new Promise(resolve=>{
          const start=scrollY, at=performance.now();
          const step=now=>{
            const t=Math.min(1,(now-at)/duration),ease=t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;
            window.scrollTo({top:start+(y-start)*ease,behavior:'instant'});
            if(t<1)requestAnimationFrame(step);else resolve();
          };requestAnimationFrame(step);
        })""", {"y": target_y, "duration": duration})
        await self.page.wait_for_timeout(300)

    async def ask(self, question):
        await self.click("#ask-input")
        count = await self.page.locator(".ask-bot").count()
        await self.page.locator("#ask-input").press_sequentially(question, delay=48)
        await self.page.wait_for_timeout(450)
        await self.page.locator("#ask-input").press("Enter")
        await self.page.wait_for_function("n=>document.querySelectorAll('.ask-bot').length>n", arg=count)
        await self.page.wait_for_selector(".ask-send:not([disabled])")
        await self.page.locator(".ask-bot").last.locator(".ask-body").wait_for()
        await self.page.wait_for_timeout(650)

    async def notice_ready(self):
        await self.page.wait_for_selector("#notice-text:not(.is-writing)")
        await self.page.wait_for_timeout(500)

    async def run(self):
        p = self.page
        await p.goto(URL, wait_until="networkidle")
        await p.wait_for_selector('body.is-ready')
        await p.wait_for_selector('#main[aria-busy="false"]')
        await p.wait_for_selector('#ask-fab')
        await p.evaluate("document.fonts.ready")
        await p.evaluate(OVERLAYS)
        # Warm the fully loaded map for a real two seconds before scene one.
        await p.wait_for_timeout(2000)
        self.start = await p.evaluate("""()=>{
          document.getElementById('demo-preroll').remove();
          document.getElementById('demo-sync').remove();
          return performance.now()/1000;
        }""")

        await self.scene(1, "Area signals and Singapore map")
        await self.caption("DengueSUX — where to check for mosquitoes this week",
                           "Built on Singapore's open NEA, MOH and URA data")
        await self.hold(4.8)
        await self.scroll(140, 1000)
        await self.finish(8)

        await self.scene(2, "Largest cluster first")
        await self.click("#briefing-view")
        await p.wait_for_selector("#area-detail .plan-button")
        await self.caption("Largest cluster first", "74 people across Jurong West and Jurong East")
        await self.finish(7)

        await self.scene(3, "High and Active priority filters")
        await self.click('.filter[data-filter="High"]')
        await p.wait_for_selector('.filter[data-filter="High"][aria-pressed="true"]')
        await self.caption("Areas ranked by people in active clusters", "High = 10 or more people")
        await self.hold(3.5)
        await self.click('.filter[data-filter="active"]')
        await p.wait_for_selector('.filter[data-filter="active"][aria-pressed="true"]')
        await self.finish(8)

        await self.scene(4, "Walking inspection plan and Done checklist")
        await self.click(".plan-button")
        await p.wait_for_selector(".stop-done input")
        await p.wait_for_function("document.querySelectorAll('#inspection-map img.leaflet-tile-loaded').length > 0")
        await self.caption("One-click inspection plan", "8 stops on a 1.2 km OneMap walking route")
        await self.hold(4.4)
        last_y = await p.locator(".inspection-stop").last.evaluate("e=>e.getBoundingClientRect().bottom+scrollY-innerHeight+90")
        await self.scroll(last_y, 4000)
        await self.hold(1)
        await self.click(p.locator(".stop-done input").last)
        assert await p.locator(".stop-done input").last.is_checked()
        await self.shot("04-done")
        await self.hold(1.5)
        await self.scroll(0, 1900)
        await self.finish(16)

        await self.scene(5, "Resident notice, rewrite, safety checks and Chinese")
        await self.click("#plan-notice")
        await p.wait_for_selector("#notice-dialog[open]")
        await self.caption("Resident notice, drafted from dated facts",
                           "Every draft passes 5 automatic safety checks", "top")
        await self.notice_ready()
        await self.hold(4)
        await self.click("#rewrite-notice")
        await self.notice_ready()
        await self.hold(1.4)
        await self.click("#notice-checks summary")
        await p.wait_for_selector("#notice-checks[open]")
        await self.shot("05-checks")
        await self.hold(2.5)
        await self.click('[data-language="zh"]')
        await self.notice_ready()
        await self.shot("05-chinese")
        await self.hold(3)
        await self.click("#close-notice")
        await p.wait_for_selector("#notice-dialog", state="hidden")
        await self.click("#back-to-areas")
        await self.scroll(0, 900)
        await self.finish(22)

        await self.scene(6, "Ask DengueSUX: Jurong East and function calls")
        await self.click("#ask-fab")
        await p.wait_for_selector("#ask-panel:not([hidden])")
        await self.caption("Ask DengueSUX",
                           "Answers come from the data, and every number cites a dated source")
        await self.ask("Why is Jurong East High?")
        await self.hold(2.8)
        await self.click(p.locator(".ask-trace summary").last)
        await self.page.locator(".ask-trace[open]").last.scroll_into_view_if_needed()
        await self.page.wait_for_timeout(400)
        await self.shot("06-function-calls")
        await self.finish(15)

        await self.scene(7, "March early warning and the forecast chart")
        await self.click(p.locator(".ask-trace[open] summary").last)
        await self.ask("What drove the March 2022 early warning?")
        await self.caption("Explains the forecast", "Recent cases drove the warning, 11 weeks before the peak")
        await self.hold(4.5)
        await self.click(p.get_by_role("button", name="Show this week on the chart", exact=True))
        await p.wait_for_selector("#forecast-view:not([hidden])")
        await self.hold(2)
        await self.shot("07-chart")
        await self.finish(14)

        await self.scene(8, "Ask the data: monthly forecast error and SQL")
        if not await p.locator("#ask-panel").is_visible():
            await self.click("#ask-fab")
        await self.click('.ask-modes [data-mode="sql"]')
        await self.click(p.get_by_role("button", name="Monthly forecast error in 2022", exact=True))
        await p.wait_for_selector(".ask-sql summary")
        await p.wait_for_selector(".ask-send:not([disabled])")
        await p.wait_for_timeout(500)
        await self.caption("Ask the data", "Plain English → SQL over the gold Delta tables")
        await self.hold(3)
        await self.click(".ask-sql summary")
        await p.wait_for_selector(".ask-sql[open]")
        await p.locator(".ask-sql pre").scroll_into_view_if_needed()
        await p.wait_for_timeout(500)
        await self.shot("08-sql")
        await self.hold(3)
        await self.click(".ask-close")
        await self.finish(13)

        await self.scene(9, "Forecast replay and next area growth model")
        await self.click('.rail-button[data-view="forecast"]')
        await self.scroll(0, 1000)
        await self.click("#replay-button")
        await p.wait_for_selector('#replay-button[aria-pressed="true"]')
        await self.caption("Tested on a real outbreak",
                           "Error ~83 people a week, vs ~172 for a simple average")
        await p.wait_for_timeout(8000)
        growth_y = await p.locator("#growth-model").evaluate("e=>e.getBoundingClientRect().top+scrollY-innerHeight/2+e.offsetHeight/2")
        await self.scroll(growth_y, 1400)
        await p.locator("#growth-model").wait_for(state="visible")
        await self.caption("Next: an area-level growth model", "Collecting daily snapshots now", "top")
        await self.hold(4.8)
        await self.finish(17)

        await self.scene(10, "DengueSUX end card")
        await p.evaluate("""()=>{
          document.getElementById('demo-caption').style.opacity='0';
          document.getElementById('demo-cursor').style.display='none';
          const end=document.createElement('div');end.id='demo-end';
          end.innerHTML='<strong>DengueSUX · Small actions. Fewer bites.</strong><span>DAISI Challenge Singapore</span>';
          document.body.append(end);requestAnimationFrame(()=>requestAnimationFrame(()=>end.style.opacity='1'));
        }""")
        await p.wait_for_timeout(350)
        await self.shot("10-end")
        await p.wait_for_timeout(4000)
        self.end = await self.now()


def timestamp(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def convert(video, demo):
    # The 16px magenta pre-roll marker lets us find the first warm frame in the
    # actual recorded timeline, rather than guessing when Chromium began video.
    pixels = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(video), "-t", "45", "-vf",
        "fps=30,crop=8:8:4:4,scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"
    ])
    marker_seen = False
    trim = None
    for frame, offset in enumerate(range(0, len(pixels), 3)):
        r, g, b = pixels[offset:offset+3]
        marker = r > 210 and g < 65 and b > 210
        if marker:
            marker_seen = True
        elif marker_seen:
            trim = frame / 30
            break
    if trim is None:
        raise RuntimeError("Could not locate the prewarm boundary in the recording")
    duration = demo.end - demo.start
    dest = OUT / ("rehearsal.mp4" if demo.rehearsal else "denguesux_demo.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-v", "warning", "-i", str(video), "-ss", str(trim),
        "-t", str(duration), "-an", "-vf", "fps=30", "-c:v", "libx264",
        "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(dest)
    ], check=True)
    info = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_name,width,height,r_frame_rate,pix_fmt", "-of", "json", str(dest)
    ]))
    scenes = [{"scene": s["scene"], "title": s["title"],
               "seconds": round(s["page_time"] - demo.start, 3),
               "timestamp": timestamp(s["page_time"] - demo.start)} for s in demo.scenes]
    captions = [{**c, "seconds": round(c["page_time"] - demo.start, 3)} for c in demo.captions]
    report = {"video": str(dest), "duration_seconds": float(info["format"]["duration"]),
              "prewarm_trim_seconds": trim, "encoding": info["streams"],
              "scenes": scenes, "captions": captions, "app_files_unchanged": True}
    prefix = "rehearsal" if demo.rehearsal else "denguesux_demo"
    (OUT / f"{prefix}_timestamps.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (OUT / f"{prefix}_scenes.md").write_text("# DengueSUX demo scene timestamps\n\n" +
        f"Duration: {report['duration_seconds']:.2f} seconds · 1440×900 · H.264 · 30 fps\n\n" +
        "\n".join(f"- {s['timestamp'].replace(',', '.')} — {s['scene']}. {s['title']}" for s in scenes) + "\n")
    entries = []
    for i, c in enumerate(captions, 1):
        entries.append(f"{i}\n{timestamp(c['seconds'])} --> {timestamp(c['seconds']+c['duration'])}\n{c['title']}\n{c['subtitle']}\n")
    end_start = scenes[-1]["seconds"]
    entries.append(f"{len(entries)+1}\n{timestamp(end_start)} --> {timestamp(duration)}\nDengueSUX · Small actions. Fewer bites.\nDAISI Challenge Singapore\n")
    (OUT / f"{prefix}.srt").write_text("\n".join(entries))
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rehearsal", action="store_true", help="Shorten reading pauses; keep the same real interactions")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    before = app_hashes()
    ensure_server()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900},
            record_video_dir=str(OUT / ("rehearsal_raw" if args.rehearsal else "raw")),
            record_video_size={"width": 1440, "height": 900}, device_scale_factor=1,
            locale="en-SG", timezone_id="Asia/Singapore", reduced_motion="no-preference")
        page = await context.new_page()
        page.set_default_timeout(20000)
        demo = Demo(page, args.rehearsal)
        try:
            await demo.run()
        except Exception:
            await page.screenshot(path=str(OUT / "failure.png"))
            raise
        finally:
            video = await page.video.path()
            await context.close()
            await browser.close()
        assert before == app_hashes(), "App files changed during capture"
        convert(video, demo)


if __name__ == "__main__":
    asyncio.run(main())
