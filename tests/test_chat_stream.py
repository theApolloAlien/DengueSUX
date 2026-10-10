import io
import json
from types import SimpleNamespace
from pathlib import Path
from fastapi.testclient import TestClient
import app as server
from denguesux import assistant as A
ROOT=Path(__file__).resolve().parents[1]

def test_serving_stream_emits_received_deltas_and_closes():
    stream=io.BytesIO(b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: {"choices":[{"delta":{"content":" there"}}]}\n\ndata: [DONE]\n\n')
    calls=[]
    def do(*a,**kw):calls.append(kw);return {'contents':stream}
    result=list(A.make_final_stream('example',SimpleNamespace(api_client=SimpleNamespace(do=do)))([]))
    assert result==['Hello',' there'] and stream.closed
    assert calls[0]['body']['stream'] is True

def test_sse_orders_real_tool_steps_deltas_and_typed_completion(monkeypatch):
    replies=iter([{'tool_calls':[{'id':'a','function':{'name':'top_areas','arguments':'{}'}}]},{'content':'discarded non-streamed planner answer'}])
    monkeypatch.setattr(server,'_llm_endpoint',lambda:'test')
    monkeypatch.setattr(server,'_genie_space',lambda:None)
    monkeypatch.setattr(A,'make_llm',lambda _:lambda *args:next(replies))
    monkeypatch.setattr(A,'make_final_stream',lambda _:lambda messages:iter(['Look at ','these areas.']))
    response=TestClient(server.app).post('/api/chat/stream',json={'messages':[{'role':'user','content':'top areas'}]})
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert [e['type'] for e in events]==['step','delta','delta','done']
    assert events[0]['tool']=='top_areas'
    assert events[-1]['answer']=='Look at these areas.'
    assert events[-1]['cards'][0]['type']=='top_areas'
    assert 'discarded' not in response.text
    assert response.headers['content-type'].startswith('text/event-stream')

def test_sse_unconfigured_endpoint_has_clean_fallback(monkeypatch):
    monkeypatch.setattr(server,'_llm_endpoint',lambda:None)
    assert TestClient(server.app).post('/api/chat/stream',json={'messages':[{'role':'user','content':'hello'}]}).status_code==503
