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
    # Embedded snapshots need no server-side preload or install manifest. Bundle brand
    # images/icons as well as CSS so a file:// copy cannot silently lose its identity.
    html=re.sub(r'\s*<link rel="(?:preload|manifest)"[^>]*>', '', html)
    def inline_asset(match):
        asset=WEB/match.group(2).lstrip('/')
        mime=mimetypes.guess_type(asset)[0] or 'application/octet-stream'
        encoded=base64.b64encode(asset.read_bytes()).decode()
        return match.group(1)+'data:'+mime+';base64,'+encoded+'"'
    html=re.sub(r'<link rel="stylesheet" href="([^"]+)">',lambda m:'<style>'+inline_css(WEB/m.group(1).lstrip('/'))+'</style>',html)
    html=re.sub(r'<script src="([^"]+)"[^>]*></script>',lambda m:'<script>'+(WEB/m.group(1).lstrip('/')).read_text().replace('</script','<\\/script')+'</script>',html)
    html=re.sub(r'((?:src|href)=")(/brand/[^\"]+)"',inline_asset,html)
    # The 3D view loads lazily in the hosted app; the portable export carries its pinned assets.
    gl=WEB/'vendor/maplibre/maplibre-gl.js'
    if gl.exists():
        html=html.replace('<head>','<head><style>'+inline_css(gl.with_suffix('.css'))+'</style><script>'+gl.read_text().replace('</script','<\\/script')+'</script>',1)
    payload=json.loads((ROOT/'output/web/dashboard.json').read_text())
    for name in ('inspection', 'growth', 'notices', 'alerts', 'footprints', 'population'):
        path=ROOT/'output/web'/f'{name}.json'
        if path.exists(): payload[name]=json.loads(path.read_text())
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    html=html.replace('<head>','<head><script>window.DENGUESUX_DATA = '+data+';</script>',1)
    target=ROOT/'output/denguesux.html';target.write_text(html)
    print(f'{target} ({target.stat().st_size:,} bytes)')
    return target

if __name__=='__main__':build()
