"""Local prototype server. Forecast computation remains in portable notebook stages."""
from pathlib import Path
import json
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT=Path(__file__).resolve().parent
app=FastAPI(title='DengueSUX',docs_url=None,redoc_url=None)

@app.get('/api/health')
def health():
    return {'status':'ready' if (ROOT/'output/web/dashboard.json').exists() else 'awaiting_pipeline','synthetic_data':False}

@app.get('/data/{name}')
def data(name:str):
    allowed={'dashboard.json','current.json','model.json','inspection.json','growth.json','notices.json'}
    if name not in allowed: raise HTTPException(404)
    p=ROOT/'output/web'/name
    if not p.exists(): raise HTTPException(503,'Run the pipeline to prepare real data.')
    return FileResponse(p,media_type='application/json')

@app.get('/api/notices/{area_code}')
def resident_notice(area_code: str, language: Literal['en','zh','ms','ta']='en'):
    from denguesux.notices import generate_notice
    try:
        return generate_notice(area_code, language, root=ROOT)
    except ValueError:
        raise HTTPException(404,'Unknown planning area or unavailable source facts.') from None
    except (OSError, KeyError, json.JSONDecodeError):
        raise HTTPException(503,'Build the dated gold facts before generating a notice.') from None

@app.get('/reports/{name}')
def reports(name:str):
    if name not in {'DATA_REPORT.md','MODEL_REPORT.md'}: raise HTTPException(404)
    return FileResponse(ROOT/name,media_type='text/markdown',filename=name)

@app.get('/prototype.html')
def standalone():
    return FileResponse(ROOT/'output/denguesux.html',media_type='text/html')

app.mount('/',StaticFiles(directory=ROOT/'app/web',html=True),name='frontend')
