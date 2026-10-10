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


def test_showcase_prompts_leads_and_typed_matches_use_saved_data():
    run(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{},document:{},matchMedia:()=>({matches:true}),console};
vm.runInNewContext(fs.readFileSync('app/web/showcase.js','utf8'),context);
const S=context.window.Showcase;S.init(data);
const ids=S.prompts().map(p=>p.id);
assert.equal(ids[0],'demo');
for(const id of ['hotspots','how'])assert(ids.includes(id),id);
const t=data.current.totals;
assert(S.lead('hotspots').startsWith(`${t.clusters} active clusters with ${t.cluster_cases} people`));
const o=data.model.prospective.overall;
assert(S.lead('accuracy').includes(`${o.n} weeks`));
assert(S.lead('accuracy').includes(o.selected.mae.toFixed(1)));
const route=S.prompts().find(p=>p.id==='route');
if(route)assert(S.lead('route',{area:route.area}).includes(`${data.inspection.areas[route.area].stops.length} places`));
assert.equal(S.match('How does DengueSUX work?'),'how');
assert.equal(S.match('How accurate is the forecast?'),'accuracy');
assert.equal(S.match('What is driving the forecast?'),'drivers');
assert.equal(S.match('Show this week’s hotspots on a map'),'hotspots');
assert.equal(S.match('Walk me through this week'),'demo');
assert.equal(S.match('What changed since the last snapshot?'),'changes');
assert.equal(S.match('Is my block near a cluster?'),null);
for(const id of ['hotspots','outlook','route','accuracy','how'])for(const s of S.sources(id)){assert(s.name);assert(!s.url||s.url.startsWith('https://'),s.url);}
""")


def test_showcase_hides_forecast_prompts_without_a_live_outlook():
    data = json.loads((ROOT / 'output/web/dashboard.json').read_text())
    data['model']['live_forecast'] = {'available': False}
    run(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{},document:{},matchMedia:()=>({matches:true}),console};
vm.runInNewContext(fs.readFileSync('app/web/showcase.js','utf8'),context);
const S=context.window.Showcase;S.init(data);
const ids=S.prompts().map(p=>p.id);
assert(!ids.includes('outlook')&&!ids.includes('drivers'),ids.join());
assert(S.lead('outlook').includes('unavailable'));
""", json.dumps(data))
