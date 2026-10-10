"""Freeze a reviewable real-data mock and its assets, without another app stack."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
web=ROOT/'app/web'
s=(web/'index.html').read_text()
s=re.sub(r'<link rel="stylesheet" href="([^"]+)">',lambda m:'<style>'+(web/m.group(1).lstrip('/')).read_text()+'</style>',s)
s=re.sub(r'<script src="([^"]+)"[^>]*></script>',lambda m:'<script>'+(web/m.group(1).lstrip('/')).read_text().replace('</script','<\\/script')+'</script>',s)
s=s.replace('<head>','<head><base href="http://127.0.0.1:8791/"><script>window.DENGUESUX_DATA='+json.dumps(json.loads((ROOT/'output/web/dashboard.json').read_text())).replace('<','\\u003c')+';window.DENGUESUX_CARE='+json.dumps(json.loads((web/'care-copy.json').read_text())).replace('<','\\u003c')+';</script>',1)
s=s.replace('<body>', '<body>')
examples=json.loads((ROOT/'output/design/saas/location-status-examples.json').read_text())
controls="""<script>
const statusExamples=EXAMPLES;
const mockTimer=setInterval(()=>{if(!window.Product?.ready)return;clearInterval(mockTimer);const toolbar=document.createElement('nav');toolbar.className='design-review-controls';toolbar.style='display:flex;flex-wrap:wrap;gap:8px;padding:12px;background:#edf1ea;border:1px solid #b9c6b8;border-radius:8px;margin:20px 0';toolbar.setAttribute('aria-label','Design review states');toolbar.innerHTML='<strong>Design review · public map examples</strong> '+['Landing','Conversation','red','amber','purple','green'].map(s=>'<button class="outline-button" data-state="'+s+'">'+s+'</button>').join('');document.querySelector('#main').append(toolbar);toolbar.querySelectorAll('button').forEach(b=>b.onclick=()=>{window.ChatHome.clear();location.hash='#week';if(b.dataset.state==='Conversation')window.ChatHome.ask('Which areas should we check first?');else if(statusExamples[b.dataset.state])window.LocationCheck.show(statusExamples[b.dataset.state]);});},100);
</script>""".replace('EXAMPLES',json.dumps(examples))
s=s.replace('</body>',controls+'</body>')
path=ROOT/'output/design/saas/mock-this-week-chat.html';path.write_text(s)
print(path)
