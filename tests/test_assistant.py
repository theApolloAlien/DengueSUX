import json
import copy
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
import pytest
from denguesux import assistant as A

ROOT = Path(__file__).resolve().parents[1]
DATA = A.load_data(ROOT)

def scripted(*replies):
    """An LLM that returns the given assistant messages in order and records what it was sent."""
    seen = []
    def llm(messages, tools):
        seen.append((json.loads(json.dumps(messages)), tools))
        return replies[len(seen) - 1]
    llm.seen = seen
    return llm

def call(name, **args):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': f'c-{name}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}

def say(text):
    return {'role': 'assistant', 'content': text}

def ask(text, llm, **kw):
    return A.run_chat([{'role': 'user', 'content': text}], llm, ROOT, **kw)

def test_greeting_needs_no_tools_and_prompt_carries_today_and_guardrails():
    llm = scripted(say('Hello! I can help with area priorities.'))
    out = ask('hello', llm)
    assert out['answer'].startswith('Hello') and out['steps'] == [] and out['sources'] == []
    prompt = llm.seen[0][0][0]['content']
    assert 'Today is' in prompt and 'not a validated local forecast' in prompt and 'at least 10 people' in prompt
    assert {t['function']['name'] for t in llm.seen[0][1]} >= {'get_area', 'top_areas', 'inspection_plan', 'forecast_week', 'query_database', 'data_status'}

def test_date_is_given_to_the_model_in_singapore_time():
    prompt = A.system_prompt(DATA, datetime(2026, 10, 10, 23, 30, tzinfo=A.SGT))
    assert 'Saturday 10 October 2026' in prompt

def test_tool_loop_runs_tool_feeds_result_back_and_collects_sources_and_actions():
    top = DATA['current']['areas'][0]
    llm = scripted(call('get_area', area=top['name'].lower()), say(f"{top['name']} is busy. [[clusters]]"))
    out = ask(f"why is {top['name']} high", llm)
    assert out['steps'] == [{'tool': 'get_area', 'args': {'area': top['name'].lower()}}]
    assert [s['id'] for s in out['sources']] == ['clusters', 'weather']
    tool_msg = llm.seen[1][0][-1]
    assert tool_msg['role'] == 'tool' and json.loads(tool_msg['content'])['name'] == top['name']
    assert {'type': 'select_area', 'area': top['code'], 'label': 'Show on map'} in out['actions']

def test_unknown_area_returns_suggestions_not_a_guess():
    assert A.tool_get_area(DATA, 'Bedoc')[0]['name'] == 'Bedok'  # clear typo
    res, _ = A.tool_get_area(DATA, 'Jurong Eest')  # equally close to East and West: ask, don't guess
    assert res['error'] == 'unknown_area' and set(res['did_you_mean']) == {'Jurong East', 'Jurong West'}
    res, _ = A.tool_get_area(DATA, 'Atlantis')
    assert res['error'] == 'unknown_area' and 'did_you_mean' in res

def test_forecast_months_and_out_of_range_year():
    res, _ = A.tool_forecast_week(DATA, 'March 2022')
    assert res['target_week_start'].startswith('2022-03') and res['forecast_level'] in ('Low', 'Medium', 'High')
    res, _ = A.tool_forecast_week(DATA, 'first high warning')
    assert res['issue_date'] == res['first_high_warning_issued']
    res, _ = A.tool_forecast_week(DATA, 'March 2026')
    assert res['error'] == 'no_such_week' and '2022' in res['note']
    res, _ = A.tool_forecast_week(DATA, 'peak')
    assert res['reported_people'] == round(DATA['model']['peak_lead_time']['peak_people'])

def test_inspection_plan_for_area_without_clusters_points_to_busy_areas():
    quiet = next(a for a in DATA['current']['areas'] if a['cluster_count'] == 0)
    res, _ = A.tool_inspection_plan(DATA, quiet['name'])
    assert res['stops'] == [] and res['busiest_areas_instead']

