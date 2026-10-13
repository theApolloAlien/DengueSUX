/* Field inspection: source-backed places to check. Never inferred breeding sites. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = n => `<i class="ph ph-${n}" aria-hidden="true"></i>`;
  const date = v => { if(!v)return 'Unavailable'; const raw=String(v);const text=/^\d{14}$/.test(raw)?`${raw.slice(0,4)}-${raw.slice(4,6)}-${raw.slice(6,8)}`:raw;const d=new Date(text.length===10?`${text}T12:00:00+08:00`:text);return Number.isNaN(+d)?raw:d.toLocaleDateString('en-SG',{day:'numeric',month:'short',year:'numeric'}); };
  const num = (n,d=0) => typeof n==='number' && Number.isFinite(n)?n.toLocaleString('en-SG',{maximumFractionDigits:d}):'—';
  const safeURL = v => {try{const u=new URL(v);return u.protocol==='https:'?esc(u.href):'#';}catch{return '#';}};
  const FOOTNOTE='Places to check, ranked by nearby cases and place type. Not confirmed breeding sites.';
  const REPORT_OPTIONS=[['water_found','Water found','drop'],['cleared','Tidied up','broom'],['nothing','Nothing','check']];
  const OUTCOME_TEXT={water_found:'Water found',cleared:'Tidied up',nothing:'Nothing found'};
  function markReport(box,row){box.querySelectorAll('[data-outcome]').forEach(b=>b.classList.toggle('active',b.dataset.outcome===row.outcome));box.querySelector('.report-status').textContent=`${OUTCOME_TEXT[row.outcome]} · ${date(String(row.reported_at).replace(' ','T')+'Z')}`;}
  let reportRequest=0;
  async function loadReports(area){
    if(window.DENGUESUX_DATA)return;
    const request=++reportRequest;
    try{const r=await fetch(`/api/reports?area_code=${encodeURIComponent(area.code)}`,{signal:AbortSignal.timeout(15000)});if(!r.ok||request!==reportRequest||selectedArea?.code!==area.code)return;const summary=await r.json();
      if(request!==reportRequest)return;  // A newer plan or save has asked again; never show an older summary.
      document.querySelectorAll('[data-report-stop]').forEach(box=>{const row=summary.by_stop?.[box.dataset.reportStop];if(row)markReport(box,row);});
      const note=$('#field-report-summary');if(note&&summary.reports){note.hidden=false;note.innerHTML=`${icon('clipboard-text')} <strong>${num(summary.stops_checked)}</strong> stops reported · ${num(summary.water_found)} with water found · last report ${esc(date(String(summary.last_reported_at).replace(' ','T')+'Z'))}`;}}catch{}
  }
  function bindReports(area,asOf){
    document.querySelectorAll('[data-report-stop]').forEach(box=>box.querySelectorAll('[data-outcome]').forEach(button=>button.addEventListener('click',async()=>{
      if(window.DENGUESUX_DATA){actions.toast('Reports are saved in the live app, not this offline copy.');return;}
      const buttons=[...box.querySelectorAll('[data-outcome]')];if(buttons.some(b=>b.disabled))return;
      buttons.forEach(b=>b.disabled=true);box.setAttribute('aria-busy','true');box.querySelector('.report-status').textContent='Saving…';
      try{const r=await fetch('/api/reports',{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(45000),body:JSON.stringify({area_code:area.code,stop_id:box.dataset.reportStop,stop_name:box.dataset.reportName,place_type:box.dataset.reportType,outcome:button.dataset.outcome,plan_as_of:asOf||null})});
        if(!r.ok)throw new Error();const saved=await r.json();markReport(box,{outcome:button.dataset.outcome,reported_at:saved.reported_at});actions.toast('Report saved. Thank you for checking.');loadReports(area);}
      catch{box.querySelector('.report-status').textContent='Not saved. Check your connection and try again.';}
      finally{buttons.forEach(b=>b.disabled=false);box.removeAttribute('aria-busy');}
    })));
  }
  let data={},actions={},map=null,plan=null,selectedArea=null,notice=null,language='en',noticeRequest=0,noticeVariant=0,noticeDraft='';
  let stopMarkers=new Map(),printFit=null;
  window.addEventListener('beforeprint',()=>printFit?.());
  window.addEventListener('afterprint',()=>{map?.invalidateSize({animate:false});});
  const growthRows=()=>Array.isArray(data.growth?.clusters)?data.growth.clusters:Object.values(data.growth?.clusters||{});
  const growthFor=id=>growthRows().find(c=>String(c.cluster_id??c.id)===String(id));
  const growthText=row=>row?.status_label||row?.classification||row?.status||'Not enough history yet';
  const growthBadge=row=>{let status=growthText(row);if(/insufficient|not_enough|unavailable/i.test(status))status='Not enough history yet';return `<span class="growth-badge ${/growing/i.test(status)?'is-growing':''}">${esc(status)}</span>`;};
  const clusterFeatures=code=>(data.current?.clusters?.features||[]).filter(f=>(f.properties.area_codes||[f.properties.area_code]).includes(code));
  function sourceLink(src){return `<a href="${safeURL(src.url||src.source_url)}" target="_blank" rel="noopener">${esc(src.name||src.layer||src.dataset_id||'Source')}${icon('arrow-up-right')}</a>${src.retrieved_at||src.retrieved_at_utc?`<span>Retrieved ${date(src.retrieved_at||src.retrieved_at_utc)}</span>`:''}`;}
  function download(text,name,type='text/plain;charset=utf-8'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function load(payload,callbacks){
    data=payload;actions=callbacks;
    if(!window.DENGUESUX_DATA){await Promise.all(['inspection','growth','notices'].filter(key=>!data[key]).map(async key=>{try{const r=await fetch(`/data/${key}.json`,{cache:'no-cache',signal:AbortSignal.timeout(12000)});if(r.ok)data[key]=await r.json();}catch{/* Existing dashboard remains usable without optional artifacts. */}}));}
    $('#close-notice').addEventListener('click',()=>$('#notice-dialog').close());
  }
  function areaActions(area){
    selectedArea=area;
    const box=document.createElement('section');box.className='field-actions';
    box.innerHTML=`<button class="solid-button plan-button">${icon('footprints')} Plan a check ${icon('arrow-up-right')}</button><button class="text-button notice-button">${icon('translate')} Draft resident notice</button>`;
    $('#area-detail .priority-summary').after(box);
    box.querySelector('.plan-button').addEventListener('click',()=>openPlan(area));
    box.querySelector('.notice-button').addEventListener('click',()=>openNotice(area));
    const clusters=clusterFeatures(area.code);
    const growthReady=data.growth?.history_available===true;
    const streets=name=>{const parts=String(name||'').split(' / ');return parts.length>2?`${esc(parts.slice(0,2).join(' / '))} <span class="more-streets">+${parts.length-2} more</span>`:esc(name);};
    if(clusters.length){const details=document.createElement('details');details.className='area-cluster-history';details.innerHTML=`<summary>${clusters.length} cluster${clusters.length===1?'':'s'}</summary>${clusters.map(f=>`<div title="${esc(f.properties.name)}"><strong>${num(f.properties.cases)} people</strong>${growthReady?growthBadge(growthFor(f.properties.id)):''}<p>${streets(f.properties.name)}</p><small>Updated ${date(f.properties.updated_at)}</small></div>`).join('')}`;box.after(details);}
  }
  function renderGrowth(){
    // Growth needs two snapshots at least 7 days apart; the card stays hidden until then.
    const g=data.growth||{};const ready=g.history_available===true && g.growing_count!=null;
    if(!ready)return;
    const row=$('#signals-view .stats-row');
    let stat=$('#growth-stat');if(!stat){stat=document.createElement('div');stat.id='growth-stat';stat.className='stat-item growth-stat';row.appendChild(stat);}
    stat.innerHTML=`<div class="stat-label">Clusters growing</div><div class="stat-value">${num(g.growing_count)}</div><p>vs ${date(g.baseline_date||g.baseline_date_sgt)}</p>`;
    // Use DOM-backed labels for existing map pins and list rows, without fabricating changes.
    document.querySelectorAll('.cluster-pin').forEach(pin=>{const label=pin.title||pin.getAttribute('aria-label')||'';const f=(data.current?.clusters?.features||[]).find(f=>label.includes(f.properties.name));if(f){const g=growthFor(f.properties.id);pin.title=`${label} · ${growthText(g)}`;}});
  }
  function componentStatus(value){return ({assumed_weight:'Assumed weight',observed_coordinates:'Verified coordinates',source_snapshot:'Dated source',not_enough_history:'Not enough history yet',unavailable_no_valid_area_join:'Unavailable · no valid area join'})[value]||String(value||'Observed').replaceAll('_',' ');}
  function formulaDetails(formula){if(!formula||typeof formula==='string')return '';return `<dl class="formula-rules"><div><dt>Place type · cap 25</dt><dd>Blocks 25 · hawker centres 20 · parks 15</dd></div>${['proximity','cluster_size','growth','elderly'].map(k=>`<div><dt>${esc(k.replaceAll('_',' '))} · cap ${formula[k]?.cap}</dt><dd>${esc(formula[k]?.expression)}</dd></div>`).join('')}</dl><p>${esc(formula.missing)} This score is not a disease probability or proof of stagnant water.</p>`;}
  function closePlan(){
    window.RouteFlythrough?.dispose();printFit=null;
    if(map){map.stop();map.remove();map=null;}$('#inspection-view').hidden=true;document.body.classList.remove('inspection-open');
    $('.page-heading').hidden=false;
  }
  // Every area has a saved 3D walk (output/web/walks/<CODE>.json): the cluster plan where NEA names exact blocks,
  // otherwise a routine walk through official places. Loaded only when a plan or the 3D view needs it.
  const walks=new Map();let planRequest=0;
  function loadWalk(code){
    if(window.DENGUESUX_DATA){if(!walks.has('*'))walks.set('*',window.DengueEmbedded?.json('walks-gz').catch(()=>null)||Promise.resolve(null));return walks.get('*').then(all=>all?.[code]||null);}
    if(!/^[A-Z]{2,3}$/.test(String(code)))return Promise.resolve(null);
    if(!walks.has(code))walks.set(code,fetch(`/data/walks/${code}.json`,{cache:'no-cache',signal:AbortSignal.timeout(15000)}).then(r=>r.ok?r.json():null).catch(()=>{walks.delete(code);return null;}));
    return walks.get(code);
  }
  function openPlan(area){
    if(window.Product?.ready&&!window.Product.openingPlan)return window.Product.go('plan',area.code);
    window.RouteFlythrough?.dispose();
    selectedArea=area;actions.open();
    if(map){map.stop();map.remove();map=null;}
    const inspection=data.inspection||{},clusterPlan=inspection.areas?.[area.code];
    const request=++planRequest;
    if(clusterPlan?.stops?.length)return renderPlan(area,clusterPlan,{kind:'cluster'});
    renderPlan(area,{area_code:area.code,area_name:area.name,status:'loading',stops:[],cluster_blocks:[],search_rings:[],clusters:{type:'FeatureCollection',features:clusterFeatures(area.code)}},{kind:'loading'});
    loadWalk(area.code).then(walk=>{
      if(request!==planRequest||selectedArea?.code!==area.code||$('#inspection-view').hidden)return;
      const fallback={area_code:area.code,area_name:area.name,status:clusterPlan?.status||'unavailable',message:clusterPlan?.message||'Verified places are unavailable for this saved snapshot.',stops:[],cluster_blocks:[],search_rings:[],clusters:{type:'FeatureCollection',features:clusterFeatures(area.code)}};
      if(!walk?.plan)return renderPlan(area,fallback,{kind:'empty'});
      // Today's cluster footprints come from the live snapshot, not from when the walk was saved.
      renderPlan(area,{...walk.plan,clusters:{type:'FeatureCollection',features:clusterFeatures(area.code)}},{kind:'walk',walk,clusterPlan,rerender:true});
    });
  }
  function walkBanner(area,plan,ctx){
    const features=clusterFeatures(area.code),snapshot=date(data.current?.as_of);
    const why=!plan.stops?.length?(features.length?`NEA’s ${snapshot} snapshot lists ${features.length===1?'a cluster':'clusters'} here (${esc(features.map(f=>f.properties.name).join('; '))}).`:`No active cluster here in NEA’s ${snapshot} snapshot.`)
      :plan.basis==='near_cluster'?`NEA’s ${snapshot} snapshot lists ${features.length===1?'a cluster':'clusters'} here (${esc(features.map(f=>f.properties.name).join('; '))}) without exact blocks, so this walk visits the official places nearest ${features.length===1?'its':'their'} footprint.`
      :features.length?`NEA’s ${snapshot} snapshot lists ${features.length===1?'a cluster':'clusters'} here, but no verified block could be located. This is a routine walk; check the cluster footprint on the map too.`
      :`No active cluster here in NEA’s ${snapshot} snapshot. A routine weekly walk keeps it that way.`;
    return `<div class="walk-banner">${icon(plan.basis==='near_cluster'?'warning-circle':'path')}<div><strong>${plan.basis==='near_cluster'?'Walk near the cluster':plan.stops?.length?'Routine walk':'No places to walk here'}</strong><p>${why} ${esc(plan.basis_note||'')}</p></div></div>`;
  }
  function renderPlan(area,current,ctx){
    plan=current;
    const inspection=data.inspection||{},walk=ctx.walk,isWalk=ctx.kind==='walk',loading=ctx.kind==='loading';
    const stops=plan.stops||[],radius=isWalk?(plan.radius_m||350):(inspection.radius_m||300),route=plan.route||{};
    // Show text that repeats across every stop once, not on each card.
    const same=key=>stops.length>1&&new Set(stops.map(s=>JSON.stringify(s[key]??null))).size===1;
    const opts={checklist:same('checklist')?stops[0].checklist||null:null,showScore:!same('score')};
    const sourceDates=[...new Set(clusterFeatures(area.code).map(f=>date(f.properties.updated_at)))];
    const toolbar=$('#inspection-view .plan-toolbar');
    $('#signals-view').hidden=true;$('#forecast-view').hidden=true;$('#inspection-view').hidden=false;
    $('.page-heading').hidden=true;document.body.classList.add('inspection-open');
    const formula=isWalk?walk.formula:inspection.formula,sources=isWalk?walk.sources:inspection.sources;
    const stale=isWalk?walk.map_data_stale:inspection.map_data_stale;
    const heading=loading?'Loading the walk…':stops.length?`${stops.length} stops to check`:plan.tour?'A 3D look at this area':'No verified stops yet';
    const legend=isWalk?`${clusterFeatures(area.code).length?'<span><b class="legend-footprint"></b>Cluster footprint</span>':''}<span><b class="legend-stop"></b>Walk stop</span><span><b class="legend-route"></b>${route.method==='onemap_walk'?'Walking route':'Approximate order'}</span>`
      :`<span><b class="legend-footprint"></b>Cluster footprint</span><span><b class="legend-radius"></b>${radius} m search</span><span><b class="legend-block"></b>Cluster block</span><span><b class="legend-route"></b>${route.method==='onemap_walk'?'Walking route':'Approximate order'}</span>`;
    const limits=isWalk?`<p>Up to ${stops.length||7} official places within about ${radius} m of the walk centre. Block pins sit inside each block’s official HDB footprint; hawker and park points are official source points, not verified entrances. Inspect only publicly accessible places; never enter homes or climb to gutters.</p><p>${esc(walk.landuse_note||'')}</p>`
      :`<p>Top ${inspection.top_n||8} available places; ${radius} m from exact cluster blocks. A place can be outside the selected area if it is near a shared cluster. Source points are approximate locations, not verified public entrances. Inspect only publicly accessible places; never enter homes or climb to gutters.</p>`;
    $('#inspection-view').innerHTML=`<div class="inspection-nav"><button id="back-to-areas" class="text-button">${icon('arrow-left')} Map</button><span>FIELD PLAN <span class="nav-step">/</span> ${esc(area.name)}</span><button id="print-plan" class="text-button" ${stops.length?'':'disabled'}>${icon('printer')} Print / save PDF</button></div>
      <header class="inspection-heading"><div><h1 tabindex="-1">${heading}<span>${esc(area.name)}${isWalk&&stops.length?' · routine walk':''}</span></h1></div><button class="outline-button" id="plan-notice">${icon('translate')} <span data-i18n="plan.notice">Resident notice</span></button></header>
      ${stops.length&&!window.DENGUESUX_DATA?`<div class="field-tools"><button type="button" class="outline-button" id="field-mode" aria-pressed="${document.body.classList.contains('field-mode')}">${icon('person-simple-walk')} <span data-i18n="plan.field">Field mode</span></button><button type="button" class="outline-button" id="claim-walk" hidden>${icon('hand-waving')} <span>Claim this walk</span></button><a class="text-button" id="reports-csv" href="/api/reports.csv?area_code=${esc(area.code)}" download>${icon('download-simple')} <span data-i18n="plan.csv">Export outcomes (CSV)</span></a><span class="claim-line" id="claim-line" hidden></span></div><div class="field-gps" id="field-gps" hidden></div>`:''}
      <div class="plan-evidence">${isWalk?`<span title="Walk saved from official HDB, NEA and NParks layers">${icon('calendar-dots')} Walk saved ${date(walk.generated_at)}</span><span title="NEA cluster snapshot">${icon('crosshair')} Clusters as of ${date(data.current?.as_of)}</span>`:`<span title="NEA source updated ${esc(sourceDates.join(' / ')||'unavailable')}">${icon('calendar-dots')} Saved ${date(inspection.as_of||data.current?.as_of)}</span><span title="Assumed search radius around each cluster block">${icon('circles-three')} ${radius} m radius</span>`}${plan.impact?`<span class="impact-chip" title="${esc(plan.impact.source)}. ${esc(plan.impact.note)}">${icon('house-line')} <strong>${num(plan.impact.homes_in_route_blocks)}</strong> homes on this route</span>`:''}</div>
      ${isWalk?walkBanner(area,plan,ctx):''}
      ${stale?`<div class="field-warning">${icon('cloud-warning')}<span title="${esc(inspection.stale_note||'Cached geocodes are being used because OneMap could not be refreshed.')}">Saved map data · check access on site.</span></div>`:''}
      <div class="inspection-layout"><div class="inspection-map-column"><section class="inspection-map-wrap" aria-label="Street level inspection map"><div id="inspection-map"></div><button id="fit-inspection" class="map-chip">${icon('arrows-out-simple')} Fit plan</button><div id="tile-warning" class="tile-warning" role="status" hidden>OneMap basemap is unavailable. Verified source locations remain visible; map data may be stale.</div></section><div class="inspection-legend">${legend}</div><p class="route-disclaimer">${route.method==='onemap_walk'?'OneMap walking route · check access on site.':stops.length>1?'Straight lines show order, not walkable paths. Check access on site.':''}</p>
      <details class="plan-sources"><summary>${icon('database')} Sources & limits</summary><div class="source-content"><h3>A transparent planning rule</h3><p>${esc(typeof formula==='string'?formula:formula?.expression||'Place type + proximity + cluster size + growth + elderly share. Each component is capped; unavailable inputs add no points.')}</p>${isWalk?walkFormula(formula):formulaDetails(formula)}${limits}<div class="source-links">${(sources||[]).map(sourceLink).join('')}</div>${isWalk?'':`<ul>${(inspection.layer_status||[]).map(x=>`<li><strong>${esc(x.name||x.layer||x.dataset_id)}</strong>: ${esc(x.reason||x.note||x.status)}</li>`).join('')}</ul>`}</div></details></div>
      <section class="inspection-stops" aria-labelledby="stops-heading" aria-busy="${loading}"><div class="stops-heading"><h2 id="stops-heading">${loading?'Loading…':stops.length?`${stops.length} places to check`:plan.tour?'No places to walk':'No verified stops yet'}</h2></div><p class="field-report-summary" id="field-report-summary" hidden></p><p class="stops-subtitle">${stops.length?`${route.method==='onemap_walk'&&route.distance_m?`${num(route.distance_m/1000,1)} km walking route`:'Approximate order'}`:loading?'':plan.tour?'The 3D view flies around instead.':'A route needs verified place locations.'}</p>${stops.length&&plan.unresolved_blocks?`<p class="coverage-note">${plan.unresolved_blocks} unlocated blocks; nearby stops may be missing.</p>`:''}${opts.checklist?`<div class="shared-checklist"><h3>At each stop</h3><ul>${opts.checklist.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div>`:''}${stops.length?'<div class="stop-progress"><span id="stop-progress-label" role="status"></span><progress id="stop-progress" aria-label="Inspection checklist progress" max="1" value="0"></progress></div>':''}<ol class="stop-list">${loading?'<li class="inspection-stop skeleton" style="height:120px"></li><li class="inspection-stop skeleton" style="height:120px"></li>':stops.map(s=>renderStop(s,opts)).join('')}</ol>${stops.length||loading?'':`<div class="inspection-empty"><img class="spot" src="/brand/no-clusters.png" width="112" height="112" alt=""><h3>${plan.tour?'No official place to check here':plan.status==='no_active_clusters'?'No active cluster in this area':'Exact block locations are unavailable'}</h3><p>${esc(plan.message||'No verified places match this saved snapshot.')}</p><p>${plan.tour?'Open the 3D view for a flyover of the area. ':''}Keep checking for standing water each week.</p></div>`}<p class="inspection-footnote">${esc(plan.footnote||FOOTNOTE)}</p></section></div>`;
    if(toolbar)$('#inspection-view').prepend(toolbar);
    $('#back-to-areas').addEventListener('click',()=>{closePlan();actions.back();$('#area-detail .plan-button')?.focus();});
    $('#print-plan').addEventListener('click',()=>window.print());$('#plan-notice').addEventListener('click',()=>openNotice(area));
    if($('#field-mode')){$('#field-mode').onclick=()=>fieldMode(area,!document.body.classList.contains('field-mode'));if(document.body.classList.contains('field-mode'))fieldMode(area,true);}
    if(!loading)loadClaim(area);window.I18N?.apply();
    $('.stop-list').querySelectorAll('[data-stop]').forEach(b=>b.addEventListener('click',()=>focusStop(b.dataset.stop)));
    const asOf=isWalk?walk.generated_at:inspection.as_of;
    $('.stop-list').querySelectorAll('input[type=checkbox]').forEach(c=>c.addEventListener('change',()=>{const key=`denguesux-check:${asOf}:${area.code}:${c.dataset.check}`;try{sessionStorage.setItem(key,String(c.checked));}catch{}updateProgress();}));
    $('.stop-list').querySelectorAll('input[type=checkbox]').forEach(c=>{try{c.checked=sessionStorage.getItem(`denguesux-check:${asOf}:${area.code}:${c.dataset.check}`)==='true';}catch{}});
    if(!loading){bindReports(area,asOf);loadReports(area);}
    updateProgress();renderPlanMap();window.Checklist3D?.decorate($('#inspection-view'));
    // An area with no official place, HDB block or mapped building (Tuas, the islands) has no 3D scene; say so instead of a blank plane.
    const noScene=isWalk&&!stops.length&&!(walk?.buildings?.features?.length);
    if(noScene)$('.inspection-map-column')?.insertAdjacentHTML('afterbegin',`<p class="no-scene-note">${icon('cube')} Nothing to show in 3D here: no official HDB block, hawker centre, park or mapped building lies in ${esc(area.name)}. The map shows the area outline.</p>`);
    if(!loading&&!noScene)window.RouteFlythrough?.mount(plan,area,id=>focusStop(id,true),{buildings:isWalk?walk.buildings:null,margin:isWalk?walk.method?.context_margin_m:null,loadWalk,onMode:mode=>{if(mode==='2d')requestAnimationFrame(()=>map?.invalidateSize());},
      // On desktop the plan opens in 3D: it is the clearest picture of the route. Phones, print and reduced motion stay 2D.
      start3d:(matchMedia('(min-width: 1000px)').matches||!!window.RouteFlythrough?.force3d)&&!matchMedia('(prefers-reduced-motion: reduce)').matches&&!!window.Checklist3D?.supported(),outline:isWalk?(data.current?.boundaries?.features||[]).find(f=>f.properties?.code===area.code)||null:null});
    if(!ctx.rerender)$('#inspection-view').scrollIntoView({block:'start',behavior:'instant'});
    if(!ctx.rerender||document.activeElement===document.body)$('.inspection-heading h1').focus({preventScroll:true});
  }
  function walkFormula(formula){if(!formula||typeof formula==='string')return '';return `<dl class="formula-rules"><div><dt>Place type · cap 25</dt><dd>Blocks 25 · hawker centres 20 · parks 15</dd></div>${['compactness','homes'].map(k=>`<div><dt>${k==='homes'?'Homes nearby':'Compactness'} · cap ${formula[k]?.cap}</dt><dd>${esc(formula[k]?.expression)}</dd></div>`).join('')}</dl><p>${esc(formula.missing)} This order is not a disease probability or proof of stagnant water.</p>`;}
  // Field mode: large targets, the screen stays awake, and the distance from this phone to the next unchecked stop
  // (computed on the device from the browser's position; never sent anywhere).
  let gpsWatch=null,wakeLock=null;
  async function fieldMode(area,on){
    document.body.classList.toggle('field-mode',on);$('#field-mode')?.setAttribute('aria-pressed',String(on));try{sessionStorage.setItem('denguesux:field',on?'1':'');}catch{}
    const gps=$('#field-gps');
    if(!on){if(gpsWatch!=null)navigator.geolocation?.clearWatch(gpsWatch);gpsWatch=null;try{wakeLock?.release();}catch{}wakeLock=null;if(gps)gps.hidden=true;return;}
    try{wakeLock=await navigator.wakeLock?.request('screen');}catch{}
    if(!gps||!navigator.geolocation)return;gps.hidden=false;gps.innerHTML=`${icon('crosshair-simple')} <span>${esc(window.I18N?window.I18N.t('plan.gps'):'Show my distance to the next stop')}</span><small>Location stays on this phone</small>`;
    gpsWatch=navigator.geolocation.watchPosition(pos=>{
      const stops=plan?.stops||[],next=stops.find(s=>{const c=document.querySelector(`.stop-done input[data-check="${CSS.escape(String(s.id))}:done"], #stop-${CSS.escape(String(s.id))} .stop-done input`);return !(c&&c.checked);})||stops[0];if(!next)return;
      const d=distanceM([pos.coords.longitude,pos.coords.latitude],[next.longitude,next.latitude]);
      gps.innerHTML=`${icon('crosshair-simple')} <span>${esc(window.I18N?window.I18N.t('plan.toNext',Math.round(d),next.number):`${Math.round(d)} m to stop ${next.number}`)}</span><small>${esc(next.name)} · ±${Math.round(pos.coords.accuracy||0)} m</small>`;
    },()=>{gps.innerHTML=`${icon('crosshair-simple')} <span>Location unavailable</span><small>Allow location to see the distance to the next stop</small>`;},{enableHighAccuracy:true,maximumAge:5000});
  }
  const distanceM=(a,b)=>{const lat=(a[1]+b[1])*Math.PI/360;return Math.hypot((a[0]-b[0])*Math.cos(lat),a[1]-b[1])*111195;};
  // Team mode: who claimed this area's walk for the week.
  async function loadClaim(area){
    const line=$('#claim-line'),button=$('#claim-walk');if(!line||!button)return;
    try{const r=await fetch('/api/claims',{signal:AbortSignal.timeout(12000)});if(!r.ok)throw 0;const c=await r.json();
      const mine=(c.claims||[]).filter(x=>x.area_code===area.code),claim=mine[0],me=c.me;
      const t=(k,...a)=>window.I18N?window.I18N.t(k,...a):k;
      button.hidden=false;line.hidden=!claim;if(claim)line.innerHTML=`${icon('hand-waving')} ${esc(t('plan.claimedBy',claim.claimed_by+(claim.claimed_by===me?' (me)':'')))}`;
      const release=!!claim&&(claim.claimed_by===me||me==null);
      button.querySelector('span').textContent=release?t('plan.release'):t('plan.claim');
      button.onclick=async()=>{button.disabled=true;try{await fetch('/api/claims',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({area_code:area.code,release})});actions.toast(release?'Walk released.':'Walk claimed for this week.');await loadClaim(area);}catch{actions.toast('Could not save the claim.');}finally{button.disabled=false;}};
    }catch{button.hidden=true;line.hidden=true;}
  }
  function updateProgress(){
    const checks=[...document.querySelectorAll('.stop-list input[type=checkbox]')];
    const meter=$('#stop-progress');if(!meter)return;
    const done=checks.filter(c=>c.checked).length,total=checks.length;
    const unit=$('.stop-done')?'stops':'checks';
    $('#stop-progress-label').textContent=total&&done===total?'Checklist complete · thank you for checking':`${done} of ${total} ${unit} complete`;
    let ring=$('.progress-ring');if(!ring){meter.insertAdjacentHTML('beforebegin','<svg class="progress-ring" viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="12"/><circle cx="14" cy="14" r="12"/></svg>');ring=$('.progress-ring');}ring.lastElementChild.style.strokeDashoffset=76*(1-done/(total||1));
    meter.max=total||1;meter.value=done;meter.parentElement.classList.toggle('complete',total>0&&done===total);
  }
  function renderStop(s,opts={}){
    const types={hdb:'building',hdb_block:'building',block:'building',park:'tree',parks:'tree',hawker:'storefront',hawker_centre:'storefront'};
    const components=Array.isArray(s.components)?s.components:Object.entries(s.components||{}).map(([key,v])=>typeof v==='object'?{key,...v}:{key,label:key,contribution:v});
    const checklist=opts.checklist?'':`<fieldset class="stop-checklist"><legend>Look for stagnant water in</legend>${(s.checklist||[]).map((item,i)=>`<label><input type="checkbox" data-check="${esc(s.id)}:${i}"><span>${esc(item)}</span></label>`).join('')}</fieldset>`;
    return `<li class="inspection-stop compact-stop" id="stop-${esc(s.id)}"><div class="stop-top"><button class="stop-number" data-stop="${esc(s.id)}" aria-label="Show stop ${num(s.number)} on map" title="Priority #${num(s.rank??s.number)}">${num(s.number)}</button><div><h3>${esc(s.name)}</h3><span class="place-type">${s.max_floor_lvl?`${num(s.max_floor_lvl)} storeys`:esc(String(s.place_type||'place').replaceAll('_',' '))}</span></div>${opts.showScore?`<strong class="stop-score">${num(s.score,1)}<small>/ 100</small></strong>`:''}${opts.checklist?`<label class="stop-done"><input type="checkbox" data-check="${esc(s.id)}:done"><span>Done</span></label>`:''}</div>${checklist}<details class="stop-report" data-report-stop="${esc(s.id)}" data-report-name="${esc(s.name)}" data-report-type="${esc(s.place_type||'place')}"><summary>Report</summary>${REPORT_OPTIONS.map(([key,label,ic])=>`<button type="button" data-outcome="${key}">${icon(ic)} ${label}</button>`).join('')}<small class="report-status" role="status"></small></details><div class="stop-foot"><details class="score-details"><summary>Why ${icon('caret-down')}</summary><p>${esc(String(s.place_type||'place').replaceAll('_',' '))}${s.dwelling_units?` · ${num(s.dwelling_units)} homes`:''}</p><p class="stop-reason">${esc(s.reason||'Reason unavailable — exclude this stop before inspection.')}</p><dl>${components.map(c=>`<div><dt>${esc(c.label||c.key)}<small>${esc(componentStatus(c.status))}${c.value!=null?` · ${typeof c.value==='number'?num(c.value,2):esc(c.value)}${c.unit?` ${esc(c.unit)}`:''}`:''}</small></dt><dd>${num(c.contribution??c.points,1)}${c.cap!=null?` <span>/ ${c.cap}</span>`:''}</dd></div>`).join('')}</dl><p>Planning points, not a disease probability. Missing inputs contribute no points.</p><p>As of ${date(s.as_of||data.inspection?.as_of)}. ${(s.sources||[]).map(src=>typeof src==='string'?esc(src):sourceLink(src)).join(' · ')}</p></details><a class="stop-map-link" href="https://www.google.com/maps/search/?api=1&query=${Number(s.latitude)},${Number(s.longitude)}" target="_blank" rel="noopener">Map ${icon('arrow-up-right')}</a></div><span class="print-coordinates">${Number(s.latitude).toFixed(6)}, ${Number(s.longitude).toFixed(6)}</span></li>`;
  }
  function printRoute(){
    const stops=plan.stops||[],geometry=plan.route?.geometry;
    const lines=geometry?.type==='LineString'?[geometry.coordinates]:geometry?.type==='MultiLineString'?geometry.coordinates:[];
    const points=[...lines.flat(),...stops.map(s=>[s.longitude,s.latitude])].filter(p=>p.every(Number.isFinite));if(!points.length)return '';
    const xs=points.map(p=>p[0]*Math.cos(1.35*Math.PI/180)),ys=points.map(p=>p[1]),minX=Math.min(...xs),maxY=Math.max(...ys),dx=Math.max(...xs)-minX,dy=maxY-Math.min(...ys),scale=Math.min(640/(dx||1),200/(dy||1));
    const project=p=>[40+(640-dx*scale)/2+(p[0]*Math.cos(1.35*Math.PI/180)-minX)*scale,28+(200-dy*scale)/2+(maxY-p[1])*scale];
    return `<svg class="print-route" viewBox="0 0 720 260" role="img" aria-label="Saved route and all numbered stops, north up"><rect width="720" height="260" fill="#f7f8f4"/>${lines.map(line=>`<polyline points="${line.map(p=>project(p).join(',')).join(' ')}" fill="none" stroke="#193e33" stroke-width="2"/>`).join('')}${stops.map(s=>{const [x,y]=project([s.longitude,s.latitude]);return `<circle cx="${x}" cy="${y}" r="9" fill="#193e33" stroke="white" stroke-width="2"/><text x="${x}" y="${y+3}" fill="white" text-anchor="middle" font-size="9" font-family="sans-serif">${num(s.number)}</text>`;}).join('')}<text x="18" y="20" fill="#193e33" font-size="11" font-family="sans-serif">North up</text><text x="18" y="248" fill="#52645a" font-size="10" font-family="sans-serif">${plan.route?.method==='onemap_walk'?'Saved OneMap walking geometry':'Verified stop locations'} - check local access</text></svg>`;
  }
  function renderPlanMap(){
    $('.inspection-map-column').insertAdjacentHTML('afterbegin',printRoute());
    stopMarkers=new Map();map=L.map('inspection-map',{zoomAnimation:false,fadeAnimation:false,minZoom:11,maxZoom:20,scrollWheelZoom:false,zoomControl:false,zoomSnap:.25,zoomDelta:.5}).setView(selectedArea.centroid||[1.35,103.82],15);L.control.zoom({position:'bottomright'}).addTo(map);map.attributionControl.setPrefix(false);
    const tiles=L.tileLayer('https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png',{maxZoom:20,minZoom:11,attribution:'<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener">OneMap</a> © Singapore Land Authority · NEA / data.gov.sg'}).addTo(map);
    tiles.on('tileerror',()=>{$('#tile-warning').hidden=false;});
    const bounds=L.featureGroup().addTo(map);
    const visitBounds=L.latLngBounds((plan.stops||[]).map(s=>[s.latitude,s.longitude]));
    const clusterLayer=L.geoJSON(plan.clusters||{type:'FeatureCollection',features:clusterFeatures(selectedArea.code)},{style:{color:'#b5412d',weight:1.5,fillColor:'#d65239',fillOpacity:.12},onEachFeature:(f,l)=>{const p=f.properties||{};l.bindPopup(`<strong>${num(p.cases??p.CASE_SIZE)} people associated with this cluster</strong><br>${esc(p.name||p.LOCALITY)}<br>${growthBadge(growthFor(p.id||p.OBJECTID))}<br><small>Cluster footprint, not a confirmed breeding location.</small>`);}}).addTo(map);
    if(!(plan.cluster_blocks||[]).length)bounds.addLayer(clusterLayer);
    // With nothing to walk, outline the planning area itself so the map is never an empty street grid.
    const outline=!(plan.stops||[]).length&&(data.current?.boundaries?.features||[]).find(f=>f.properties?.code===selectedArea.code);
    if(outline)L.geoJSON(outline,{style:{color:'#163f35',weight:2,dashArray:'6 6',fill:false},interactive:false}).addTo(bounds);
    (plan.search_rings||[]).forEach(r=>L.circle([r.latitude,r.longitude],{radius:r.radius_m||data.inspection.radius_m,color:'#5c8c73',weight:1,dashArray:'4 5',fillColor:'#91b89b',fillOpacity:.035,interactive:false}).addTo(bounds));
    (plan.cluster_blocks||[]).forEach(b=>L.circleMarker([b.latitude,b.longitude],{radius:4,color:'#b5412d',weight:2,fillColor:'#fff',fillOpacity:1}).bindPopup(`<strong>Cluster block ${esc(b.block)}</strong><br>${esc(b.street)}<br><small>OneMap geocode · retrieved ${date(b.retrieved_at)}</small>`).addTo(bounds));
    if(plan.route?.geometry)L.geoJSON(plan.route.geometry,{style:{color:'#163f35',weight:3,opacity:.8,dashArray:plan.route.method==='onemap_walk'?null:'7 7'}}).addTo(bounds);
    (plan.stops||[]).forEach(s=>{const marker=L.marker([s.latitude,s.longitude],{icon:L.divIcon({className:'inspection-pin',html:esc(s.number),iconSize:[32,32],iconAnchor:[16,16]}),title:`Stop ${s.number}: ${s.name}`}).bindPopup(`<strong>${num(s.number)}. ${esc(s.name)}</strong><br>${esc(s.reason)}`).addTo(bounds);marker.on('click',()=>{$(`#stop-${CSS.escape(String(s.id))}`)?.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});});stopMarkers.set(String(s.id),marker);});
    const fit=()=>{if(bounds.getBounds().isValid())map.fitBounds(bounds.getBounds(),{padding:[30,30],maxZoom:17});else if(selectedArea.centroid)map.setView(selectedArea.centroid,15);else map.setView([1.35,103.82],12);};
    if(visitBounds.isValid())map.fitBounds(visitBounds,{padding:[55,55],maxZoom:17.5});else fit();
    printFit=()=>{if(!map)return;map.invalidateSize({animate:false});if(visitBounds.isValid())map.fitBounds(visitBounds,{padding:[25,25],maxZoom:17.5,animate:false});};
    $('#fit-inspection').addEventListener('click',fit);requestAnimationFrame(()=>map?.invalidateSize());
  }
  function focusStop(id,fromTour=false){
    document.querySelectorAll('.inspection-stop').forEach(card=>{const selected=card.id==='stop-'+id;card.classList.toggle('is-tour-selected',selected);const button=card.querySelector('.stop-number');if(selected)button?.setAttribute('aria-current','step');else button?.removeAttribute('aria-current');});
    if(fromTour||window.RouteFlythrough?.focusStop(id))return;
    const marker=stopMarkers.get(String(id));if(marker){map.setView(marker.getLatLng(),18);marker.openPopup();if(matchMedia('(max-width:720px)').matches)$('#inspection-map').scrollIntoView({block:'center'});}
  }
  async function openNotice(area,requestedLanguage='en'){
    selectedArea=area;language=['en','zh','ms','ta'].includes(requestedLanguage)?requestedLanguage:'en';noticeVariant=0;$('#notice-title').textContent=`A note for ${area.name}`;$('#notice-dialog').showModal();await showNotice();
  }
  function savedNotice(code,lang){const n=data.notices||{};return n.areas?.[code]?.[lang]||n.notices?.[code]?.[lang]||n[code]?.[lang]||null;}
  async function showNotice(){
    const req=++noticeRequest,code=selectedArea.code,lang=language;
    const finishLoad=window.Product?.busy($('#plan-notice'));
    $('#notice-content').innerHTML='<div class="notice-loading" aria-busy="true"><span class="skeleton" style="width:100%;height:150px"></span><span class="sr-only">Loading saved notice</span></div>';
    let result=savedNotice(code,lang);
    if(!window.DENGUESUX_DATA){try{const r=await fetch(`/api/notices/${encodeURIComponent(code)}?language=${encodeURIComponent(lang)}`,{signal:AbortSignal.timeout(15000)});if(r.ok)result=await r.json();}catch{}}
    finishLoad?.();if(req!==noticeRequest)return;
    notice=result;
    const facts=result?.source_facts||result?.facts;
    const languages=[['en','English'],['zh','中文'],['ms','Bahasa Melayu'],['ta','தமிழ்']];
    $('#notice-content').innerHTML=`<p class="notice-label">${icon('pencil-simple')} Draft: review before sending</p><div class="notice-tabs" role="group" aria-label="Notice language">${languages.map(([id,label])=>`<button data-language="${id}" aria-pressed="${id===lang}" class="${id===lang?'active':''}" lang="${id}">${label}</button>`).join('')}</div>${result?`<div class="notice-text" id="notice-text" lang="${lang}"></div><details class="notice-checks" id="notice-checks"></details><div class="notice-tools"><button id="copy-notice" class="solid-button">${icon('copy')} Copy notice</button><button id="download-notice" class="outline-button">${icon('download-simple')} Download</button>${lang==='en'&&facts?`<button id="rewrite-notice" class="text-button">${icon('arrows-clockwise')} Rewrite</button>`:''}</div><details class="notice-facts"><summary><h3>Sources used</h3>${icon('caret-down')}</summary>${renderFacts(result.source_facts||result.facts)}<p>Area totals may share clusters. Counts are from the dated snapshot, not new cases this week.</p><a href="https://www.nea.gov.sg/dengue-zika/stop-dengue-now" target="_blank" rel="noopener">NEA Mozzie Wipeout ${icon('arrow-up-right')}</a></details>`:'<div class="inspection-empty"><h3>Notice facts are unavailable</h3><p>No saved notice is available for this area.</p></div>'}`;
    $('#notice-content').querySelectorAll('[data-language]').forEach(b=>b.addEventListener('click',()=>{language=b.dataset.language;showNotice();}));
    if(result){noticeDraft=lang==='en'&&facts?writeNotice(facts,noticeVariant):noticeText(result,lang);typeNotice(noticeDraft);renderChecks(checkNotice(noticeDraft,facts,lang),lang);
      $('#rewrite-notice')?.addEventListener('click',()=>{noticeVariant++;noticeDraft=writeNotice(facts,noticeVariant);typeNotice(noticeDraft);renderChecks(checkNotice(noticeDraft,facts,lang),lang);});
      $('#copy-notice').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(noticeExport());actions.toast('Draft copied. Review before sending.');}catch{actions.toast('Copy is unavailable here. Use Download instead.');}});$('#download-notice').addEventListener('click',()=>download(noticeExport(),`denguesux-${selectedArea.code}-${lang}-draft.txt`));}
  }
  function renderFacts(facts){
    if(!facts)return '<p>No source facts supplied.</p>';
    const rows=[['Planning area',facts.area_name],['Snapshot saved',date(facts.source_retrieved_at||facts.snapshot_date)],['Active clusters',facts.cluster_count],['People in clusters',facts.cluster_cases],['NEA guidance checked',date(facts.prevention_guidance_checked)]];
    return `<dl>${rows.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl><div class="source-links">${(facts.sources||[]).map(sourceLink).join('')}</div>`;
  }
  // English drafts use the same date format as the rest of the app; other languages keep the source text.
  function noticeText(n,lang){const text=n.text||n.notice||'Notice text unavailable.';return lang==='en'?text.replace(/\b\d{4}-\d{2}-\d{2}\b/g,d=>date(d)):text;}
  // Writes a fluent English draft from the dated facts; every number, date and NEA step is checked below.
  function writeNotice(f,variant){
    const area=f.area_name,day=date(f.snapshot_date),n=f.cluster_count,clusters=`${n} active dengue ${n===1?'cluster':'clusters'}`;
    const steps='loosen hardened soil, empty flowerpot plates, overturn pails and wipe their rims, replace the water in vases, and keep roof gutters clear, applying BTI as directed';
    const limit='These are places to check, not confirmed breeding sites.';
    const drafts=n?[`Dear ${area} residents, NEA’s snapshot of ${day} shows ${clusters} overlapping our area. A few minutes a week can stop mosquitoes breeding at home: ${steps}. ${limit} Thank you for doing your part.`,
      `${area} neighbours: as of ${day}, NEA reports ${clusters} around us. Please take a few minutes this week to ${steps}. ${limit}`,
      `A quick note for ${area}: NEA’s ${day} snapshot lists ${clusters} in our area, and small checks help most. Please ${steps}. ${limit}`]
      :[`Dear ${area} residents, NEA’s snapshot of ${day} shows no active dengue cluster in our area. Weekly checks help keep it that way: ${steps}. ${limit}`,
      `${area} neighbours: NEA’s ${day} snapshot has no active dengue clusters here. Please keep up weekly checks: ${steps}. ${limit}`];
    return drafts[variant%drafts.length];
  }
  const STEP_PATTERNS=[/hardened soil/i,/flowerpot plates?/i,/pails?/i,/vases?/i,/gutters?/i];
  function checkNotice(text,f,lang){
    if(!f)return [];
    const en=lang==='en',iso=String(f.snapshot_date||'');
    const allowed=new Set([f.cluster_count,f.cluster_cases,...iso.split('-')].map(v=>String(Number(v))));
    const numbers=(text.match(/\d+/g)||[]).map(v=>String(Number(v)));
    const steps=en?STEP_PATTERNS.every(r=>r.test(text)):(f.prevention_steps?.[lang]||[]).every(step=>text.includes(step.replace(/[.。]$/,'')));
    return [['Every number matches the source facts',numbers.every(v=>allowed.has(v))],
      ['Snapshot date matches',text.includes(en?date(iso):iso)],
      ['All five NEA prevention steps included',steps],
      ['No fogging or confirmed-breeding claims',!/fogging|熏雾|pengasapan/i.test(text)&&(!en||!/(?<!not )confirmed breeding/i.test(text))],
      [lang==='zh'?'Under 350 characters':'Under 80 words',lang==='zh'?text.length<=350:text.split(/\s+/).length<=80]];
  }
  function renderChecks(checks,lang){
    const box=$('#notice-checks');if(!box)return;
    if(!checks.length){box.hidden=true;return;}
    const passed=checks.filter(([,ok])=>ok).length;
    box.className=`notice-checks ${passed===checks.length?'is-pass':'is-fail'}`;
    box.innerHTML=`<summary>${icon(passed===checks.length?'check-circle':'warning-circle')} ${passed}/${checks.length} automatic checks passed ${icon('caret-down')}</summary><ul>${checks.map(([label,ok])=>`<li class="${ok?'':'failed'}">${icon(ok?'check':'x')} ${esc(label)}</li>`).join('')}</ul>`;
    $('#copy-notice').disabled=passed!==checks.length;
  }
  function typeNotice(text){const box=$('#notice-text');if(box){box.textContent=text;box.dataset.draft=text;}}
  function noticeExport(){return `Draft: review before sending\n\n${noticeDraft||noticeText(notice,language)}\n\nSource facts\n${JSON.stringify(notice.source_facts||notice.facts,null,2)}\nNEA: https://www.nea.gov.sg/dengue-zika/stop-dengue-now\n`;}
  window.Fieldwork={load,areaActions,renderGrowth,openPlan,closePlan,openNotice,growthFor,growthBadge,loadWalk};
})();
