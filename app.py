"""Local prototype server. Forecast computation remains in portable notebook stages."""
from pathlib import Path
import json
import os
from datetime import timedelta
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
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

class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)

def _genie_space():
    return os.environ.get('GENIE_SPACE_ID') or None

@app.get('/api/ask/status')
def ask_status():
    return {'enabled': bool(_genie_space()), 'engine': 'Databricks Genie'}

@app.post('/api/ask')
def ask_genie(body: AskBody):
    """Answer a plain-English question with the Databricks Genie space over the gold tables."""
    space = _genie_space()
    if not space:
        raise HTTPException(503, 'Genie is not configured for this deployment.')
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        reply = w.genie.start_conversation_and_wait(space_id=space, content=body.question.strip(), timeout=timedelta(seconds=120))
        out = {'answer': None, 'sql': None, 'description': None, 'columns': [], 'rows': [], 'truncated': False, 'source': 'Databricks Genie'}
        for att in reply.attachments or []:
            if att.text and att.text.content:
                out['answer'] = att.text.content
            if att.query:
                out['sql'] = att.query.query
                out['description'] = att.query.description
                result = w.genie.get_message_attachment_query_result(space_id=space, conversation_id=reply.conversation_id,
                                                                     message_id=reply.message_id, attachment_id=att.attachment_id)
                resp = result.statement_response
                if resp and resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
                    out['columns'] = [c.name for c in resp.manifest.schema.columns]
                rows = (resp.result.data_array if resp and resp.result and resp.result.data_array else [])
                out['truncated'] = len(rows) > 50
                out['rows'] = rows[:50]
        return out
    except HTTPException:
        raise
    except Exception as exc:  # The front end falls back to the saved-data answers.
        raise HTTPException(502, f'Genie could not answer: {type(exc).__name__}') from None

@app.get('/reports/{name}')
def reports(name:str):
    if name not in {'DATA_REPORT.md','MODEL_REPORT.md'}: raise HTTPException(404)
    return FileResponse(ROOT/name,media_type='text/markdown',filename=name)

@app.get('/prototype.html')
def standalone():
    return FileResponse(ROOT/'output/denguesux.html',media_type='text/html')

app.mount('/',StaticFiles(directory=ROOT/'app/web',html=True),name='frontend')
