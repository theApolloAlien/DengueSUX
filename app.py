"""Local prototype server. Forecast computation remains in portable notebook stages."""
from contextlib import asynccontextmanager
from pathlib import Path
import json
import os
from datetime import timedelta
from typing import Literal, Optional
from fastapi import Request, FastAPI, HTTPException, Path as PathParam, Query
from pydantic import BaseModel, Field, field_validator
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT=Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(_app):
    # The Telegram bot answers residents while the app runs; it starts only when a token is attached.
    from denguesux.telegram import start_polling
    start_polling(ROOT)
    yield

app=FastAPI(title='DengueSUX',docs_url=None,redoc_url=None,lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

@app.middleware('http')
async def cache_policy(request, call_next):
    """Pinned vendor files may be cached; app code, data and API answers are revalidated so a deploy or refresh shows at once."""
    response = await call_next(request)
    if 'cache-control' not in response.headers:
        path = request.url.path
        response.headers['Cache-Control'] = 'public, max-age=604800' if path.startswith('/vendor/') else 'no-store' if path.startswith('/api/') else 'no-cache'
    return response

def _refresh_snapshot():
    """User requests never wait for the Volume; a due refresh runs in the background."""
    from denguesux.app_snapshot import refresh_in_background
    return refresh_in_background(ROOT)

@app.get('/api/data/status')
def data_status():
    """Explicit status check: waits for a due refresh so operators see its real outcome."""
    from denguesux.app_snapshot import refresh_snapshot
    return refresh_snapshot(ROOT)

@app.get('/api/trace/status')
def trace_status():
    """Is assistant tracing configured, and does a probe span export? Reports error types only, never messages or secrets."""
    out = {'tracking_uri_set': bool(os.environ.get('MLFLOW_TRACKING_URI')), 'experiment_set': bool(os.environ.get('MLFLOW_EXPERIMENT_ID'))}
    try:
        import mlflow
        out['mlflow_version'] = getattr(mlflow, '__version__', None)
    except Exception as exc:
        out['import_error'] = type(exc).__name__
        out['missing_module'] = getattr(exc, 'name', None)  # a module name, never data
        return out
    try:
        with mlflow.start_span(name='trace_status_probe', span_type='CHAIN') as span:
            span.set_inputs({'probe': True})
        out['probe_trace_id'] = mlflow.get_last_active_trace_id()
        out['exported'] = bool(out['probe_trace_id'])
    except Exception as exc:
        out['probe_error'] = type(exc).__name__
    return out

@app.get('/api/telegram/status')
def telegram_status():
    """Whether the alert bot is configured and its public username; never chat ids or the token."""
    from denguesux.telegram import status
    return status()

@app.get('/api/health')
def health():
    return {'status':'ready' if (ROOT/'output/web/dashboard.json').exists() else 'awaiting_pipeline','synthetic_data':False}

@app.get('/data/{name}')
def data(name:str):
    from denguesux.app_snapshot import PUBLIC_FILES
    allowed=set(PUBLIC_FILES)
    if name not in allowed: raise HTTPException(404)
    _refresh_snapshot()
    p=(ROOT/'output/web'/name).resolve()  # pin one published generation for the whole response
    if not p.exists(): raise HTTPException(503,'Run the pipeline to prepare real data.')
    return FileResponse(p,media_type='application/json')

@app.get('/feeds/alerts.xml')
def alert_feed(request: Request, area: Optional[str] = Query(default=None, pattern=r'^[A-Z]{2,3}$')):
    """Atom feed of today's alerts and two-week outlook warnings, optionally for one area.

    Anyone can follow it in a feed reader or a chat bot without giving us an email address or phone number."""
    from xml.sax.saxutils import escape
    _refresh_snapshot()
    def load(name):
        try: return json.loads((ROOT/'output/web'/name).read_text())
        except (OSError, json.JSONDecodeError): return {}
    alerts, outlook = load('alerts.json'), load('area_forecast.json')
    base = str(request.base_url).rstrip('/')
    entries = []
    for item in alerts.get('alerts', []):
        if area and area not in (item.get('area_codes') or []): continue
        code = area or (item.get('area_codes') or [''])[0]
        entries.append((f"alert:{alerts.get('snapshot_date')}:{item.get('kind')}:{code}", item.get('title',''), item.get('message',''),
                        f"{base}/#plan/{code}" if code else f"{base}/#week", alerts.get('generated_at')))
    for row in outlook.get('areas', []):
        if area and row.get('code') != area: continue
        if row.get('band') == 'High' and row.get('band_now') != 'High':
            entries.append((f"outlook:{outlook.get('as_of')}:{row['code']}", f"{row['name']} may reach High within about two weeks",
                            f"Chance of 10 or more people in dengue clusters: {round(100*row.get('p_high',0))}%. A check-first outlook, not a case forecast.",
                            f"{base}/#map", outlook.get('generated_at')))
    updated = alerts.get('generated_at') or outlook.get('generated_at') or '1970-01-01T00:00:00+00:00'
    title = 'DengueSUX alerts' + (f' · {area}' if area else '')
    body = [f'<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">',
            f'<title>{escape(title)}</title>', f'<id>{escape(base)}/feeds/alerts.xml{("?area="+area) if area else ""}</id>',
            f'<updated>{escape(updated)}</updated>', f'<link href="{escape(base)}/"/>',
            '<subtitle>Places to check, not confirmed breeding sites. Generated from NEA open data.</subtitle>']
    for entry_id, entry_title, summary, link, stamp in entries:
        body += ['<entry>', f'<id>urn:denguesux:{escape(entry_id)}</id>', f'<title>{escape(entry_title)}</title>',
                 f'<updated>{escape(stamp or updated)}</updated>', f'<link href="{escape(link)}"/>', f'<summary>{escape(summary)}</summary>', '</entry>']
    body.append('</feed>')
    return Response('\n'.join(body), media_type='application/atom+xml')

@app.get('/data/walks/{area_code}.json')
def walk(area_code: str = PathParam(pattern=r'^[A-Z]{2,3}$')):
    """The saved 3D walk for one planning area: plan, official HDB footprints and parks/water context."""
    p=ROOT/'output/web/walks'/f'{area_code}.json'
    if not p.is_file(): raise HTTPException(404,'No saved walk for this area.')
    return FileResponse(p,media_type='application/json')

@app.get('/api/notices/{area_code}')
def resident_notice(area_code: str = PathParam(pattern=r'^[A-Z]{2,3}$'), language: Literal['en','zh','ms','ta']='en'):
    _refresh_snapshot()
    from denguesux.notices import generate_notice
    try:
        return generate_notice(area_code, language, root=ROOT)
    except (OSError, KeyError, json.JSONDecodeError):
        raise HTTPException(503,'Build the dated gold facts before generating a notice.') from None
    except ValueError:
        raise HTTPException(404,'Unknown planning area or unavailable source facts.') from None

class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    conversation_id: Optional[str] = Field(default=None, max_length=64)

def _genie_space():
    return os.environ.get('GENIE_SPACE_ID') or None

def _llm_endpoint():
    return os.environ.get('LLM_ENDPOINT') or None

def _genie_ask(question: str, conversation_id: Optional[str] = None):
    """One Genie turn over the gold tables. Pass conversation_id to continue a thread (follow-up questions)."""
    from databricks.sdk import WorkspaceClient
    space = _genie_space()
    w = WorkspaceClient()
    wait = timedelta(seconds=120)
    if conversation_id:
        reply = w.genie.create_message_and_wait(space_id=space, conversation_id=conversation_id, content=question.strip(), timeout=wait)
    else:
        reply = w.genie.start_conversation_and_wait(space_id=space, content=question.strip(), timeout=wait)
    out = {'answer': None, 'sql': None, 'description': None, 'columns': [], 'rows': [], 'truncated': False, 'source': 'Databricks Genie', 'conversation_id': reply.conversation_id}
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

@app.get('/api/ask/status')
def ask_status():
    return {'enabled': bool(_genie_space()), 'engine': 'Databricks Genie'}

@app.post('/api/ask')
def ask_genie(body: AskBody):
    """Answer a plain-English question with the Databricks Genie space over the gold tables."""
    if not _genie_space():
        raise HTTPException(503, 'Genie is not configured for this deployment.')
    try:
        return _genie_ask(body.question, body.conversation_id)
    except Exception as exc:  # The front end falls back to the saved-data answers.
        raise HTTPException(502, f'Genie could not answer: {type(exc).__name__}') from None

class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(max_length=2000)

class ChatBody(BaseModel):
    language: Literal['en','zh','ms','ta'] = 'en'
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)

    @field_validator('messages')
    @classmethod
    def privacy_boundary(cls, messages):
        import re
        for message in messages:
            if re.search(r'(?<!\d)\d{6}(?!\d)|\b1\.\d+\s*[, /]\s*103\.\d+\b',message.content):
                raise ValueError('Use the browser-only location check for postal codes or coordinates.')
        return messages


