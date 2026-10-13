/* Ask DengueSUX. With a hosted model configured, /api/chat answers by calling tools over the exported gold data (and Databricks
   Genie for SQL) and returns the sources it used. Without it, or if it fails, the rule-based responder below composes answers
   locally from the same kind of function results, so the panel always works. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeUrl = v => { try { const u = new URL(v); return u.protocol === 'https:' ? esc(u.href) : '#'; } catch { return '#'; } };
  const icon = n => `<i class="ph ph-${n}" aria-hidden="true"></i>`;
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const num = (v, d=0) => finite(v) ? v.toLocaleString('en-SG', {maximumFractionDigits:d, minimumFractionDigits:0}) : '—';
  const date = (v, opts={day:'numeric', month:'short', year:'numeric'}) => {
    if (!v) return 'unavailable';
    const raw = String(v), text = /^\d{14}$/.test(raw) ? `${raw.slice(0,4)}-${raw.slice(4,6)}-${raw.slice(6,8)}` : raw;
    const d = new Date(text.length === 10 ? `${text}T12:00:00+08:00` : text);
    return Number.isNaN(+d) ? raw : d.toLocaleDateString('en-SG', opts);
  };
  const wait = ms => new Promise(r => setTimeout(r, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : ms));
  const TABLE = 'workspace.denguesux';
  const MONTHS = ['january','february','march','april','may','june','july','august','september','october','november','december'];
  let data = {}, hooks = {}, busy = false, mode = 'ask', history = [], genieThread = null;

  const current = () => data.current || {};
  const model = () => data.model || {};
  const liveForecast = () => {
    if (window.DengueLiveForecast) return window.DengueLiveForecast();
    const m=model(),live=m.live_forecast,gate=m.current_forecast||{};
    if(live?.available!==true||gate.available!==true||data.meta?.labels?.gate?.available===false)return null;
    const today=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Singapore'});
    const age=(Date.parse(`${today}T00:00:00Z`)-Date.parse(`${live.issued_from_week_end}T00:00:00Z`))/86400000;
    return age>=0&&age<=(gate.max_age_days||21)&&live.headline?.target_week_end>=today?live:null;
  };
  const areas = () => [...(current().areas || [])].sort((a,b) => (b.cluster_cases||0)-(a.cluster_cases||0) || (b.cluster_count||0)-(a.cluster_count||0) || a.name.localeCompare(b.name));
  const predictions = () => model().predictions || [];
  const clustersIn = code => (current().clusters?.features || []).map(f => f.properties).filter(p => (p.area_codes || [p.area_code]).includes(code));
  const sourceUrl = name => (data.meta?.sources || []).find(s => s.name.startsWith(name))?.url;
  const bulletinUrl = () => [...(data.meta?.labels?.contract?.sources||[])].reverse().find(s=>s.url)?.url||sourceUrl('Weekly national');
  const SOURCES = {
    clusters: () => ({id:'clusters', name:'NEA active clusters · data.gov.sg', date:current().as_of, url:sourceUrl('NEA active clusters'), table:'gold_area_priorities'}),
    weather: () => ({id:'weather', name:'NEA weather stations · data.gov.sg', date:current().weather_date, url:sourceUrl('NEA weather'), table:'gold_area_priorities'}),
    growth: () => ({id:'growth', name:'Daily cluster snapshots', date:data.growth?.retrieved_at || current().as_of, table:'gold_cluster_growth'}),
    inspection: () => ({id:'inspection', name:'OneMap places and walking route', date:data.inspection?.as_of, url:'https://www.onemap.gov.sg/', table:'inspection_routes'}),
    forecast: () => ({id:'forecast', name:`2022 forecast backtest · MLflow run ${String(model().run_id || '').slice(0,8)}`, date:data.meta?.generated_at, table:'gold_national_predictions'}),
    bulletin: () => ({id:'bulletin', name:'Official MOH/CDA weekly infectious disease bulletin', date:model().latest_label, url:bulletinUrl(), table:'silver_national_weekly'}),
    live: () => ({id:'live', name:'National outlook with 80% ranges · MOH / CDA labels', date:model().live_forecast?.issued_from_week_end, url:bulletinUrl(), table:'gold_national_predictions'}),
    prospective: () => ({id:'prospective', name:`2023+ retrospective evaluation · MLflow run ${String(model().run_id || '').slice(0,8)}`, date:data.meta?.generated_at, table:'gold_national_predictions'})
  };

  /* ---------- Functions the assistant can call ---------- */
  function findArea(text) {
    const q = ` ${String(text).toLowerCase().replace(/[^a-z0-9 ]/g, ' ')} `;
    return [...(current().areas || [])].sort((a,b) => b.name.length - a.name.length).find(a => q.includes(` ${a.name.toLowerCase()} `));
  }
  function weekIndex(text) {
    const rows = predictions(); if (!rows.length) return -1;
    const lead = model().peak_lead_time || {};
    const t = String(text).toLowerCase();
    const year=t.match(/\b(20\d\d)\b/);if(year&&year[1]!=='2022')return -1;
    const iso = t.match(/\b(20\d\d)-(\d\d)-(\d\d)\b/);
    if (iso) { const target = iso[0]; if(target<rows[0].target_date||target>(rows.at(-1).target_week_end||rows.at(-1).target_date))return -1;const i = rows.findIndex(r => r.target_date >= target); return i < 0 ? rows.length-1 : i; }
    const month = MONTHS.findIndex(m => t.includes(m) || new RegExp(`\\b${m.slice(0,3)}\\b`).test(t));
    if (month >= 0) {
      const inMonth = rows.map((r,i) => ({r,i})).filter(({r}) => new Date(`${r.target_date}T12:00:00`).getMonth() === month);
      if (!inMonth.length) return -1;
      const day = t.match(/\b(\d{1,2})\b(?!\d)/)?.[1];
      if (day && !/20\d\d/.test(day)) return inMonth.reduce((best, x) => Math.abs(new Date(`${x.r.target_date}T12:00:00`).getDate()-day) < Math.abs(new Date(`${best.r.target_date}T12:00:00`).getDate()-day) ? x : best).i;
      if (/warning|high|alert/.test(t)) return (inMonth.find(({r}) => r.risk === 'High') || inMonth[0]).i;
      return inMonth[0].i;
    }
    if (/peak/.test(t)) return rows.reduce((b, r, i) => r.actual > rows[b].actual ? i : b, 0);
    if (/warning|first high|turn(ed|s)? high/.test(t)) return Math.max(0, rows.findIndex(r => r.issue_date === lead.selected?.first_high_issue_date));
    return -1;
  }
  const weatherOf = a => {
    const w = a.weather || {}, pick = k => w[k] && finite(w[k].value) ? {value:w[k].value, station:w[k].station_name, km:w[k].distance_km} : null;
    return {rain_mm:pick('rainfall'), temperature_c:pick('temperature'), humidity_pct:pick('humidity')};
  };
  const tools = {
    get_area({code}) {
      const a = (current().areas || []).find(x => x.code === code); if (!a) return {result:{error:'unknown_area'}, sources:[]};
      const clusters = clustersIn(code).sort((x,y) => y.cases - x.cases).map(p => ({id:p.id, locality:p.name, people:p.cases, shared_with:(p.area_names||[]).filter(n => n !== a.name), updated:p.updated_at}));
      return {result:{code:a.code, name:a.name, region:a.region, priority:a.risk, cluster_count:a.cluster_count, people_in_clusters:a.cluster_cases, clusters, weather:weatherOf(a)}, sources:[SOURCES.clusters(), SOURCES.weather()]};
    },
    top_areas({n=5}) {
      return {result:areas().slice(0, n).map((a,i) => ({rank:i+1, code:a.code, name:a.name, priority:a.risk, people_in_clusters:a.cluster_cases, cluster_count:a.cluster_count})), sources:[SOURCES.clusters()]};
    },
    cluster_growth({area}) {
      const g = data.growth || {}, rows = area ? clustersIn(area) : (current().clusters?.features || []).map(f => f.properties);
      return {result:{history_available:g.history_available === true, snapshots_saved:g.snapshot_count ?? 1, baseline_date:g.baseline_date, growing_count:g.growing_count, snapshot_changes:!area && g.changes?.summary ? g.changes : null, clusters:rows.map(p => ({id:p.id, locality:p.name, people:p.cases, status:p.growth_label || 'Not enough history yet', change:p.growth_cases}))}, sources:[SOURCES.growth()]};
    },
    inspection_plan({area}) {
      const plan = data.inspection?.areas?.[area] || {};
      const stops = (plan.stops || []).map(s => ({stop:s.number, name:s.name, type:s.place_type, checklist:s.checklist}));
      return {result:{area, status:plan.status || 'unavailable', message:plan.message, stops, distance_km:plan.route?.distance_m ? plan.route.distance_m/1000 : null, route_method:plan.route?.method, unresolved_blocks:plan.unresolved_blocks || 0}, sources:[SOURCES.inspection(), SOURCES.clusters()]};
    },
    forecast_replay({week}) {
      const r = predictions()[week]; if (!r) return {result:{error:'no_such_week'}, sources:[]};
      const lead = model().peak_lead_time || {};
      return {result:{week_index:week, issue_date:r.issue_date, target_week:r.target_date, forecast:r.selected_prediction ?? r.prediction, reported:r.actual, simple_average:r.baseline, level:r.risk, reported_level:r.actual_risk, origin_week_cases:r.origin_cases, high_threshold:model().thresholds?.high, peak_week:lead.peak_week, peak_people:lead.peak_people, first_high_issue:lead.selected?.first_high_issue_date, weeks_before_peak:lead.selected?.weeks_before_peak}, sources:[SOURCES.forecast(), SOURCES.bulletin()]};
    },
    live_outlook() {
      const l = liveForecast(), o = model().prospective?.overall; if (!l) return {result:{error:'no_live_forecast'}, sources:[]};
      const h = l.headline;
      return {result:{latest_week_end:l.issued_from_week_end, latest_people:l.latest_reported_people, target_week:h.target_date, forecast:h.prediction, low:h.lower, high:h.upper, level:h.risk,
        typical:h.normal, this_week:l.forecasts[0], contributions:(h.top_features || []).map(f => ({feature:f.feature, value:f.value})),
        imputed_weather:(l.forecasts||[]).filter(r=>r.weather_inputs_imputed).map(r=>({week:r.target_date,missing:r.weather_inputs_missing,total:r.weather_inputs_total})),
        test_weeks:o?.n, test_error:o?.selected.mae, test_simple_average_error:o?.baseline.mae, test_range_coverage:o?.interval_coverage}, sources:[SOURCES.live(), SOURCES.prospective()]};
    },
    forecast_evaluation() {
      const evaluation=model().prospective;
      return evaluation?{result:{...evaluation.overall,window:evaluation.window,weather_missingness:model().weather_missingness?.prospective},sources:[SOURCES.prospective()]}:{result:{error:'no_evaluation'},sources:[]};
    },
    explain_forecast({week}) {
      const r = predictions()[week]; if (!r) return {result:{error:'no_such_week'}, sources:[]};
      return {result:{method:r.explanation_method || 'Grouped TreeSHAP contributions', base_value:r.explanation_base, contributions:(r.top_features || []).map(f => ({feature:f.feature, value:f.value}))}, sources:[SOURCES.forecast()]};
    }
  };

  /* ---------- Planning and composing an answer ---------- */
  function planCalls(question) {
    const t = question.toLowerCase(), area = findArea(t), week = weekIndex(t);
    const n = Number(t.match(/\btop\s+(\d{1,2})\b/)?.[1] || t.match(/\b(\d{1,2})\s+(areas|places)\b/)?.[1] || 5);
    if (area && /route|walk|volunteer|inspect|plan|visit|check first|where .*look/.test(t)) return {intent:'route', area, calls:[['get_area', {code:area.code}], ['inspection_plan', {area:area.code}]]};
    if(!area&&!/2022|replay/.test(t)&&/accura|reliab|trust|error|how (well|good)|since 2023/.test(t))return {intent:'evaluation',calls:[['forecast_evaluation',{}]]};
    if (!area && !/2022|replay|peak/.test(t) && /driv(es|ing|er)|why .*(forecast|outlook)|expected in the week/.test(t)) return {intent:'live', calls:[['live_outlook', {}]]};
    if (!area && !/2022|replay|peak/.test(t) && /(next|this|coming) (week|fortnight)|right now|currently|latest|live|expect|national/.test(t)) return {intent:'live', calls:[['live_outlook', {}]]};
    if (/forecast|warning|predict|outlook|drove|driver|shap|replay|2022|peak/.test(t) && !area) {
      const w = week >= 0 ? week : /20\d\d/.test(t)?-1:weekIndex('first high warning');
      return {intent:'forecast', calls:[['forecast_replay', {week:w}], ['explain_forecast', {week:w}]]};
    }
    if (/grow|growing|spread|increas|rising|shrink|what changed|new clusters|since/.test(t)) return {intent:'growth', area, calls:[['cluster_growth', {area:area?.code}]]};
    if (area) return {intent:'area', area, calls:[['get_area', {code:area.code}], ['cluster_growth', {area:area.code}]]};
    if (/top|worst|highest|most|which areas?|where|priorit|rank|hotspot/.test(t)) return {intent:'top', calls:[['top_areas', {n:Math.min(Math.max(n,1),20)}]]};
    return {intent:'help', calls:[]};
  }

  function cite(sources, src) { let i = sources.findIndex(s => s.id === src.id); if (i < 0) { sources.push(src); i = sources.length-1; } return `<sup class="ask-cite">[${i+1}]</sup>`; }
  const people = n => `${num(n)} ${n === 1 ? 'person' : 'people'}`;
  const nearestActive = a => {
    const [lat, lng] = a.centroid || [0,0];
    return areas().filter(x => x.cluster_count && x.code !== a.code && x.centroid).map(x => ({x, d:Math.hypot(x.centroid[0]-lat, (x.centroid[1]-lng)*Math.cos(lat*Math.PI/180))*111})).sort((p,q) => p.d-q.d).slice(0,2);
  };

  // Starter questions follow the current snapshot, so they never point at an area without clusters or a plan.
  function suggestions() {
    const areas = [...(data.current?.areas || [])].sort((a, b) => (b.cluster_cases || 0) - (a.cluster_cases || 0));
    const top = areas.find(a => a.risk === 'High') || areas[0];
    const planned = areas.find(a => data.inspection?.areas?.[a.code]?.stops?.length);
    return ['What’s expected next week?', top && `Why is ${top.name} ${top.risk}?`, planned && `Plan a Saturday volunteer route in ${planned.name}.`,
      'Which areas should we check first?'].filter(Boolean).slice(0, 4);
  }
  function compose(plan, results, question) {
    const sources = [], out = {paragraphs:[], actions:[], sources};
    const R = name => results.find(r => r.name === name);
    const C = (name, id) => cite(sources, R(name).sources.find(s => s.id === id) || R(name).sources[0]);
    if (plan.intent === 'area') {
      const a = R('get_area').result, g = R('cluster_growth').result, w = a.weather;
      const why = a.priority === 'High' ? `because <b>${people(a.people_in_clusters)}</b> are in <b>${a.cluster_count}</b> active ${a.cluster_count === 1 ? 'cluster' : 'clusters'} overlapping the area. High starts at 10 people.`
        : a.priority === 'Medium' ? `because it has <b>${a.cluster_count}</b> active ${a.cluster_count === 1 ? 'cluster' : 'clusters'} with <b>${people(a.people_in_clusters)}</b>, under the 10-person High line.`
        : `because no active cluster overlaps it in this snapshot. Low isn't the same as no risk, so routine checks still matter.`;
      out.paragraphs.push(`<b>${esc(a.name)}</b> is <b>${esc(a.priority)}</b> priority ${why}${C('get_area','clusters')}`);
      if (a.clusters.length) {
        const top = a.clusters[0], streets = top.locality.split(' / ').slice(0,2).join(' / ');
        out.paragraphs.push(`The largest is the <b>${num(top.people)}-person</b> cluster around ${esc(streets)}${top.shared_with.length ? `, which it shares with ${esc(top.shared_with.join(' and '))}` : ''}. NEA last updated it on ${date(top.updated)}.${C('get_area','clusters')}`);
      }
      const wx = [w.rain_mm && `${num(w.rain_mm.value,1)} mm rain`, w.temperature_c && `${num(w.temperature_c.value,1)}°C`, w.humidity_pct && `${num(w.humidity_pct.value,0)}% humidity`].filter(Boolean);
      if (wx.length) out.paragraphs.push(`Nearby stations recorded ${wx.join(', ')} on ${date(current().weather_date)}. Weather adds context but doesn't change the priority level.${C('get_area','weather')}`);
      out.paragraphs.push(g.history_available ? `${g.clusters.filter(c => /grow/i.test(c.status)).length} of these clusters grew since ${date(g.baseline_date)}.${C('cluster_growth','growth')}` : `It's too early to say whether these clusters are growing: growth needs two snapshots at least 7 days apart, and ${g.snapshots_saved} ${g.snapshots_saved === 1 ? 'is' : 'are'} saved so far.${C('cluster_growth','growth')}`);
      if (a.cluster_count) out.actions.push({label:`Plan a route in ${a.name}`, ask:`Plan a volunteer route in ${a.name}.`});
      out.actions.push({label:'Show on map', run:() => hooks.selectArea?.(a.code)});
    }
    if (plan.intent === 'route') {
      const a = R('get_area').result, p = R('inspection_plan').result, day = question.match(/\b(mon|tues|wednes|thurs|fri|satur|sun)day\b/i)?.[0];
      if (p.stops.length) {
        const km = p.distance_km, minutes = Math.round((km ? km/4.5*60 : 0) + p.stops.length*5);
        out.paragraphs.push(`${day ? `For a ${esc(day.charAt(0).toUpperCase()+day.slice(1).toLowerCase())} session in` : 'In'} <b>${esc(a.name)}</b>, walk these <b>${p.stops.length} places</b> in order${km ? ` along a <b>${num(km,1)} km</b> ${p.route_method === 'onemap_walk' ? 'walking route' : 'route'}` : ''}. Allow about <b>${minutes} minutes</b>, including roughly 5 minutes at each stop.${C('inspection_plan','inspection')}`);
        out.paragraphs.push(`<ol class="ask-list">${p.stops.map(s => `<li>${esc(s.name)}</li>`).join('')}</ol>`);
        const checklist = p.stops[0].checklist || [];
        if (checklist.length) out.paragraphs.push(`At each stop: ${checklist.map(c => esc(c.charAt(0).toLowerCase()+c.slice(1))).join('; ')}. These stops sit near the ${people(a.people_in_clusters)} in active clusters, but none is a confirmed breeding site.${C('inspection_plan','clusters')}`);
        if (p.unresolved_blocks) out.paragraphs.push(`${p.unresolved_blocks} listed ${p.unresolved_blocks === 1 ? 'block' : 'blocks'} couldn't be located, so a few nearby places may be missing.`);
        out.actions.push({label:'Open the full plan', run:() => hooks.openPlan?.(a.code)}, {label:'Draft a resident notice', run:() => hooks.openNotice?.(a.code)});
      } else {
        const near = nearestActive((current().areas || []).find(x => x.code === a.code) || {});
        out.paragraphs.push(`<b>${esc(a.name)}</b> has no active dengue cluster in the ${date(current().as_of)} snapshot, so there's no cluster-led route to plan there.${C('inspection_plan','clusters')}`);
        if (near.length) out.paragraphs.push(`The nearest areas with active clusters are ${near.map(({x,d}) => `<b>${esc(x.name)}</b> (${people(x.cluster_cases)}, about ${num(d,0)} km away)`).join(' and ')}.${C('inspection_plan','clusters')} A volunteer group could start there.`);
        out.paragraphs.push(`Around ${esc(a.name)}, a general sweep still helps: loosen hardened soil, empty flowerpot plates, overturn pails, change vase water and keep gutters clear.`);
        near.forEach(({x}) => out.actions.push({label:`Plan a route in ${x.name}`, ask:`Plan a volunteer route in ${x.name}.`}));
      }
    }
    if (plan.intent === 'forecast') {
      const f = R('forecast_replay').result, e = R('explain_forecast').result;
      if (f.error) { out.paragraphs.push("That week is outside the 2022 replay. Use Ask the data for a later historical week, or ask for the latest national outlook."); return out; }
      const isFirst = f.issue_date === f.first_high_issue;
      if (/peak/i.test(question)) out.paragraphs.push(`Reported cases peaked in the week of <b>${date(f.peak_week)}</b>, at <b>${people(f.peak_people)}</b>.${C('forecast_replay','bulletin')}`);
      out.paragraphs.push(`${isFirst ? 'The early warning came on' : 'The forecast issued on'} <b>${date(f.issue_date)}</b>${isFirst ? ', when the forecast' : ''} predicted <b>${people(Math.round(f.forecast))}</b> (${esc(f.level)}) for the week of ${date(f.target_week,{day:'numeric',month:'short'})}. The High line is ${num(f.high_threshold,0)}.${C('forecast_replay','forecast')}${isFirst ? ` That was <b>${num(f.weeks_before_peak)} weeks</b> before the ${date(f.peak_week,{day:'numeric',month:'short'})} peak of ${people(f.peak_people)}.` : ''}`);
      const parts = [...e.contributions].sort((x,y) => Math.abs(y.value)-Math.abs(x.value));
      const lead = parts[0], total = parts.reduce((s,c) => s+Math.abs(c.value), 0) || 1;
      const weatherShare = parts.filter(c => /rain|heat/i.test(c.feature)).reduce((s,c) => s+Math.abs(c.value), 0) / total;
      out.paragraphs.push(`What drove it, starting from a typical week of ${num(e.base_value,0)}: ${parts.map(c => `${esc(c.feature.toLowerCase())} <b>${c.value >= 0 ? '+' : '−'}${num(Math.abs(c.value),1)}</b>`).join(', ')}.${C('explain_forecast','forecast')}`);
      if (lead) out.paragraphs.push(lead.feature === 'Recent cases' ? `So the signal came mostly from recent cases: <b>${people(f.origin_week_cases)}</b> were reported in the week the forecast was made.${C('forecast_replay','bulletin')} ${weatherShare < .25 ? 'Weather played a small part.' : 'Weather also mattered.'} These are associations, not causes.` : `The largest factor was ${esc(lead.feature.toLowerCase())}. These contributions are associations, not causes.`);
      out.paragraphs.push(`${people(f.reported)} were actually reported that week; a simple four-week average would have said ${num(Math.round(f.simple_average))}.${C('forecast_replay','bulletin')}`);
      out.actions.push({label:'Show this week on the chart', run:() => hooks.showWeek?.(f.week_index)});
    }
    if (plan.intent === 'live') {
      const l = R('live_outlook').result;
      if (l.error) { out.paragraphs.push('A current national outlook is unavailable because the saved forecast is missing or out of date. Historical evaluation remains available.'); return out; }
      const n = l.typical, ratio = n ? l.forecast / Math.max(n.median, 1) : null;
      const versus = ratio == null ? '' : ratio < .8 ? 'lower than' : ratio > 1.25 ? 'higher than' : 'about the same as';
      out.paragraphs.push(`For the week of <b>${date(l.target_week,{day:'numeric',month:'long'})}</b>, expect about <b>${people(Math.round(l.forecast))}</b> nationally, likely between ${num(l.low,0)} and ${num(l.high,0)}.${C('live_outlook','live')}${n ? ` That’s ${versus} a typical week at this time of year (about ${num(n.median,0)} in ${esc(n.years)}).` : ''}`);
      out.paragraphs.push(`The latest official count is <b>${people(l.latest_people)}</b> for the week ending ${date(l.latest_week_end)}. The earlier unreported week of ${date(l.this_week?.target_date)} has a forecast of about ${num(Math.round(l.this_week?.prediction),0)}.${C('live_outlook','live')}`);
      if (l.test_weeks) out.paragraphs.push(`In a retrospective check of ${num(l.test_weeks,0)} weeks since 2023, the fixed recipe was off by about <b>${num(l.test_error,0)} people a week</b>, against ${num(l.test_simple_average_error,0)} for a simple average. Its 80% range held the real count in ${num(l.test_range_coverage*100,0)}% of weeks. Models were refitted yearly on earlier labels; this is not performance recorded in real time.${C('live_outlook','prospective')}`);
      if(l.imputed_weather.length)out.paragraphs.push(`Missing weather inputs: ${l.imputed_weather.map(r=>`${num(r.missing)} of ${num(r.total)} for the week of ${date(r.week)}`).join('; ')}. The estimator uses training-set medians internally; observations remain missing.${C('live_outlook','live')}`);
      out.paragraphs.push('Ranges describe past forecast error, not a guarantee.');
      const top = [...l.contributions].sort((x,y) => Math.abs(y.value)-Math.abs(x.value))[0];
      if (top) out.paragraphs.push(`The biggest influence was ${esc(top.feature.toLowerCase())}, ${top.value >= 0 ? 'pushing the outlook up' : 'pulling it down'}. These are associations, not causes.`);
      out.actions.push({label:'Open the forecast', run:() => hooks.showLive?.()}, {label:'Which areas should we check first?', ask:'Which areas should we check first?'});
    }
    if(plan.intent==='evaluation'){
      const e=R('forecast_evaluation').result;
      if(e.error){out.paragraphs.push('The 2023+ retrospective evaluation is unavailable.');return out;}
      out.paragraphs.push(`Across ${num(e.n)} weeks (${esc(e.window)}), average error was <b>${num(e.selected.mae,1)} people a week</b>, versus ${num(e.baseline.mae,1)} for the simple average. The 80% range contained the reported count in ${num(e.interval_coverage*100,1)}% of weeks.${C('forecast_evaluation','prospective')}`);
      out.paragraphs.push('This is a retrospective check of the fixed recipe, refitted yearly using earlier labels. It uses revised counts and assumed immediate publication, not performance recorded in real time.');
      if(e.weather_missingness)out.paragraphs.push(`${num(e.weather_missingness.share_of_weeks_with_imputed_weather_inputs*100,1)}% of these weeks used at least one imputed weather input inside the estimator; observations remain missing.${C('forecast_evaluation','prospective')}`);
      out.actions.push({label:'Open the forecast evaluation',run:()=>hooks.showLive?.()});
    }
    if (plan.intent === 'top') {
      const rows = R('top_areas').result;
      out.paragraphs.push(`Start with these ${rows.length} areas, ranked by people in active clusters:${C('top_areas','clusters')}`);
      out.paragraphs.push(`<ol class="ask-list">${rows.map(r => `<li><b>${esc(r.name)}</b> · ${esc(r.priority)} · ${people(r.people_in_clusters)} in ${r.cluster_count} ${r.cluster_count === 1 ? 'cluster' : 'clusters'}</li>`).join('')}</ol>`);
      out.paragraphs.push('A cluster that crosses a boundary counts in both areas, so these totals shouldn’t be added up.');
      if (rows[0]) out.actions.push({label:`Why is ${rows[0].name} ${rows[0].priority}?`, ask:`Why is ${rows[0].name} ${rows[0].priority}?`});
    }
    if (plan.intent === 'growth') {
      const g = R('cluster_growth').result;
      if (g.history_available) {
        const growing = g.clusters.filter(c => /grow/i.test(c.status));
        out.paragraphs.push(`${growing.length} of ${g.clusters.length} clusters${plan.area ? ` in ${esc(plan.area.name)}` : ''} grew since ${date(g.baseline_date)}.${C('cluster_growth','growth')}`);
        if (growing.length) out.paragraphs.push(`<ol class="ask-list">${growing.map(c => `<li>${esc(c.locality.split(' / ')[0])} · +${num(c.change)}</li>`).join('')}</ol>`);
      } else if (g.snapshot_changes) {
        const c = g.snapshot_changes, s = c.summary;
        out.paragraphs.push(`Between ${date(c.from_date)} and ${date(c.to_date)}, active clusters went from <b>${num(s.clusters_then)}</b> to <b>${num(s.clusters_now)}</b>: ${num(s.new)} new, ${num(s.growing)} growing and ${num(s.closed)} closed.${C('cluster_growth','growth')} People in clusters went from ${num(s.people_then)} to ${num(s.people_now)}; these are cumulative cluster sizes, not new weekly cases.`);
      } else {
        out.paragraphs.push(`Not yet. Growth compares two snapshots at least 7 days apart, and ${g.snapshots_saved} ${g.snapshots_saved === 1 ? 'snapshot is' : 'snapshots are'} saved so far (${date(data.growth?.as_of_date || current().as_of)}).${C('cluster_growth','growth')} The daily job keeps collecting, so this will fill in automatically.`);
        const biggest = [...g.clusters].sort((x,y) => y.people-x.people).slice(0,3);
        if (biggest.length) out.paragraphs.push(`For now, the largest ${biggest.length === 1 ? 'cluster' : 'clusters'}${plan.area ? ` in ${esc(plan.area.name)}` : ''} ${biggest.length === 1 ? 'is' : 'are'} ${biggest.map(c => `${esc(c.locality.split(' / ')[0])} (${people(c.people)})`).join(', ')}.${C('cluster_growth','growth')}`);
      }
    }
    if (plan.intent === 'help') {
      out.paragraphs.push('I can answer questions about area priorities, active clusters, inspection routes, the live national outlook and the 2022 replay, using the saved data. Try one of these:');
      suggestions().forEach(q => out.actions.push({label:q, ask:q}));
    }
    return out;
  }

  async function respond(question, onStep) {
    const plan = planCalls(question), results = [];
    for (const [name, args] of plan.calls) {
      onStep(name, args);
      results.push({name, args, ...tools[name](args)});
    }
    return {plan, results, answer:compose(plan, results, question)};
  }

  /* ---------- Ask the data: plain-English questions to SQL over the gold tables ---------- */
  const REGIONS = ['north-east','north','east','west','central'];
  const areaRows = () => areas().map(a => ({area_code:a.code, area_name:a.name, region:a.region, priority:a.risk, cluster_count:a.cluster_count, cluster_cases:a.cluster_cases}));
  const monthName = i => MONTHS[i].charAt(0).toUpperCase() + MONTHS[i].slice(1, 3);
  function sqlFor(question) {
    const t = question.toLowerCase(), n = Number(t.match(/\b(?:top|first)\s+(\d{1,2})\b/)?.[1] || 10);
    const more = Number(t.match(/(?:more than|over|above|at least|>=?)\s*(\d+)/)?.[1]);
    const region = REGIONS.find(r => t.includes(`${r} region`) || t.includes(r.replace('-', ' ')) && /region|areas? in/.test(t));
    if (/next week|coming|live|latest forecast|this week/.test(t)) return {
      table:'gold_national_predictions', summary:'Forecasts for weeks that have not been reported yet, with their 80% ranges.',
      sql:`SELECT target_date, round(prediction) AS forecast, round(lower) AS likely_low, round(upper) AS likely_high, normal_median AS typical_week\nFROM ${TABLE}.gold_national_predictions\nWHERE segment = 'live'\n  AND datediff(CAST(from_utc_timestamp(current_timestamp(), 'Asia/Singapore') AS DATE), CAST(origin_week_end AS DATE)) BETWEEN 0 AND 21\n  AND CAST(target_week_end AS DATE) >= CAST(from_utc_timestamp(current_timestamp(), 'Asia/Singapore') AS DATE)\nORDER BY target_date;`,
      run:() => (liveForecast()?.forecasts || []).map(r => ({target_date:r.target_date, forecast:Math.round(r.prediction), likely_low:Math.round(r.lower), likely_high:Math.round(r.upper), typical_week:r.normal?.median ?? null}))
    };
    if (/since 2023|2023|2024|2025|2026|by year|each year/.test(t) && /error|accura|off by|mae|well/.test(t)) return {
      table:'gold_national_predictions', summary:'Average weekly error in the 2023+ retrospective evaluation of the fixed recipe, refitted yearly using earlier labels.',
      sql:`SELECT year(target_date) AS year,\n       round(avg(abs(prediction - actual)), 1) AS forecast_error,\n       round(avg(abs(baseline - actual)), 1) AS simple_average_error\nFROM ${TABLE}.gold_national_predictions\nWHERE segment = 'prospective'\nGROUP BY year(target_date)\nORDER BY year;`,
      run:() => Object.entries(model().prospective?.by_year || {}).map(([year, v]) => ({year:+year, forecast_error:Math.round(v.selected.mae*10)/10, simple_average_error:Math.round(v.baseline.mae*10)/10}))
    };
    if (/error|accura|off by|mae/.test(t)) return {
      table:'gold_national_predictions', summary:'Average absolute weekly error of the forecast and the simple average, by month of 2022.',
      sql:`SELECT date_format(target_date, 'MMM') AS month,\n       round(avg(abs(prediction - actual)), 0) AS forecast_error,\n       round(avg(abs(baseline - actual)), 0) AS simple_average_error\nFROM ${TABLE}.gold_national_predictions\nWHERE segment = 'replay_2022'\nGROUP BY month(target_date), month\nORDER BY month(target_date);`,
      run:() => { const g = {}; predictions().forEach(r => { const m = new Date(`${r.target_date}T12:00:00`).getMonth(); (g[m] ||= []).push(r); }); return Object.entries(g).map(([m, rs]) => ({month:monthName(+m), forecast_error:Math.round(rs.reduce((s,r) => s+Math.abs((r.selected_prediction ?? r.prediction)-r.actual),0)/rs.length), simple_average_error:Math.round(rs.reduce((s,r) => s+Math.abs(r.baseline-r.actual),0)/rs.length)})); }
    };
    if (/week|forecast|predict|2022/.test(t) && /high/.test(t)) return {
      table:'gold_national_predictions', summary:'Weeks in 2022 where the two-week forecast was High.',
      sql:`SELECT issue_date, target_date, round(prediction) AS forecast, actual AS reported\nFROM ${TABLE}.gold_national_predictions\nWHERE segment = 'replay_2022' AND risk = 'High'\nORDER BY target_date;`,
      run:() => predictions().filter(r => r.risk === 'High').map(r => ({issue_date:r.issue_date, target_date:r.target_date, forecast:Math.round(r.selected_prediction ?? r.prediction), reported:r.actual}))
    };
    if (/peak|busiest|worst week|most cases/.test(t) && /week|2022/.test(t)) return {
      table:'gold_national_predictions', summary:'The five weeks of 2022 with the most reported people.',
      sql:`SELECT target_date, actual AS reported, round(prediction) AS forecast\nFROM ${TABLE}.gold_national_predictions\nWHERE segment = 'replay_2022'\nORDER BY actual DESC\nLIMIT 5;`,
      run:() => [...predictions()].sort((a,b) => b.actual-a.actual).slice(0,5).map(r => ({target_date:r.target_date, reported:r.actual, forecast:Math.round(r.selected_prediction ?? r.prediction)}))
    };
    if (/how many|count|breakdown|split/.test(t) && /priorit|high|medium|low|level/.test(t)) return {
      table:'gold_area_priorities', summary:'Planning areas by priority level.',
      sql:`SELECT priority, count(*) AS areas, sum(cluster_cases) AS people_in_clusters\nFROM ${TABLE}.gold_area_priorities\nGROUP BY priority\nORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END;`,
      run:() => ['High','Medium','Low'].map(p => { const rs = areaRows().filter(r => r.priority === p); return {priority:p, areas:rs.length, people_in_clusters:rs.reduce((s,r) => s+r.cluster_cases,0)}; })
    };
    if (/cluster/.test(t) && !/area/.test(t) || finite(more) && /cluster/.test(t)) return {
      table:'gold_cluster_growth', summary:finite(more) ? `Active clusters with more than ${more} people.` : 'Active clusters, largest first.',
      sql:`SELECT cluster_id, locality, case_size, classification\nFROM ${TABLE}.gold_cluster_growth\nWHERE as_of_date = (SELECT max(as_of_date) FROM ${TABLE}.gold_cluster_growth)${finite(more) ? `\n  AND case_size > ${more}` : ''}\nORDER BY case_size DESC;`,
      run:() => (current().clusters?.features || []).map(f => f.properties).filter(p => !finite(more) || p.cases > more).sort((a,b) => b.cases-a.cases).map(p => ({cluster_id:p.id, locality:p.name.split(' / ').slice(0,2).join(' / ') + (p.name.split(' / ').length > 2 ? ' …' : ''), case_size:p.cases, classification:p.growth_status || 'not_enough_history'}))
    };
    if (region) return {
      table:'gold_area_priorities', summary:`Planning areas in the ${region.replace(/\b\w/g, c => c.toUpperCase())} Region with active clusters.`,
      sql:`SELECT area_name, priority, cluster_count, cluster_cases\nFROM ${TABLE}.gold_area_priorities\nWHERE region = '${region.replace(/\b\w/g, c => c.toUpperCase())} Region'\n  AND cluster_count > 0\nORDER BY cluster_cases DESC;`,
      run:() => areaRows().filter(r => (r.region || '').toLowerCase() === `${region} region` && r.cluster_count > 0).map(({area_name, priority, cluster_count, cluster_cases}) => ({area_name, priority, cluster_count, cluster_cases}))
    };
    if (/area|where|top|rank|priorit|most/.test(t)) return {
      table:'gold_area_priorities', summary:`Top ${n} planning areas by people in active clusters.`,
      sql:`SELECT area_name, priority, cluster_count, cluster_cases\nFROM ${TABLE}.gold_area_priorities\nORDER BY cluster_cases DESC, cluster_count DESC\nLIMIT ${n};`,
      run:() => areaRows().slice(0, n).map(({area_name, priority, cluster_count, cluster_cases}) => ({area_name, priority, cluster_count, cluster_cases}))
    };
    return null;
  }
  const SQL_EXAMPLES = ['Forecast for next week', 'Forecast error by year since 2023', 'Top 10 areas by people in clusters', 'How many areas are High, Medium and Low?', 'Clusters with more than 3 people', 'Weeks in 2022 where the forecast was High', 'Monthly forecast error in 2022', 'Areas in the West Region with active clusters'];
  const highlightSql = sql => esc(sql).replace(/\b(SELECT|FROM|WHERE|AND|GROUP BY|ORDER BY|LIMIT|AS|DESC|CASE|WHEN|THEN|ELSE|END)\b/g, '<b>$1</b>').replace(/\b(count|sum|avg|abs|round|max|year|month|date_format)(?=\()/g, '<b>$1</b>');

  /* ---------- Cluster growth model status (Forecast lab) ---------- */
  function renderGrowthModel() {
    const view = $('#forecast-view'); if (!view || $('#growth-model')) return;
    const g = data.growth || {}, snapshots = g.snapshot_count ?? 1, target = 28, days = g.history_days ?? 0;
    const pct = Math.min(100, Math.round(days / target * 100));
    const section = document.createElement('section'); section.className = 'growth-model'; section.id = 'growth-model';
    section.innerHTML = `<div><h3>Area model: will a cluster grow next week?</h3><p>Will learn from the daily NEA cluster snapshots this pipeline is collecting, so areas can be ranked by likely growth instead of current size.</p></div>
      <div class="growth-model-status"><span class="growth-pill">${icon('circle-notch')} Collecting data</span><div class="growth-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${target}" aria-valuenow="${days}"><b style="width:${Math.max(pct, 3)}%"></b></div><small>${num(snapshots)} ${snapshots === 1 ? 'snapshot' : 'snapshots'} since ${date(g.as_of_date || current().as_of)} · first evaluation after ${target} days</small></div>`;
    view.append(section);
  }

  const ACTIONS = {select_area:a=>hooks.selectArea?.(a.area),open_plan:a=>hooks.openPlan?.(a.area),open_notice:a=>hooks.openNotice?.(a.area),show_week:a=>hooks.showWeek?.(a.week),show_live:()=>hooks.showLive?.()};
  function init(payload, callbacks) {
    data = payload; hooks = callbacks || {};
    window.ChatHome?.init(data, hooks, {respond, tools, sqlFor});
  }
  window.Assistant = {init, tools, respond, sqlFor};
})();
