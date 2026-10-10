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
  async function loadReports(area){
    if(window.DENGUESUX_DATA)return;
    try{const r=await fetch(`/api/reports?area_code=${encodeURIComponent(area.code)}`,{signal:AbortSignal.timeout(15000)});if(!r.ok)return;const summary=await r.json();
      document.querySelectorAll('[data-report-stop]').forEach(box=>{const row=summary.by_stop?.[box.dataset.reportStop];if(row)markReport(box,row);});
      const note=$('#field-report-summary');if(note&&summary.reports){note.hidden=false;note.innerHTML=`${icon('clipboard-text')} <strong>${num(summary.stops_checked)}</strong> stops reported · ${num(summary.water_found)} with water found · last report ${date(String(summary.last_reported_at).replace(' ','T')+'Z')}`;}}catch{}
  }
  function bindReports(area,asOf){
    document.querySelectorAll('[data-report-stop]').forEach(box=>box.querySelectorAll('[data-outcome]').forEach(button=>button.addEventListener('click',async()=>{
      if(window.DENGUESUX_DATA){actions.toast('Reports are saved in the live app, not this offline copy.');return;}
      box.querySelector('.report-status').textContent='Saving…';
      try{const r=await fetch('/api/reports',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({area_code:area.code,stop_id:box.dataset.reportStop,stop_name:box.dataset.reportName,place_type:box.dataset.reportType,outcome:button.dataset.outcome,plan_as_of:asOf||null})});
        if(!r.ok)throw new Error();const saved=await r.json();markReport(box,{outcome:button.dataset.outcome,reported_at:saved.reported_at});actions.toast('Report saved. Thank you for checking.');loadReports(area);}
      catch{box.querySelector('.report-status').textContent='Could not save. Try again.';}
    })));
  }
  let data={},actions={},map=null,plan=null,selectedArea=null,notice=null,language='en',noticeRequest=0,noticeVariant=0,noticeDraft='';
  let stopMarkers=new Map();
  const growthRows=()=>Array.isArray(data.growth?.clusters)?data.growth.clusters:Object.values(data.growth?.clusters||{});
  const growthFor=id=>growthRows().find(c=>String(c.cluster_id??c.id)===String(id));
  const growthText=row=>row?.status_label||row?.classification||row?.status||'Not enough history yet';
  const growthBadge=row=>{let status=growthText(row);if(/insufficient|not_enough|unavailable/i.test(status))status='Not enough history yet';return `<span class="growth-badge ${/growing/i.test(status)?'is-growing':''}">${esc(status)}</span>`;};
  const clusterFeatures=code=>(data.current?.clusters?.features||[]).filter(f=>(f.properties.area_codes||[f.properties.area_code]).includes(code));
  function sourceLink(src){return `<a href="${safeURL(src.url||src.source_url)}" target="_blank" rel="noopener">${esc(src.name||src.layer||src.dataset_id||'Source')}${icon('arrow-up-right')}</a>${src.retrieved_at||src.retrieved_at_utc?`<span>Retrieved ${date(src.retrieved_at||src.retrieved_at_utc)}</span>`:''}`;}
  function download(text,name,type='text/plain;charset=utf-8'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function load(payload,callbacks){
    data=payload;actions=callbacks;
    if(!window.DENGUESUX_DATA){await Promise.all(['inspection','growth','notices'].map(async key=>{try{const r=await fetch(`/data/${key}.json`,{cache:'no-cache',signal:AbortSignal.timeout(12000)});if(r.ok)data[key]=await r.json();}catch{/* Existing dashboard remains usable without optional artifacts. */}}));}
    $('#close-notice').addEventListener('click',()=>$('#notice-dialog').close());
  }
  function areaActions(area){
    selectedArea=area;
    const box=document.createElement('section');box.className='field-actions';
    box.innerHTML=`<button class="solid-button plan-button">${icon('footprints')} Plan inspection ${icon('arrow-up-right')}</button><button class="text-button notice-button">${icon('translate')} Draft resident notice</button>`;
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
    window.RouteFlythrough?.dispose();
    if(map){map.remove();map=null;}$('#inspection-view').hidden=true;document.body.classList.remove('inspection-open');
    $('.page-heading').hidden=false;$('.view-bar').hidden=false;
  }
  function openPlan(area){
    window.RouteFlythrough?.dispose();
    selectedArea=area;actions.open();
    if(map){map.remove();map=null;}
    const inspection=data.inspection||{};
    plan=inspection.areas?.[area.code]||{area_code:area.code,area_name:area.name,status:'unavailable',message:'Inspection data has not been built yet. Run the inspection pipeline to load verified places.',stops:[],cluster_blocks:[],search_rings:[],clusters:{type:'FeatureCollection',features:clusterFeatures(area.code)}};
    const stops=plan.stops||[],radius=inspection.radius_m||300,route=plan.route||{};
    // Show text that repeats across every stop once, not on each card.
    const same=key=>stops.length>1&&new Set(stops.map(s=>JSON.stringify(s[key]??null))).size===1;
    const opts={checklist:same('checklist')?stops[0].checklist||null:null,showScore:!same('score')};
    const sourceDates=[...new Set(clusterFeatures(area.code).map(f=>date(f.properties.updated_at)))];
    $('#signals-view').hidden=true;$('#forecast-view').hidden=true;$('#inspection-view').hidden=false;
    $('.page-heading').hidden=true;$('.view-bar').hidden=true;document.body.classList.add('inspection-open');
    $('#inspection-view').innerHTML=`<div class="inspection-nav"><button id="back-to-areas" class="text-button">${icon('arrow-left')} Area signals</button><span>FIELD PLAN <span class="nav-step">/</span> ${esc(area.name)}</span><button id="print-plan" class="text-button" ${stops.length?'':'disabled'}>${icon('printer')} Print / save PDF</button></div>
      <header class="inspection-heading"><div><h1 tabindex="-1">${esc(area.name)}<span>Inspection plan</span></h1></div><button class="outline-button" id="plan-notice">${icon('translate')} Resident notice</button></header>
      <div class="plan-evidence"><span title="NEA source updated ${esc(sourceDates.join(' / ')||'unavailable')}">${icon('calendar-dots')} Snapshot ${date(inspection.as_of||data.current?.as_of)}</span><span title="Assumed search radius around each cluster block">${icon('circles-three')} ${radius} m radius</span>${plan.impact?`<span class="impact-chip" title="${esc(plan.impact.source)}. ${esc(plan.impact.note)}">${icon('house-line')} <strong>${num(plan.impact.homes_in_route_blocks)}</strong> homes in the blocks on this route · ${num(plan.impact.homes_in_cluster_blocks)} in the cluster blocks${plan.impact.tallest_block_floors?` · up to ${plan.impact.tallest_block_floors} storeys`:''}</span>`:''}</div>
      ${inspection.map_data_stale?`<div class="field-warning">${icon('cloud-warning')}<span>${esc(inspection.stale_note||'Map data may be stale. Cached geocodes are being used because OneMap could not be refreshed.')}</span></div>`:''}
      <div class="inspection-layout"><div class="inspection-map-column"><section class="inspection-map-wrap" aria-label="Street level inspection map"><div id="inspection-map"></div><button id="fit-inspection" class="map-chip">${icon('arrows-out-simple')} Fit plan</button><div id="tile-warning" class="tile-warning" role="status" hidden>OneMap basemap is unavailable. Verified source locations remain visible; map data may be stale.</div></section><div class="inspection-legend"><span><b class="legend-footprint"></b>Cluster footprint</span><span><b class="legend-radius"></b>${radius} m search</span><span><b class="legend-block"></b>Cluster block</span><span><b class="legend-route"></b>${route.method==='onemap_walk'?'Walking route':'Approximate order'}</span></div><p class="route-disclaimer">${route.method==='onemap_walk'?'Walking directions from OneMap. Check local access and conditions.':'Straight lines show approximate order, not walkable paths. Check crossings and access on the ground.'}</p>
      <details class="plan-sources"><summary>${icon('database')} Sources, scoring & limits</summary><div class="source-content"><h3>A transparent planning rule</h3><p>${esc(typeof inspection.formula==='string'?inspection.formula:inspection.formula?.expression||'Place type + proximity + cluster size + growth + elderly share. Each component is capped; unavailable inputs add no points.')}</p>${formulaDetails(inspection.formula)}<p>Top ${inspection.top_n||8} available places; ${radius} m from exact cluster blocks. A place can be outside the selected area if it is near a shared cluster. Source points are approximate locations, not verified public entrances. Inspect only publicly accessible places; never enter homes or climb to gutters.</p><div class="source-links">${(inspection.sources||[]).map(sourceLink).join('')}</div><ul>${(inspection.layer_status||[]).map(x=>`<li><strong>${esc(x.name||x.layer||x.dataset_id)}</strong>: ${esc(x.reason||x.note||x.status)}</li>`).join('')}</ul></div></details></div>
      <section class="inspection-stops" aria-labelledby="stops-heading"><div class="stops-heading"><h2 id="stops-heading">${stops.length?`${stops.length} places to check`:'No verified stops yet'}</h2></div><p class="field-report-summary" id="field-report-summary" hidden></p><p class="stops-subtitle">${stops.length?`${route.method==='onemap_walk'&&route.distance_m?`${num(route.distance_m/1000,1)} km walking route`:'Approximate order'} · numbered in visit order`:'A route needs verified block coordinates.'}</p>${stops.length&&plan.unresolved_blocks?`<p class="coverage-note">${plan.unresolved_blocks} listed block${plan.unresolved_blocks===1?'':'s'} couldn’t be located, so nearby places may be missing.</p>`:''}${opts.checklist?`<div class="shared-checklist"><h3>At each stop, look for stagnant water</h3><ul>${opts.checklist.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div>`:''}${stops.length?'<div class="stop-progress"><span id="stop-progress-label" role="status"></span><progress id="stop-progress" aria-label="Inspection checklist progress" max="1" value="0"></progress></div>':''}<ol class="stop-list">${stops.map(s=>renderStop(s,opts)).join('')}</ol>${stops.length?'':`<div class="inspection-empty">${icon('map-pin-line')}<h3>${plan.status==='no_active_clusters'?'No active cluster in this area':'Exact block locations are unavailable'}</h3><p>${esc(plan.message||'No validated places match the saved snapshot and radius. No replacement locations have been generated.')}</p><p>Check the dated cluster footprint for context. A footprint does not identify a place with stagnant water.</p></div>`}<p class="inspection-footnote">${FOOTNOTE}</p></section></div>`;
    $('#back-to-areas').addEventListener('click',()=>{closePlan();actions.back();$('#area-detail .plan-button')?.focus();});
    $('#print-plan').addEventListener('click',()=>window.print());$('#plan-notice').addEventListener('click',()=>openNotice(area));
    $('.stop-list').querySelectorAll('[data-stop]').forEach(b=>b.addEventListener('click',()=>focusStop(b.dataset.stop)));
    $('.stop-list').querySelectorAll('input[type=checkbox]').forEach(c=>c.addEventListener('change',()=>{const key=`denguesux-check:${inspection.as_of}:${area.code}:${c.dataset.check}`;try{sessionStorage.setItem(key,String(c.checked));}catch{}updateProgress();}));
    $('.stop-list').querySelectorAll('input[type=checkbox]').forEach(c=>{try{c.checked=sessionStorage.getItem(`denguesux-check:${inspection.as_of}:${area.code}:${c.dataset.check}`)==='true';}catch{}});
    bindReports(area,inspection.as_of);loadReports(area);
    updateProgress();renderPlanMap();window.RouteFlythrough?.mount(plan,area,id=>focusStop(id,true));$('#inspection-view').scrollIntoView({block:'start',behavior:'instant'});$('.inspection-heading h1').focus({preventScroll:true});
  }
  function updateProgress(){
    const checks=[...document.querySelectorAll('.stop-list input[type=checkbox]')];
    const meter=$('#stop-progress');if(!meter)return;
    const done=checks.filter(c=>c.checked).length,total=checks.length;
    const unit=$('.stop-done')?'stops':'checks';
    $('#stop-progress-label').textContent=total&&done===total?'Checklist complete · thank you for checking':`${done} of ${total} ${unit} complete`;
    meter.max=total||1;meter.value=done;meter.parentElement.classList.toggle('complete',total>0&&done===total);
  }
  function renderStop(s,opts={}){
    const types={hdb:'building',hdb_block:'building',block:'building',park:'tree',parks:'tree',hawker:'storefront',hawker_centre:'storefront'};
    const components=Array.isArray(s.components)?s.components:Object.entries(s.components||{}).map(([key,v])=>typeof v==='object'?{key,...v}:{key,label:key,contribution:v});
    const checklist=opts.checklist?'':`<fieldset class="stop-checklist"><legend>Look for stagnant water in</legend>${(s.checklist||[]).map((item,i)=>`<label><input type="checkbox" data-check="${esc(s.id)}:${i}"><span>${esc(item)}</span></label>`).join('')}</fieldset>`;
    return `<li class="inspection-stop compact-stop" id="stop-${esc(s.id)}"><div class="stop-top"><button class="stop-number" data-stop="${esc(s.id)}" aria-label="Show stop ${s.number} on map" title="Priority #${s.rank??s.number}">${s.number}</button><div><h3>${esc(s.name)}</h3><span class="place-type">${icon(types[s.place_type]||'map-pin')} ${esc(String(s.place_type||'place').replaceAll('_',' '))}${s.max_floor_lvl?` · ${s.max_floor_lvl} storeys`:''}${s.dwelling_units?` · ${num(s.dwelling_units)} homes`:''}</span></div>${opts.showScore?`<strong class="stop-score">${num(s.score,1)}<small>/ 100</small></strong>`:''}${opts.checklist?`<label class="stop-done"><input type="checkbox" data-check="${esc(s.id)}:done"><span>Done</span></label>`:''}</div>${checklist}<div class="stop-report" data-report-stop="${esc(s.id)}" data-report-name="${esc(s.name)}" data-report-type="${esc(s.place_type||'place')}"><span>What did you find?</span>${REPORT_OPTIONS.map(([key,label,ic])=>`<button type="button" data-outcome="${key}">${icon(ic)} ${label}</button>`).join('')}<small class="report-status" role="status"></small></div><div class="stop-foot"><details class="score-details"><summary>Why this place ${icon('caret-down')}</summary><p class="stop-reason">${esc(s.reason||'Reason unavailable — exclude this stop before inspection.')}</p><dl>${components.map(c=>`<div><dt>${esc(c.label||c.key)}<small>${esc(componentStatus(c.status))}${c.value!=null?` · ${typeof c.value==='number'?num(c.value,2):esc(c.value)}${c.unit?` ${esc(c.unit)}`:''}`:''}</small></dt><dd>${num(c.contribution??c.points,1)}${c.cap!=null?` <span>/ ${c.cap}</span>`:''}</dd></div>`).join('')}</dl><p>Planning points, not a disease probability. Missing inputs contribute no points.</p><p>As of ${date(s.as_of||data.inspection?.as_of)}. ${(s.sources||[]).map(src=>typeof src==='string'?esc(src):sourceLink(src)).join(' · ')}</p></details><a class="stop-map-link" href="https://www.google.com/maps/search/?api=1&query=${Number(s.latitude)},${Number(s.longitude)}" target="_blank" rel="noopener">Google Maps ${icon('arrow-up-right')}</a></div><span class="print-coordinates">${Number(s.latitude).toFixed(6)}, ${Number(s.longitude).toFixed(6)}</span></li>`;
  }
  function renderPlanMap(){
    stopMarkers=new Map();map=L.map('inspection-map',{minZoom:11,maxZoom:20,scrollWheelZoom:false,zoomControl:false,zoomSnap:.25,zoomDelta:.5}).setView(selectedArea.centroid||[1.35,103.82],15);L.control.zoom({position:'bottomright'}).addTo(map);map.attributionControl.setPrefix(false);
    const tiles=L.tileLayer('https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png',{maxZoom:20,minZoom:11,attribution:'<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener">OneMap</a> © Singapore Land Authority · NEA / data.gov.sg'}).addTo(map);
    tiles.on('tileerror',()=>{$('#tile-warning').hidden=false;});
    const bounds=L.featureGroup().addTo(map);
    const visitBounds=L.latLngBounds((plan.stops||[]).map(s=>[s.latitude,s.longitude]));
    const clusterLayer=L.geoJSON(plan.clusters||{type:'FeatureCollection',features:clusterFeatures(selectedArea.code)},{style:{color:'#b5412d',weight:1.5,fillColor:'#d65239',fillOpacity:.12},onEachFeature:(f,l)=>{const p=f.properties||{};l.bindPopup(`<strong>${num(p.cases??p.CASE_SIZE)} people associated with this cluster</strong><br>${esc(p.name||p.LOCALITY)}<br>${growthBadge(growthFor(p.id||p.OBJECTID))}<br><small>Cluster footprint, not a confirmed breeding location.</small>`);}}).addTo(map);
    if(!(plan.cluster_blocks||[]).length)bounds.addLayer(clusterLayer);
    (plan.search_rings||[]).forEach(r=>L.circle([r.latitude,r.longitude],{radius:r.radius_m||data.inspection.radius_m,color:'#5c8c73',weight:1,dashArray:'4 5',fillColor:'#91b89b',fillOpacity:.035,interactive:false}).addTo(bounds));
    (plan.cluster_blocks||[]).forEach(b=>L.circleMarker([b.latitude,b.longitude],{radius:4,color:'#b5412d',weight:2,fillColor:'#fff',fillOpacity:1}).bindPopup(`<strong>Cluster block ${esc(b.block)}</strong><br>${esc(b.street)}<br><small>OneMap geocode · retrieved ${date(b.retrieved_at)}</small>`).addTo(bounds));
    if(plan.route?.geometry)L.geoJSON(plan.route.geometry,{style:{color:'#163f35',weight:3,opacity:.8,dashArray:plan.route.method==='onemap_walk'?null:'7 7'}}).addTo(bounds);
    (plan.stops||[]).forEach(s=>{const marker=L.marker([s.latitude,s.longitude],{icon:L.divIcon({className:'inspection-pin',html:String(s.number),iconSize:[32,32],iconAnchor:[16,16]}),title:`Stop ${s.number}: ${s.name}`}).bindPopup(`<strong>${s.number}. ${esc(s.name)}</strong><br>${esc(s.reason)}`).addTo(bounds);marker.on('click',()=>{$(`#stop-${CSS.escape(String(s.id))}`)?.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});});stopMarkers.set(String(s.id),marker);});
    const fit=()=>{if(bounds.getBounds().isValid())map.fitBounds(bounds.getBounds(),{padding:[30,30],maxZoom:17});else if(selectedArea.centroid)map.setView(selectedArea.centroid,15);else map.setView([1.35,103.82],12);};
    if(visitBounds.isValid())map.fitBounds(visitBounds,{padding:[55,55],maxZoom:17.5});else fit();
    $('#fit-inspection').addEventListener('click',fit);requestAnimationFrame(()=>map.invalidateSize());
  }
  function focusStop(id,fromTour=false){
    document.querySelectorAll('.inspection-stop').forEach(card=>{const selected=card.id==='stop-'+id;card.classList.toggle('is-tour-selected',selected);const button=card.querySelector('.stop-number');if(selected)button?.setAttribute('aria-current','step');else button?.removeAttribute('aria-current');});
    if(fromTour||window.RouteFlythrough?.focusStop(id))return;
    const marker=stopMarkers.get(String(id));if(marker){map.setView(marker.getLatLng(),18);marker.openPopup();if(matchMedia('(max-width:720px)').matches)$('#inspection-map').scrollIntoView({block:'center'});}
  }
  async function openNotice(area){
    selectedArea=area;language='en';noticeVariant=0;$('#notice-title').textContent=`A note for ${area.name}`;$('#notice-dialog').showModal();await showNotice();
  }
  function savedNotice(code,lang){const n=data.notices||{};return n.areas?.[code]?.[lang]||n.notices?.[code]?.[lang]||n[code]?.[lang]||null;}
  async function showNotice(){
    const req=++noticeRequest,code=selectedArea.code,lang=language;
    $('#notice-content').innerHTML=`<p class="notice-loading" role="status">${icon('circle-notch')} Preparing a draft from the saved source facts…</p>`;
    let result=savedNotice(code,lang);
    if(!window.DENGUESUX_DATA){try{const r=await fetch(`/api/notices/${encodeURIComponent(code)}?language=${encodeURIComponent(lang)}`);if(r.ok)result=await r.json();}catch{}}
    if(req!==noticeRequest)return;
    notice=result;
    const facts=result?.source_facts||result?.facts;
    const languages=[['en','English'],['zh','中文'],['ms','Bahasa Melayu'],['ta','தமிழ்']];
    $('#notice-content').innerHTML=`<p class="notice-label">${icon('pencil-simple')} Draft: review before sending</p><div class="notice-tabs" role="group" aria-label="Notice language">${languages.map(([id,label])=>`<button data-language="${id}" aria-pressed="${id===lang}" class="${id===lang?'active':''}" lang="${id}">${label}</button>`).join('')}</div>${result?`<div class="notice-text" id="notice-text" lang="${lang}"></div><details class="notice-checks" id="notice-checks"></details><div class="notice-tools"><button id="copy-notice" class="solid-button">${icon('copy')} Copy notice</button><button id="download-notice" class="outline-button">${icon('download-simple')} Download</button>${lang==='en'&&facts?`<button id="rewrite-notice" class="text-button">${icon('arrows-clockwise')} Rewrite</button>`:''}</div><details class="notice-facts"><summary><h3>Sources used</h3>${icon('caret-down')}</summary>${renderFacts(result.source_facts||result.facts)}<p>Area totals may share clusters. Counts are from the dated snapshot, not new cases this week.</p><a href="https://www.nea.gov.sg/dengue-zika/stop-dengue-now" target="_blank" rel="noopener">NEA Mozzie Wipeout ${icon('arrow-up-right')}</a></details>`:'<div class="inspection-empty"><h3>Notice facts are unavailable</h3><p>Build the saved notice artifact before drafting. No unsupported facts have been substituted.</p></div>'}`;
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
  function typeNotice(text){
    const box=$('#notice-text');if(!box)return;
    // Progress follows elapsed time, so throttled timers catch up instead of stalling mid-draft.
    const words=text.split(/(\s+)/),start=performance.now();box.textContent='';box.classList.add('is-writing');
    const step=()=>{if(!box.isConnected||box.dataset.draft!==text)return;const i=Math.min(words.length,Math.ceil((performance.now()-start)/4.5));box.textContent=words.slice(0,i).join('');if(i<words.length)setTimeout(step,24);else box.classList.remove('is-writing');};
    box.dataset.draft=text;
    if(matchMedia('(prefers-reduced-motion: reduce)').matches){box.textContent=text;box.classList.remove('is-writing');}else step();
  }
  function noticeExport(){return `Draft: review before sending\n\n${noticeDraft||noticeText(notice,language)}\n\nSource facts\n${JSON.stringify(notice.source_facts||notice.facts,null,2)}\nNEA: https://www.nea.gov.sg/dengue-zika/stop-dengue-now\n`;}
  window.Fieldwork={load,areaActions,renderGrowth,openPlan,closePlan,openNotice,growthFor,growthBadge};
})();