def test_unknown_tool_and_bad_arguments_do_not_crash_the_loop():
    llm = scripted({'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': '1', 'type': 'function', 'function': {'name': 'drop_tables', 'arguments': '{}'}},
        {'id': '2', 'type': 'function', 'function': {'name': 'query_database', 'arguments': 'not json'}}]}, say('Sorry, I could not do that.'))
    out = ask('hi', llm)
    results = [json.loads(m['content']) for m in llm.seen[1][0] if m['role'] == 'tool']
    assert results[0]['error'] == 'unknown_tool' and results[1]['error'] == 'bad_arguments'
    assert out['answer'].startswith('Sorry')

def test_query_database_uses_genie_and_degrades_without_it():
    genie = lambda q: {'answer': None, 'columns': ['priority', 'areas'], 'rows': [['High', 3]], 'sql': 'SELECT 1', 'truncated': False}
    llm = scripted(call('query_database', question='how many areas are high'), say('3 areas. [[genie]]'))
    out = ask('how many areas are high', llm, genie=genie)
    assert [s['id'] for s in out['sources']] == ['genie']
    assert json.loads(llm.seen[1][0][-1]['content'])['rows'] == [['High', 3]]
    def broken(q): raise TimeoutError
    llm = scripted(call('query_database', question='x y z'), say('Genie is unavailable.'))
    ask('x', llm, genie=broken)
    assert json.loads(llm.seen[1][0][-1]['content'])['error'] == 'database_unavailable'
    llm = scripted(call('query_database', question='x y z'), say('No database.'))
    ask('x', llm)
    assert json.loads(llm.seen[1][0][-1]['content'])['error'] == 'database_unavailable'

def test_loop_is_capped_and_final_turn_has_no_tools():
    llm = scripted(call('data_status'), call('data_status'), say('Done.'))
    out = ask('status', llm, max_steps=2)
    assert out['answer'] == 'Done.' and len(llm.seen) == 3 and llm.seen[-1][1] is None

