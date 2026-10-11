import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is needed for the vanilla-JS checks')


def run(script, data=None):
    stdin = data if data is not None else (ROOT / 'output/web/dashboard.json').read_text()
    result = subprocess.run(['node', '-e', script], input=stdin, text=True, cwd=ROOT, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_offline_help_answer_offers_follow_ups_instead_of_failing():
    # A vague question routes to the help intent; it once threw because suggestions() had been removed.
    run(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{},document:{querySelector:()=>({})},setTimeout,matchMedia:()=>({matches:true})};
vm.runInNewContext(fs.readFileSync('app/web/assistant.js','utf8'),context);
const app=context.window.Assistant;app.init(data,{});
app.respond('jj',()=>{}).then(r=>{
  const asks=r.answer.actions.filter(a=>a.ask).map(a=>a.label);
  assert(asks.length>=3,'help offers follow-up questions');
  assert(asks.includes('Which areas should we check first?'));
  const top=data.current.areas.filter(a=>a.risk==='High').sort((a,b)=>b.cluster_cases-a.cluster_cases)[0];
  if(top)assert(asks.includes(`Why is ${top.name} High?`));
}).catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_suggestions_are_worded_from_the_current_data():
    run(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{},document:{},matchMedia:()=>({matches:true}),console};
vm.runInNewContext(fs.readFileSync('app/web/showcase.js','utf8'),context);
const S=context.window.Showcase;S.init(data);
const list=S.suggestions('en'),ids=list.map(p=>p.id),t=data.current.totals;
assert(!ids.includes('demo'),'no briefing prompt');
assert.equal(ids[0],'hotspots');
for(const id of ['hotspots','how','fever'])assert(ids.includes(id),id);
assert(list[0].q.includes(String(t.clusters)),list[0].q);
for(const p of list){assert(!/demo/i.test(p.q),p.q);assert(p.en,p.id);}
const route=list.find(p=>p.id==='route');
if(route){const name=data.current.areas.find(a=>a.code===route.area).name;assert(route.q.includes(name));assert.equal(route.visual.id,'route');assert.equal(route.visual.area,route.area);
  assert(S.lead('route',{area:route.area}).includes(`${data.inspection.areas[route.area].stops.length} places`));}
const o=data.model.prospective.overall;
assert(list.find(p=>p.id==='accuracy').q.includes(String(o.n)));
// Every language gets the same prompts, with the same live values.
for(const lang of ['zh','ms','ta']){const other=S.suggestions(lang);assert.deepEqual(other.map(p=>p.id),ids,lang);assert(other[0].q.includes(String(t.clusters)),other[0].q);assert.equal(other[0].en,list[0].en);}
assert(S.lead('hotspots').startsWith(`${t.clusters} active clusters with ${t.cluster_cases} people`));
assert(S.lead('accuracy').includes(`${o.n} weeks`));
assert(S.lead('accuracy').includes(o.selected.mae.toFixed(1)));
const id=q=>S.match(q)?.id??null;
assert.equal(id('How does DengueSUX work?'),'how');
assert.equal(id('How accurate is the forecast?'),'accuracy');
assert.equal(id('What is driving the forecast?'),'drivers');
assert.equal(id('Show this week’s hotspots on a map'),'hotspots');
assert.equal(id('Walk me through this week'),null);
assert.equal(id('What changed since the last snapshot?'),'changes');
assert.equal(id('How recent is this data?'),'freshness');
assert.equal(id('When did the 2022 warning fire?'),'replay');
assert.equal(id('Is my block near a cluster?'),null);
const named=data.current.areas[0];assert.deepEqual({...S.match(`Tell me about ${named.name}`)},{id:'area',area:named.code});
for(const id of ['hotspots','outlook','route','accuracy','how'])for(const s of S.sources(id)){assert(s.name);assert(!s.url||s.url.startsWith('https://'),s.url);}
""")


def test_visuals_follow_the_tools_an_answer_used():
    run(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{},document:{},matchMedia:()=>({matches:true}),console};
vm.runInNewContext(fs.readFileSync('app/web/showcase.js','utf8'),context);
const S=context.window.Showcase;S.init(data);
const ids=v=>v.map(x=>x.id+(x.area?':'+x.area:'')).join();
const planned=data.current.areas.find(a=>a.cluster_count&&data.inspection.areas[a.code]?.stops?.length),quiet=data.current.areas.find(a=>!a.cluster_count);
// Any question, in any language, gets the views for the data tools its answer called.
assert.equal(ids(S.visualsFor('哪里最需要检查？',[{tool:'top_areas',args:{n:5},result:{areas:[]}}])),'hotspots');
assert.equal(ids(S.visualsFor('Is it reliable?',[{tool:'forecast_evaluation',args:{},result:{}}])),'accuracy');
assert.equal(ids(S.visualsFor('Ist es aktuell?',[{tool:'data_status',args:{},result:{}}])),'freshness');
assert.equal(ids(S.visualsFor('Peak?',[{tool:'forecast_week',args:{when:'peak'},result:{week_index:3}}])),'replay');
assert.equal(ids(S.visualsFor('Area?',[{tool:'get_area',args:{area:quiet.name.toUpperCase()},result:{name:quiet.name}}])),'area:'+quiet.code);
assert.equal(ids(S.visualsFor('Check Saturday',[{tool:'get_area',args:{code:planned.code},result:{}},{tool:'inspection_plan',args:{area:planned.name},result:{area:planned.name}}])),'route:'+planned.code);
assert.equal(ids(S.visualsFor('Check Saturday',[{tool:'inspection_plan',args:{area:'x'},area_code:planned.code,result:{}}])),'route:'+planned.code);
// A database answer is charted from its own columns, whatever was asked.
const table=S.visualsFor('Weeks rated High by year?',[{tool:'query_database',args:{},result:{columns:['year','weeks'],rows:[['2023','4'],['2024','9']],sql:'select 1'}}]);
assert.equal(table[0].id,'table');assert.equal(table[0].rows.length,2);
assert.equal(ids(S.visualsFor('x',[{tool:'query_database',result:{columns:['a'],rows:[]}}])),'');
// Failed tools draw nothing; a related typed question still gets its view.
assert.equal(ids(S.visualsFor('hello',[{tool:'top_areas',result:{error:'x'}}])),'');
assert.equal(ids(S.visualsFor('What changed lately?',[])),'changes');
// A pressed suggestion leads; at most two views per answer; old saved "route:JW" strings still parse.
const both=S.visualsFor('Where should we check?',[{tool:'top_areas',result:{}},{tool:'inspection_plan',args:{area:planned.name},result:{}},{tool:'forecast_evaluation',result:{}}],{id:'how'});
assert.equal(both.length,2);assert.equal(both[0].id,'how');
assert.equal(ids(S.visualsFor('',[], 'route:'+planned.code)),'route:'+planned.code);
""")


