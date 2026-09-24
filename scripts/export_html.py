"""Bundle the working app, local assets and real data into a single portable HTML."""
import base64
import json
import mimetypes
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'app/web'

def inline_css(path):
    text=path.read_text()
    def url(match):
        value=match.group(1).strip('\"\' ')
        if value.startswith(('data:','http:','https:','#')): return match.group(0)
        asset=(WEB/value.lstrip('/')) if value.startswith('/') else (path.parent/value.split('?')[0].split('#')[0]).resolve()
        if not asset.exists(): raise FileNotFoundError(f'Unresolved bundled asset: {value} from {path}')
        mime=mimetypes.guess_type(asset)[0] or 'application/octet-stream'
        return 'url(data:'+mime+';base64,'+base64.b64encode(asset.read_bytes()).decode()+')'
    return re.sub(r'url\(([^)]+)\)',url,text)

def build():
    html=(WEB/'index.html').read_text()
    html=re.sub(r'<link rel="stylesheet" href="([^"]+)">',lambda m:'<style>'+inline_css(WEB/m.group(1).lstrip('/'))+'</style>',html)
    html=re.sub(r'<script src="([^"]+)"[^>]*></script>',lambda m:'<script>'+(WEB/m.group(1).lstrip('/')).read_text().replace('</script','<\\/script')+'</script>',html)
    payload=json.loads((ROOT/'output/web/dashboard.json').read_text())
    for name in ('inspection', 'growth', 'notices'):
        path=ROOT/'output/web'/f'{name}.json'
        if path.exists(): payload[name]=json.loads(path.read_text())
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    html=html.replace('<head>','<head><script>window.DENGUESUX_DATA = '+data+';</script>',1)
    target=ROOT/'output/denguesux.html';target.write_text(html)
    print(f'{target} ({target.stat().st_size:,} bytes)')
    return target

if __name__=='__main__':build()