@app.get('/api/chat/status')
def chat_status():
    return {'enabled': bool(_llm_endpoint()), 'model': _llm_endpoint(), 'database': bool(_genie_space())}

@app.post('/api/chat')
def chat(body: ChatBody):
    """Tool-calling assistant: a hosted model answers from the dated gold data and can ask Genie for SQL."""
    from denguesux.care import symptom_question, fixed_response
    last_user = next((m.content for m in reversed(body.messages) if m.role == 'user'), '')
    if symptom_question(last_user):
        return fixed_response(ROOT, last_user, body.language)
    endpoint = _llm_endpoint()
    if not endpoint:
        raise HTTPException(503, 'The assistant model is not configured for this deployment.')
    _refresh_snapshot()
    from denguesux.assistant import run_chat, make_llm, make_diagrammer
    try:
        llm = make_llm(endpoint)
        return run_chat([m.model_dump() for m in body.messages], llm, ROOT,
                        genie=(lambda q: _genie_ask(q)) if _genie_space() else None, language=body.language, diagram=make_diagrammer(llm))
    except (OSError, KeyError, json.JSONDecodeError):
        raise HTTPException(503, 'Build the dated gold facts before using the assistant.') from None
    except ValueError:
        raise HTTPException(422, 'The assistant could not use that conversation. Start a new question.') from None
    except Exception as exc:  # The front end falls back to the saved-data answers.
        raise HTTPException(502, f'The assistant could not answer: {type(exc).__name__}') from None