def test_forecast_suggestions_and_visuals_need_a_live_outlook():
    data = json.loads((ROOT / 'output/web/dashboard.json').read_text())
    data['model']['live_forecast'] = {'available': False}
    run(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{},document:{},matchMedia:()=>({matches:true}),console};
vm.runInNewContext(fs.readFileSync('app/web/showcase.js','utf8'),context);
const S=context.window.Showcase;S.init(data);
const ids=S.suggestions().map(p=>p.id);
assert(!ids.includes('outlook')&&!ids.includes('drivers'),ids.join());
assert.equal(S.visualsFor('Will cases rise next week?',[{tool:'live_outlook',result:{}}]).length,0);
assert(S.lead('outlook').includes('unavailable'));
""", json.dumps(data))


def test_every_visual_label_has_all_three_translations():
    import re
    src = (ROOT / 'app/web/showcase.js').read_text()
    table = json.loads(src[src.index(' const STR=') + len(' const STR='):src.index(';\n let LANG')])
    keys = set(re.findall(r"tr\('((?:[^'\\]|\\.)+)'", src))
    keys |= set(re.findall(r"stat\([^,()]+(?:\([^()]*\))?,'([^']+)'", src))
    keys |= {'High', 'Medium', 'Low', 'Quieter than usual', 'Busier than usual', 'About usual', 'Recent cases', 'Time of year', 'Rain', 'Heat'}
    for lang in ('zh', 'ms', 'ta'):
        missing = sorted(k for k in keys if k not in table[lang])
        assert not missing, (lang, missing)


def test_visuals_draw_in_the_answer_language():
    run(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const made=[];const node=()=>({className:'',innerHTML:'',setAttribute(){},append(){},classList:{add(){}},querySelector:()=>null,querySelectorAll:()=>[],insertAdjacentHTML(){},addEventListener(){}});
const context={window:{},document:{createElement:()=>{const n=node();made.push(n);return n;}},matchMedia:()=>({matches:true}),innerWidth:1280,console,IntersectionObserver:class{observe(){}},CSS:{escape:s=>s}};
vm.runInNewContext(fs.readFileSync('app/web/showcase.js','utf8'),context);
const S=context.window.Showcase;S.init(data);
const box={closest:()=>null,append(){}};
S.render(box,{id:'changes'},'zh');assert(made.at(-1).innerHTML.includes('个感染群 ·'),'Chinese labels');
S.render(box,{id:'freshness'},'ta');assert(made.at(-1).innerHTML.includes('சரிபார்த்த மூலங்கள்'),'Tamil labels');
S.render(box,{id:'freshness'},'ms');assert(made.at(-1).innerHTML.includes('sumber disemak'),'Malay labels');
S.render(box,{id:'changes'},'en');assert(made.at(-1).innerHTML.includes('clusters ·'),'English stays English');
assert(!made.some(n=>n.innerHTML.includes('viz-empty')),'every view drew');
""")
