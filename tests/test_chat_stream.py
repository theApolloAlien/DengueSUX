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

def test_stream_llm_assembles_tool_calls_and_streams_text():
    body=(b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"get_","arguments":"{\\"area"}}]}}]}\n\n'
          b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"area","arguments":"\\": \\"Bedok\\"}"}}]}}]}\n\n'
          b'data: [DONE]\n\n')
    stream=io.BytesIO(body);seen=[]
    call=A.make_stream_llm('example',SimpleNamespace(api_client=SimpleNamespace(do=lambda *a,**kw:{'contents':stream})))
    message=call([],[{'type':'function'}],seen.append)
    assert message['tool_calls']==[{'id':'c1','type':'function','function':{'name':'get_area','arguments':'{"area": "Bedok"}'}}]
    assert seen==[] and stream.closed
    text=io.BytesIO(b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]\n\n')
    call=A.make_stream_llm('example',SimpleNamespace(api_client=SimpleNamespace(do=lambda *a,**kw:{'contents':text})))
    assert call([],None,seen.append)=={'role':'assistant','content':'Hi'} and seen==['Hi']

def test_sse_orders_real_tool_steps_deltas_and_typed_completion(monkeypatch):
    steps=iter([({'tool_calls':[{'id':'a','function':{'name':'top_areas','arguments':'{}'}}]},[]),
                ({'content':'Look at these areas.'},['Look at ','these areas.'])])
    def stream_llm(messages,tools,on_delta):
        message,deltas=next(steps)
        for d in deltas:on_delta(d)
        return message
    monkeypatch.setattr(server,'_llm_endpoint',lambda:'test')
    monkeypatch.setattr(server,'_genie_space',lambda:None)
    monkeypatch.setattr(A,'make_llm',lambda _:lambda *args:{'content':'unused non-streamed call'})
    monkeypatch.setattr(A,'make_stream_llm',lambda _:stream_llm)
    response=TestClient(server.app).post('/api/chat/stream',json={'messages':[{'role':'user','content':'top areas'}]})
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert [e['type'] for e in events]==['step','delta','delta','done']
    assert events[0]['tool']=='top_areas'
    assert events[-1]['answer']=='Look at these areas.'
    assert events[-1]['cards'][0]['type']=='top_areas'
    assert 'unused' not in response.text
    assert response.headers['content-type'].startswith('text/event-stream')

def test_sse_unconfigured_endpoint_has_clean_fallback(monkeypatch):
    monkeypatch.setattr(server,'_llm_endpoint',lambda:None)
    assert TestClient(server.app).post('/api/chat/stream',json={'messages':[{'role':'user','content':'hello'}]}).status_code==503