@app.post('/api/chat/stream')
async def chat_stream(body: ChatBody, request: Request):
    """Ephemeral SSE only: no transcript storage, real tool starts and serving deltas."""
    from denguesux.care import symptom_question, fixed_response
    last_user = next((m.content for m in reversed(body.messages) if m.role == 'user'), '')
    if symptom_question(last_user):
        result = fixed_response(ROOT, last_user, body.language)
        return StreamingResponse(iter(['data: '+json.dumps({'type':'done',**result},ensure_ascii=False)+'\n\n']),media_type='text/event-stream')
    endpoint = _llm_endpoint()
    if not endpoint:
        raise HTTPException(503, 'The assistant model is not configured for this deployment.')
    _refresh_snapshot()
    import asyncio
    import queue
    import threading
    from denguesux.assistant import run_chat, make_llm, make_stream_llm, make_diagrammer
    pending=queue.Queue(maxsize=64)
    stopped=threading.Event()
    def emit(event):
        while not stopped.is_set():
            try: pending.put(event,timeout=.5);return
            except queue.Full: pass
        raise InterruptedError('Client stopped')
    def work():
        try:
            llm=make_llm(endpoint)
            result=run_chat([m.model_dump() for m in body.messages],llm,ROOT,
                genie=(lambda q:_genie_ask(q)) if _genie_space() else None,
                on_event=emit,stream_llm=make_stream_llm(endpoint),language=body.language,diagram=make_diagrammer(llm))
            emit({'type':'done',**result})
        except InterruptedError: pass
        except Exception:
            try: emit({'type':'error','message':'Streaming unavailable; retrying the saved-data answer.'})
            except InterruptedError: pass
    async def events():
        threading.Thread(target=work,daemon=True).start()
        try:
            while not stopped.is_set():
                if await request.is_disconnected():break
                try:event=await asyncio.to_thread(pending.get,True,1)
                except queue.Empty:
                    yield ': keepalive\n\n';continue
                yield 'data: '+json.dumps(event,ensure_ascii=False,default=str)+'\n\n'
                if event['type'] in ('done','error'):break
        finally:stopped.set()
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

class FieldReportBody(BaseModel):
    area_code: str = Field(pattern=r'^[A-Z]{2,3}$')
    stop_id: str = Field(min_length=1, max_length=120)
    stop_name: str = Field(min_length=1, max_length=160)
    place_type: str = Field(default='place', max_length=40)
    outcome: Literal['water_found', 'cleared', 'nothing']
    note: Optional[str] = Field(default=None, max_length=280)
    plan_as_of: Optional[str] = Field(default=None, max_length=40)