def test_history_is_trimmed_and_must_end_with_user():
    msgs = [{'role': 'assistant', 'content': 'stale'}] + [{'role': 'user', 'content': f'q{i}'} for i in range(12)]
    cleaned = A.clean_messages(msgs)
    assert len(cleaned) <= A.MAX_TURNS and cleaned[0]['role'] == 'user'
    with pytest.raises(ValueError):
        A.clean_messages([{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': 'hello'}])

def test_reasoning_model_content_parts_are_flattened():
    msg = {'content': [{'type': 'reasoning', 'summary': []}, {'type': 'text', 'text': 'Hello there'}]}
    assert A._text(msg) == 'Hello there'


@pytest.fixture
def current_outlook_data():
    data = copy.deepcopy(DATA)
    data['model']['latest_label'] = '2026-10-03'
    data['model']['current_forecast'] = {'available': True, 'max_age_days': 21}
    data['meta'].setdefault('labels', {})['gate'] = {'available': True}
    row = {'issue_date': '2026-10-04', 'target_date': '2026-10-11', 'target_week_end': '2026-10-17',
           'prediction': 69., 'lower': 51., 'upper': 94., 'weather_inputs_missing': 2,
           'weather_inputs_total': 24, 'weather_inputs_imputed': True, 'top_features': []}
    data['model']['live_forecast'] = {'available': True, 'issued_from_week_end': '2026-10-03',
                                     'latest_reported_people': 71, 'headline': row, 'forecasts': [row]}
    return data


def test_live_tool_returns_ranges_missingness_sources_and_navigation(current_outlook_data, monkeypatch):
    monkeypatch.setattr(A, 'load_data', lambda _: current_outlook_data)
    llm = scripted(call('live_outlook'), say('About 69 people, range 51–94. [[live]]'))
    out = ask('What is expected next week?', llm, now=datetime(2026, 10, 10, tzinfo=A.SGT))
    result = out['trace'][0]['result']
    assert result['segment'] == 'live'
    assert result['headline']['lower'] == 51 and result['headline']['upper'] == 94
    assert result['headline']['weather_inputs_imputed'] is True
    assert {s['id'] for s in out['sources']} == {'live', 'bulletin'}
    assert out['actions'] == [{'type': 'show_live', 'label': 'Open the national forecast'}]
    assert 'public weekly case data ends Dec 2022' not in llm.seen[0][0][0]['content']


@pytest.mark.parametrize('change', ['live_disabled', 'gate_disabled', 'export_gate_disabled', 'missing_date', 'expired'])
def test_live_tool_and_status_refuse_stale_or_unverified_outlook(current_outlook_data, change):
    data = current_outlook_data
    now = datetime(2026, 10, 10, tzinfo=A.SGT)
    if change == 'live_disabled': data['model']['live_forecast']['available'] = False
    elif change == 'gate_disabled': data['model']['current_forecast']['available'] = False
    elif change == 'export_gate_disabled': data['meta']['labels']['gate']['available'] = False
    elif change == 'missing_date': del data['model']['live_forecast']['headline']['target_week_end']
    else: now = datetime(2026, 10, 18, tzinfo=A.SGT)
    result, _ = A.tool_live_outlook(data, now)
    assert result['error'] == 'live_forecast_unavailable'
    assert 'headline' not in result
    assert A.tool_data_status(data, now)[0]['forecast_mode'] == 'historical_evaluation_only'
    assert A._actions([{'tool': 'live_outlook', 'result': result}]) == []


def test_retrospective_evaluation_remains_available_without_live_forecast(current_outlook_data):
    data = current_outlook_data
    data['model']['live_forecast'] = None
    result, sources = A.tool_forecast_evaluation(data)
    assert result['segment'] == 'prospective'
    assert result['overall'] == data['model']['prospective']['overall']
    assert 'not performance recorded in real time' in result['caveat']
    assert 'prospective' in sources


def test_iso_date_outside_replay_does_not_silently_return_2022_week():
    result, _ = A.tool_forecast_week(DATA, '2026-03-01')
    assert result['error'] == 'no_such_week'
    assert 'no live national forecast' not in result['note']


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is needed for the vanilla-JS assistant check')
def test_frontend_live_action_and_stale_guards_match_backend(current_outlook_data):
    script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
let clock='2026-10-10T12:00:00+08:00',opened=0;
class FixedDate extends Date {constructor(...args){if(args.length)super(...args);else super(clock);}static now(){return Date.parse(clock);}}
const context={window:{},document:{querySelector:()=>({})},Date:FixedDate,setTimeout,matchMedia:()=>({matches:true})};
const source=fs.readFileSync('app/web/assistant.js','utf8').replace('window.Assistant = {init, tools, respond, sqlFor};','window.Assistant = {init, tools, respond, sqlFor, actions:ACTIONS};');
vm.runInNewContext(source,context);
const app=context.window.Assistant;
app.init(data,{showLive:()=>opened++});
assert.equal(app.tools.live_outlook().result.low,51);
assert.equal(app.tools.live_outlook().result.imputed_weather[0].missing,2);
app.actions.show_live({});assert.equal(opened,1);
data.model.current_forecast.available=false;
assert.equal(app.tools.live_outlook().result.error,'no_live_forecast');
assert.equal(app.sqlFor('latest forecast').run().length,0);
assert.equal(app.tools.forecast_evaluation().result.n,data.model.prospective.overall.n);
data.model.current_forecast.available=true;clock='2026-10-18T12:00:00+08:00';
assert.equal(app.tools.live_outlook().result.error,'no_live_forecast');
app.respond('forecast for March 2026',()=>{}).then(r=>{
assert.equal(r.results[0].result.error,'no_such_week');
assert.equal(r.answer.actions.length,0);
}).catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script], input=json.dumps(current_outlook_data), text=True,
                            cwd=ROOT, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_accuracy_figures_are_named_for_what_they_measure():
    result, _ = A.tool_forecast_evaluation(DATA)
    plain, overall = result['plain_overall'], DATA['model']['prospective']['overall']
    assert plain['average_error_people_per_week'] == round(overall['selected']['mae'], 1)
    assert plain['weeks_risk_level_matched_percent'] == round(overall['selected']['accuracy'] * 100, 1)
    assert 'Not an overall accuracy score' in result['definitions']['weeks_risk_level_matched_percent']
    assert 'no single accuracy percentage' in A.system_prompt(DATA)


def test_unsupported_percentages_are_corrected_then_dropped():
    calls = [{'tool': 'forecast_evaluation', 'result': A.tool_forecast_evaluation(DATA)[0]}]
    mae = calls[0]['result']['plain_overall']['average_error_people_per_week']
    good = f'Average error was {mae} people a week; the level matched in {calls[0]["result"]["plain_overall"]["weeks_risk_level_matched_percent"]}% of weeks.'
    assert A.unsupported_figures(good, calls) == []
    assert A.unsupported_figures('The model is 94.5% accurate.', calls) == ['94.5%']
    # One correction pass with the model.
    fixed = A.checked_answer('The model is 94.5% accurate.', calls, [{'role': 'user', 'content': 'How accurate?'}], scripted(say(good)))
    assert fixed == good
    # If the correction still invents a figure, the sentence carrying it is dropped.
    kept = A.checked_answer(f'Error is {mae} people a week. It is 94.5% accurate.', calls, [{'role': 'user', 'content': 'q'}], scripted(say('Still 97.1% accurate.')))
    assert kept == f'Error is {mae} people a week.'
    # General answers (no tools) are not checked against tool results.
    assert A.checked_answer('Most people recover in about 1.5 weeks.', [], [], None) == 'Most people recover in about 1.5 weeks.'


def test_general_answer_gets_a_shape_checked_diagram():
    diagram_json = json.dumps({'kind': 'cycle', 'title': 'How dengue spreads', 'related_view': 'hotspots', 'items': [
        {'label': 'Infected person', 'detail': 'An Aedes mosquito bites someone with dengue.', 'icon': 'person'},
        {'label': 'Virus grows', 'detail': 'It multiplies in the mosquito for about a week.', 'icon': 'bug'},
        {'label': 'Next bite', 'detail': 'The mosquito passes it on.', 'icon': 'not-an-icon'},
        {'label': 'Fake stat', 'detail': '87% of cases', 'icon': 'warning'}]})
    llm = scripted(say('Dengue spreads through Aedes mosquito bites.'), say('Here you go:\n' + diagram_json))
    out = ask('How does dengue spread?', llm, diagram=A.make_diagrammer(llm))
    d = out['diagram']
    assert d['kind'] == 'cycle' and d['related_view'] == 'hotspots' and len(d['items']) == 3
    assert d['items'][2]['icon'] is None  # unknown icons are dropped, percentages are refused
    assert out['trace'] == []
    # Greetings and invalid JSON draw nothing.
    llm = scripted(say('Hello! I can help.'))
    assert 'diagram' not in ask('Hello', llm, diagram=A.make_diagrammer(llm))
    llm = scripted(say('Dengue is a viral infection.'), say('not json'))
    assert 'diagram' not in ask('What is dengue?', llm, diagram=A.make_diagrammer(llm))
    assert A.clean_diagram({'kind': 'facts', 'items': [{'label': 'Only one'}]}) is None


def test_parallel_chats_share_one_data_load(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    (tmp_path / 'output/web').mkdir(parents=True)
    (tmp_path / 'output/web/dashboard.json').write_text(json.dumps(DATA))
    with ThreadPoolExecutor(16) as pool:
        loaded = list(pool.map(lambda _: A.load_data(tmp_path), range(64)))
    assert all(d is loaded[0] for d in loaded)


def test_live_outlook_states_its_direction_from_the_numbers(current_outlook_data):
    result, _ = A.tool_live_outlook(current_outlook_data, datetime(2026, 10, 11, tzinfo=A.SGT))
    if 'error' in result:
        pytest.skip(result['note'])
    latest, point = result['latest_reported_people'], current_outlook_data['model']['live_forecast']['headline']['prediction']
    want = 'about the same' if abs(point - latest) <= max(5, .1 * latest) else 'higher' if point > latest else 'lower'
    assert result['forecast_vs_latest_reported_week'] == want
    has_normal = bool((current_outlook_data['model']['live_forecast']['headline'].get('normal') or {}).get('median'))
    assert result['forecast_vs_typical_week'] in (('quieter than usual', 'about usual', 'busier than usual') if has_normal else (None,))
    prompt = A.system_prompt(current_outlook_data)
    assert 'Never infer a direction yourself' in prompt and '疟疾' not in prompt
    assert '疟疾' in A.language_notes('zh') and 'கொசுக்கடி' in A.language_notes('ta') and '疟疾' not in A.language_notes('ta')
    assert A.language_notes('en') == '' and 'Spray, Apply, Wear' in A.language_notes('ms')