def _planned_stop(area_code, stop_id):
    """Reports must refer to a stop in a saved public plan (the cluster plan or the area's walk), so counts cannot be inflated with invented stops."""
    plans = []
    for path, pick in ((ROOT/'output/web/inspection.json', lambda d: d.get('areas', {}).get(area_code)),
                       (ROOT/'output/web/walks'/f'{area_code}.json', lambda d: d.get('plan'))):
        try:
            plans.append(pick(json.loads(path.read_text())) or {})
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
    return next((stop for plan in plans for stop in plan.get('stops', []) if str(stop.get('id')) == stop_id), None)

def _reports():
    from denguesux.field_reports import store
    return store(ROOT)

@app.post('/api/reports')
def add_report(body: FieldReportBody, verify_only: bool = False):
    """Record an unverified finding at a planned stop; personal details are not requested."""
    from denguesux.field_reports import make_report
    if verify_only:
        try:
            _reports().verify()
        except Exception as exc:
            raise HTTPException(503, f'Report storage verification failed: {type(exc).__name__}') from None
        return {'saved': False, 'verified': True, 'observations_written': 0}
    stop = _planned_stop(body.area_code, body.stop_id)
    if stop is None:
        raise HTTPException(422, 'That stop is not in the current inspection plan for this area. Reload the plan and try again.')
    fields = {**body.model_dump(), 'stop_name': str(stop.get('name') or body.stop_name)[:160], 'place_type': str(stop.get('place_type') or body.place_type)[:40]}
    report = make_report(**fields, source='databricks_app' if os.environ.get('DATABRICKS_WAREHOUSE_ID') else 'local')
    try:
        _reports().add(report)
    except Exception as exc:
        raise HTTPException(503, f'Report could not be saved: {type(exc).__name__}') from None
    return {'saved': True, 'report_id': report['report_id'], 'reported_at': report['reported_at']}

@app.get('/api/reports')
def list_reports(area_code: Optional[str] = Query(default=None, pattern=r'^[A-Z]{2,3}$')):
    from denguesux.field_reports import summarise
    try:
        rows = _reports().recent(area_code)
    except Exception as exc:
        raise HTTPException(503, f'Reports are unavailable: {type(exc).__name__}') from None
    return summarise(rows)

def _onemap_client():
    from denguesux.onemap import OneMapClient
    return OneMapClient(ROOT)

_postal_probe = {'checked': 0.0, 'ok': False}

def _probe_postal():
    """Offer postal lookup only if OneMap actually answers from this server (cached; public cloud IPs can be refused)."""
    import time
    now = time.monotonic()
    if _postal_probe['checked'] and now - _postal_probe['checked'] < (900 if _postal_probe['ok'] else 300):
        return _postal_probe['ok']
    ok = False
    try:
        client = _onemap_client()
        if client.postal_lookup_available():
            plan = json.loads((ROOT/'output/web/inspection.json').read_text()).get('areas', {})
            probe = next((str(stop['postal']) for area in plan.values() for stop in area.get('stops', []) if stop.get('postal')), None)
            # A public HDB block from the saved plan; the answer itself is discarded.
            ok = bool(probe) and client.locate_postal(probe) is not None and not client.map_data_stale
    except Exception:
        ok = False
    _postal_probe.update(checked=now, ok=ok)
    return ok

@app.get('/api/locate/status')
def locate_status():
    """Postal lookup uses the server's OneMap token or OneMap public search, and is offered only when it works."""
    return {'postal': _probe_postal()}

@app.get('/api/locate')
def locate(postal: str = Query(pattern=r'^\d{6}$')):
    client = None
    try:
        client = _onemap_client()
        found = client.locate_postal(postal)
    except Exception:
        found = None
    if found:
        return found
    if client is None or client.map_data_stale or not client.postal_lookup_available():
        raise HTTPException(503, 'Postal lookup is unavailable right now. Try “Use my location” or the example.')
    raise HTTPException(404, 'That postal code could not be located. Check the six digits or try “Use my location”.')

@app.get('/reports/{name}')
def reports(name:str):
    if name not in {'DATA_REPORT.md','MODEL_REPORT.md'}: raise HTTPException(404)
    return FileResponse(ROOT/name,media_type='text/markdown',filename=name)

@app.get('/prototype.html')
def standalone():
    return FileResponse(ROOT/'output/denguesux.html',media_type='text/html')

app.mount('/',StaticFiles(directory=ROOT/'app/web',html=True),name='frontend')
