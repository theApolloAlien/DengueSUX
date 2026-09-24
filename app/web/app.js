/* DengueSUX: local, dependency-light evidence dashboard. All values come from the saved pipeline artifact. */
(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const escape = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const number = (v, digits=0) => finite(v) ? v.toLocaleString('en-SG',{maximumFractionDigits:digits,minimumFractionDigits:digits}) : '—';
  const date = (value, opts={day:'numeric',month:'short',year:'numeric'}) => {
    if (!value) return 'Not available';
    const text=String(value);
    const normalized=/^\d{14}$/.test(text)?`${text.slice(0,4)}-${text.slice(4,6)}-${text.slice(6,8)}`:text;
    const d=new Date(normalized.length===10 ? `${normalized}T12:00:00+08:00` : normalized);
    return Number.isNaN(d.valueOf()) ? text : d.toLocaleDateString('en-SG',opts);
  };
  const percent = v => finite(v) ? `${number(v<=1?v*100:v,1)}%` : '—';
  const colors={Low:'#f4e7c6',Medium:'#edae48',High:'#d65239',Unknown:'#dfe5dc'};
  const color=risk=>colors[risk]||colors.Unknown;
  const badge=(risk)=>`<span class="badge ${escape((risk||'unknown').toLowerCase())}">${escape(risk||'Unavailable')}</span>`;
  const icon=name=>`<i class="ph ph-${name}" aria-hidden="true"></i>`;
  const state={data:null,areas:[],filter:'active',search:'',selected:null,view:'signals',map:null,areaLayer:null,clusterLayer:null,labelLayer:null,layers:new Map(),predictions:[],index:0,chartGeometry:null,replayOnly:true};
  let toastTimeout, replayTimer, ready=false;

  function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>$('#toast').hidden=true,3500);}
  function current(){return state.data.current||{};}
  function meta(){return state.data?.meta||{};}
  function renderDataStatus(){
    const c=current(),status=$('#data-timestamp');
    status.innerHTML=`<span class="status-dot"></span> Updated ${date(c.as_of)}`;
    status.title=`Cluster snapshot saved ${date(c.as_of)} · weather ${date(c.weather_date||meta().current_weather_date)}. National case reports end Dec 2022, so the forecast is a 2022 replay.`;
  }
  const modelLabel=()=>state.data?.model?.selected_baseline?'Four-week average':'Weather + recent trends';
  const TITLES={signals:'Area signals',forecast:'Forecast lab'};
  const reducedMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  function setDrawer(open,restoreFocus=false){$('.explorer').classList.toggle('show-areas',open);$('#toggle-areas').setAttribute('aria-expanded',String(open));if(open)$('#area-search').focus();else if(restoreFocus)$('#toggle-areas').focus();}

  function metric(area,key){
    const weather=area.weather?.current||area.weather||{};
    const raw=weather[key];return raw&&typeof raw==='object'?raw:{value:raw??null};
  }

  function normalizeArea(raw){
    const components=raw.components||raw.signals||raw.priority_components||{};
    return {...raw,name:raw.name||raw.PLN_AREA_N||'Unnamed area',code:raw.code||raw.PLN_AREA_C,risk:raw.risk||raw.risk_label||raw.priority_label||'Unknown',score:raw.score??raw.risk_score??raw.priority_score,components,completeness:raw.completeness??raw.weather_completeness};
  }
  function switchView(view){
    if(state.view==='inspection')window.Fieldwork?.closePlan();
    state.view=view==='forecast'?'forecast':'signals';
    if(state.view!=='forecast')stopReplay();
    $$('.view-tab,.rail-button[data-view]').forEach(button=>{const active=button.dataset.view===state.view;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
    if(ready){$('#signals-view').hidden=state.view!=='signals';$('#forecast-view').hidden=state.view!=='forecast';}
    $('#page-title').textContent=TITLES[state.view];
    $('#page-description').textContent=state.view==='forecast'?'Explore how the two-week outlook performed against reported cases in 2022.':'Find an area. Understand the signals. Plan your next check.';
    if(state.view==='signals' && state.map)setTimeout(()=>{state.map.invalidateSize();state.map.fitBounds(state.areaLayer.getBounds(),{padding:[24,24],animate:false});},40);
    if(state.view==='forecast')requestAnimationFrame(drawChart);
    if(location.hash!==`#${state.view}`)history.replaceState(null,'',`#${state.view}`);
  }

  function renderAreas(){
    const matches=state.areas.filter(a=>`${a.name} ${a.region}`.toLowerCase().includes(state.search));
    const filtered=matches.filter(a=>state.filter==='all'||(state.filter==='active'?a.cluster_count>0:a.risk===state.filter));
    const hidden=state.filter==='active'?matches.length-filtered.length:0;
    $('#area-list-count').textContent=filtered.length;
    const more=hidden?`<button class="area-row area-more" data-show-all>${icon('eye')}<span class="area-row-text"><span class="area-row-name">${hidden} more with no active clusters</span></span></button>`:'';
    $('#area-list').innerHTML=filtered.length||hidden?filtered.map(a=>`<button class="area-row ${a.code===state.selected?'active':''}" data-area="${escape(a.code)}" aria-pressed="${a.code===state.selected}" aria-label="${escape(a.name)}, ${escape(a.risk)} priority"><span class="area-dot" style="background:${color(a.risk)}"></span><span class="area-row-text"><span class="area-row-name">${escape(a.name)}</span><span class="area-row-meta">${a.cluster_count?`${number(a.cluster_count)} ${a.cluster_count===1?'cluster':'clusters'} · ${number(a.cluster_cases)} people`:'No active clusters'}</span></span>${badge(a.risk)}</button>`).join('')+more:`<div class="empty-list">${icon('magnifying-glass')}<strong>No matching areas</strong><p>Try another name or reset your filters.</p><button class="outline-button" data-reset-search>Show all areas</button></div>`;
    $$('#area-list [data-area]').forEach(b=>b.addEventListener('click',()=>selectArea(b.dataset.area,true)));
    $('#area-list [data-show-all]')?.addEventListener('click',()=>setFilter('all'));
    $('#area-list [data-reset-search]')?.addEventListener('click',()=>{state.search='';$('#area-search').value='';setFilter('all');$('#area-search').focus();});
  }
  function setFilter(filter){
    state.filter=filter;
    $$('.filter').forEach(b=>{b.classList.toggle('active',b.dataset.filter===filter);b.setAttribute('aria-pressed',String(b.dataset.filter===filter));});
    renderAreas();
  }
  function styleArea(feature){const p=normalizeArea(feature.properties);const selected=p.code===state.selected;return{color:selected?'#714032':'#bdbaad',weight:selected?2.1:.8,fillColor:$('#show-priority').checked?color(p.risk):'#dce7d5',fillOpacity:selected?.93:.76,opacity:selected?1:.8};}
  function selectArea(code,pan=false){
    const area=state.areas.find(a=>a.code===code);if(!area)return;state.selected=code;renderAreas();renderAreaDetail(area);
    if(state.areaLayer){state.areaLayer.setStyle(styleArea);const layer=state.layers.get(code);if(layer){layer.bringToFront();if(pan){const p=area.centroid;if(p)state.map.panTo(p,{animate:!matchMedia('(prefers-reduced-motion: reduce)').matches});}}}
    setDrawer(false);
  }
  function renderAreaDetail(area){
    const rain=metric(area,'rainfall'),temp=metric(area,'temperature'),rh=metric(area,'humidity');
    const observed=[rain,temp,rh].filter(m=>finite(m.value)).length;
    const weatherRows=[['Rain',rain,'mm','cloud-rain'],['Temperature',temp,'°C','thermometer-simple'],['Humidity',rh,'%','drop']];
    const station=m=>finite(m.value)?`${m.station_name} · ${number(m.distance_km,1)} km · ${percent(m.coverage)} readings · ${date(current().weather_date)}`:'No qualifying observation';
    const wx=(label,m,unit,i)=>`<div class="signal-row" title="${escape(station(m))}"><span class="signal-label">${icon(i)}${label}</span><span class="signal-value">${finite(m.value)?number(m.value,1):'—'}<small>${finite(m.value)?unit:''}</small></span></div>`;
    const caption=area.cluster_count?`in ${number(area.cluster_count)} active ${area.cluster_count===1?'cluster':'clusters'}`:'No active clusters in this snapshot';
    $('#area-detail').innerHTML=`<div class="detail-top"><p class="detail-region">${escape(area.region||'Singapore')}</p>${badge(area.risk)}</div><h3 class="detail-title">${escape(area.name)}</h3><div class="priority-summary"><div class="area-people">${number(area.cluster_cases)} <span>people</span></div><p class="priority-caption">${caption}</p></div><details class="area-weather"><summary>Local weather <span>${observed}/3 stations</span></summary>${weatherRows.map(row=>wx(...row)).join('')}</details>`;
    window.Fieldwork?.areaActions(area);
    const detail=$('#area-detail');detail.classList.remove('detail-enter');void detail.offsetWidth;detail.classList.add('detail-enter');
  }

  function initializeMap(){
    const c=current();const boundaries=c.boundaries||(c.areas?.type==='FeatureCollection'?c.areas:null);
    if(!boundaries?.features?.length)throw new Error('Planning area boundaries are missing from the saved artifact.');
    state.map=L.map('map',{zoomControl:false,attributionControl:true,minZoom:8,maxZoom:15,scrollWheelZoom:false,zoomSnap:.25});
    L.control.zoom({position:'bottomright'}).addTo(state.map);
    state.map.attributionControl.setPrefix(false);state.map.attributionControl.addAttribution('URA Master Plan 2025 · NEA / data.gov.sg');
    state.areaLayer=L.geoJSON(boundaries,{style:styleArea,onEachFeature:(feature,layer)=>{const p=normalizeArea(feature.properties);state.layers.set(p.code,layer);layer.bindTooltip(`<strong>${escape(p.name)}</strong><br>${escape(p.risk)} planning priority · ${number(p.cluster_cases||0)} people in clusters`,{sticky:true,direction:'top'});layer.on('click',()=>selectArea(p.code));layer.on('mouseover',()=>layer.setStyle({weight:2,color:'#617c50'}));layer.on('mouseout',()=>layer.setStyle(styleArea(feature)));}}).addTo(state.map);
    state.map.fitBounds(state.areaLayer.getBounds(),{padding:[24,24]});
    const clusterFeatures=c.clusters?.features||[];
    state.clusterLayer=L.layerGroup();
    clusterFeatures.forEach(feature=>{const p=feature.properties||{};const pos=finite(p.latitude)&&finite(p.longitude)?[p.latitude,p.longitude]:L.geoJSON(feature).getBounds().getCenter();const cases=p.cases??p.case_size??p.CASE_SIZE;const diameter=Math.round(16+5*Math.sqrt(Math.max(0,cases||0)));const marker=L.marker(pos,{icon:L.divIcon({className:'cluster-pin',html:escape(number(cases)),iconSize:[diameter,diameter],iconAnchor:[diameter/2,diameter/2]}),title:`${number(cases)} people · ${p.name||'Dengue cluster'}`,zIndexOffset:Math.round(cases||0)});marker.bindPopup(`<strong>${number(cases)} people in this cluster</strong><br>${escape(p.name||'Dengue cluster')}<br>${escape((p.area_names||[]).join(' · '))}<br><small>Updated ${date(p.updated_at)}</small><br>${window.Fieldwork?.growthBadge(window.Fieldwork.growthFor(p.id))||''}`);marker.on('click',()=>{if(p.area_code)selectArea(p.area_code);});state.clusterLayer.addLayer(marker);});
    state.clusterLayer.addTo(state.map);
    state.labelLayer=L.layerGroup();
    const prominent=new Set(['Jurong West','Woodlands','Yishun','Sembawang','Choa Chu Kang','Tampines','Pasir Ris','Bedok','Punggol','Sengkang','Ang Mo Kio','Bukit Timah','Bukit Panjang','Clementi','Queenstown','Toa Payoh','Geylang','Tuas','Changi','Southern Islands','Western Islands','Bukit Batok']);
    const updateLabels=()=>{state.labelLayer.clearLayers();state.areas.forEach(a=>{if(!a.centroid||(!prominent.has(a.name)&&state.map.getZoom()<12))return;if(state.map.getZoom()<10.5&&!['Woodlands','Tampines','Jurong West','Yishun','Bedok','Tuas'].includes(a.name))return;const label=L.marker(a.centroid,{interactive:false,icon:L.divIcon({className:'',html:`<div class="map-name-label">${escape(a.name.replace(' ','<wbr>')).replace('&lt;wbr&gt;','<wbr>')}</div>`,iconSize:[0,0]})});state.labelLayer.addLayer(label);});};
    updateLabels();state.labelLayer.addTo(state.map);state.map.on('zoomend',updateLabels);
    $('#fit-map').addEventListener('click',()=>{state.map.fitBounds(state.areaLayer.getBounds(),{padding:[24,24]});setDrawer(false);});
    $('#show-priority').addEventListener('change',()=>state.areaLayer.setStyle(styleArea));
    $('#show-clusters').addEventListener('change',e=>e.target.checked?state.clusterLayer.addTo(state.map):state.map.removeLayer(state.clusterLayer));
    $('#show-labels').addEventListener('change',e=>e.target.checked?state.labelLayer.addTo(state.map):state.map.removeLayer(state.labelLayer));
  }
  function renderCurrent(){
    const c=current();const source=Array.isArray(c.areas)?c.areas:(c.boundaries||c.areas)?.features?.map(f=>f.properties)||[];
    state.areas=source.map(normalizeArea).sort((a,b)=>(b.cluster_cases||0)-(a.cluster_cases||0)||(b.cluster_count||0)-(a.cluster_count||0)||(b.score??-1)-(a.score??-1)||a.name.localeCompare(b.name));
    const totals=c.totals||c.summary||{};
    $('#cluster-count').textContent=number(totals.clusters??c.clusters?.features?.length);$('#case-count').textContent=number(totals.cluster_cases);
    $('#high-count').textContent=number(totals.high??state.areas.filter(a=>a.risk==='High').length);
    if(state.areas.length)selectArea(state.areas[0].code);
    initializeMap();
    renderBriefing();
    renderDataStatus();
    window.Fieldwork?.renderGrowth();
  }

  function renderBriefing(){
    const largest=[...(current().clusters?.features||[])].sort((a,b)=>b.properties.cases-a.properties.cases)[0]?.properties;
    if(!largest){$('#briefing-text').textContent='No active clusters in this snapshot. Keep checking for standing water.';return;}
    const names=largest.area_names?.length?largest.area_names:[state.areas[0]?.name];
    $('#briefing-text').innerHTML=`Largest cluster: <strong>${number(largest.cases)} people</strong> in ${names.map(n=>`<strong>${escape(n)}</strong>`).join(' and ')}.`;
    const target=state.areas.find(a=>names.includes(a.name))||state.areas[0];
    const view=$('#briefing-view');view.hidden=!target;
    view.onclick=()=>{switchView('signals');selectArea(target.code,true);$('.explorer').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});};
  }
  function featureName(raw){
    const text=String(raw||'').toLowerCase();
    return /case|trend/.test(text)?'Recent cases':/season|time of year/.test(text)?'Time of year':/rain/.test(text)?'Rain':'Heat';
  }
  function groupedFeatures(features){
    const groups={'Recent cases':0,'Time of year':0,'Rain':0,'Heat':0};
    for(const f of features||[])groups[featureName(f.feature||f.name)]+=f.contribution??f.value??f.importance??0;
    return Object.entries(groups).map(([name,value])=>({name,value}));
  }
  function leadText(lead){
    if(!lead)return 'Not available';
    if(lead.status==='already_high_at_replay_start')return 'High at replay start';
    const weeks=lead.weeks_before_peak??lead.weeks;
    if(finite(weeks))return `${number(weeks,1).replace('.0','')} weeks before the peak`;
    return 'No High warning before peak';
  }

  function predictionValue(p,key){const aliases={predicted:['selected_prediction','selected_predicted','prediction_selected','predicted','prediction','y_pred','model_prediction'],candidate:['predicted','prediction','y_pred','model_prediction'],actual:['actual','target','y_true','actual_cases'],baseline:['baseline','baseline_prediction']};for(const k of aliases[key]||[key])if(finite(p[k]))return p[k];return null;}
  function renderModel(){
    const model=state.data.model||{},metrics=model.selected_metrics||model.metrics||{},baseline=model.baseline_metrics||{};
    $('#model-mae').textContent=`~${number(metrics.mae)}`;
    $('#baseline-mae').textContent=`~${number(baseline.mae)}`;
    $('#model-name').textContent=modelLabel();
    $('#lead-stat').title=`High means at least ${number(model.thresholds?.high,1)} reported people a week. Counted from the first High forecast to the observed peak.`;
    const lead=model.peak_lead_time?.selected;const weeks=lead?.weeks_before_peak??lead?.weeks;
    $('#lead-weeks').textContent=finite(weeks)?number(weeks,1).replace('.0',''):lead?.status==='already_high_at_replay_start'?'Already High':'—';
    $('#lead-caption').textContent=finite(weeks)?'weeks of advance warning':leadText(lead);
    state.predictions=(model.predictions||[]).map(p=>({...p,origin_date:p.origin_date||p.origin_week,label:p.risk,predicted:predictionValue(p,'predicted'),actual:predictionValue(p,'actual'),baseline:predictionValue(p,'baseline')}));
    $('#forecast-week').max=Math.max(0,state.predictions.length-1);$('#forecast-week').disabled=!state.predictions.length;
    if(state.predictions.length){$('#timeline-start').textContent=date(state.predictions[0].target_date);$('#timeline-end').textContent=date(state.predictions.at(-1).target_date);const firstHigh=state.predictions.findIndex(p=>p.issue_date===model.peak_lead_time?.selected?.first_high_issue_date);state.index=Math.max(0,firstHigh);$('#forecast-week').value=state.index;renderPrediction();}
    $('#split-details').innerHTML='<span><b>Train</b> 2017+</span><i class="ph ph-arrow-right" aria-hidden="true"></i><span><b>Select</b> 2019–21</span><i class="ph ph-arrow-right" aria-hidden="true"></i><span><b>Test</b> 2022</span>';
    const difference=baseline.mae-metrics.mae;
    const result=!finite(difference)?'':Math.abs(difference)<.05?'The simple average remains our strongest forecast.':difference>0?`The forecast’s average error was ${number(difference/baseline.mae*100)}% lower than the simple average’s.`:`The simple average was ${number(Math.abs(difference))} people a week closer in 2022.`;
    $('#model-comparison').textContent=`${result} Simple average: ${leadText(model.peak_lead_time?.baseline).toLowerCase()}.`;
    $('#model-selection-note').hidden=!model.selected_baseline;
    if(model.selected_baseline)$('#model-selection-note').innerHTML=`${icon('scales')}<span>The simple average won across quiet and outbreak years.</span>`;
    $('#about-model').textContent=`The map helps people decide where to check first. The national replay uses the ${modelLabel().toLowerCase()} model, chosen using 2019–2021. ${result}`;
    requestAnimationFrame(drawChart);
  }

  function renderPrediction(){
    const p=state.predictions[state.index];if(!p)return;
    $('#forecast-week-date').textContent=date(p.target_date,{day:'numeric',month:'short'});
    const drivers=groupedFeatures(p.top_features);
    const max=Math.max(...drivers.map(f=>Math.abs(f.value)),.001);
    $('#forecast-detail').innerHTML=`<div class="detail-top"><span class="eyebrow">TWO-WEEK OUTLOOK</span>${badge(p.label)}</div><h3>${date(p.target_date,{day:'numeric',month:'long'})}</h3><div class="forecast-number">${number(p.predicted)}<small>people</small></div><p class="forecast-number-caption">forecast for this week</p><div class="signal-row"><span class="signal-label">Actually reported</span><span class="signal-value">${number(p.actual)}</span></div><div class="signal-row"><span class="signal-label">Simple average</span><span class="signal-value">${number(p.baseline)}</span></div><h4 class="forecast-driver-title">What shaped this outlook</h4>${drivers.map(f=>`<div class="forecast-driver"><span>${escape(f.name)}</span><span class="driver-direction ${f.value<0?'negative':''}" aria-label="${f.value>0?'Raised':f.value<0?'Lowered':'No effect on'} forecast">${f.value>0?'↑':f.value<0?'↓':'—'}<b style="width:${Math.abs(f.value)/max*48}px"></b></span></div>`).join('')}`;
    const peakIndex=state.predictions.reduce((best,row,i)=>row.actual>state.predictions[best].actual?i:best,0);
    const crossing=state.data.model?.peak_lead_time?.selected?.first_high_issue_date;
    const note=state.index===peakIndex?`The outbreak peaks: ${number(p.actual)} people reported this week.`:crossing&&p.issue_date===crossing?`The forecast turns High — ${leadText(state.data.model.peak_lead_time.selected).toLowerCase()}.`:'';
    $('#replay-note').textContent=note;$('#replay-note').hidden=!note;
    drawChart();
  }
  function stopReplay(){clearInterval(replayTimer);replayTimer=null;$('#replay-button').innerHTML=`${icon('play')} Replay 2022`;$('#replay-button').setAttribute('aria-pressed','false');}
  function toggleReplay(){
    if(replayTimer){stopReplay();return;}
    state.index=0;$('#forecast-week').value=0;renderPrediction();
    $('#replay-button').innerHTML=`${icon('pause')} Pause replay`;$('#replay-button').setAttribute('aria-pressed','true');
    replayTimer=setInterval(()=>{if(state.index>=state.predictions.length-1){stopReplay();return;}state.index++;$('#forecast-week').value=state.index;renderPrediction();},700);
  }

  function drawChart(){
    const canvas=$('#forecast-chart');const rect=canvas.getBoundingClientRect();if(rect.width<10)return;
    const dpr=Math.min(window.devicePixelRatio||1,2);canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
    const width=rect.width,height=rect.height,pad={left:43,right:13,top:20,bottom:28};const chartWidth=width-pad.left-pad.right,chartHeight=height-pad.top-pad.bottom;
    const rows=state.predictions;
    if(!rows.length){ctx.fillStyle='#93a183';ctx.font='11px "DM Sans", sans-serif';ctx.textAlign='center';ctx.fillText('Historical predictions will appear here.',width/2,height/2);return;}
    const maxValue=Math.max(...rows.flatMap(p=>[p.actual,p.predicted,p.baseline]).filter(finite),1);const step=10**Math.floor(Math.log10(maxValue));const yMax=Math.ceil(maxValue/step)*step;
    const x=i=>pad.left+i/Math.max(1,rows.length-1)*chartWidth;const y=v=>pad.top+(1-v/yMax)*chartHeight;
    ctx.font='9px "DM Sans", sans-serif';ctx.lineWidth=1;ctx.textAlign='right';ctx.fillStyle='#a0aa94';
    for(let i=0;i<=4;i++){const value=yMax*i/4;const lineY=y(value);ctx.beginPath();ctx.strokeStyle='#edf1e7';ctx.moveTo(pad.left,lineY);ctx.lineTo(width-pad.right,lineY);ctx.stroke();ctx.fillText(number(value),pad.left-10,lineY+3);}
    ctx.textAlign='center';const tickCount=Math.min(6,rows.length);for(let i=0;i<tickCount;i++){const index=Math.round(i/(tickCount-1||1)*(rows.length-1));ctx.fillText(date(rows[index].target_date,{month:'short'}),x(index),height-5);}
    const drawLine=(key,stroke,lineWidth,dash=[])=>{ctx.beginPath();ctx.strokeStyle=stroke;ctx.lineWidth=lineWidth;ctx.setLineDash(dash);let started=false;rows.forEach((p,i)=>{if(!finite(p[key])){started=false;return;}if(started)ctx.lineTo(x(i),y(p[key]));else{ctx.moveTo(x(i),y(p[key]));started=true;}});ctx.stroke();ctx.setLineDash([]);};
    drawLine('baseline','#cbb687',1.7,[4,4]);drawLine('predicted','#8ba97c',2.2);drawLine('actual','#244f3d',2.3);
    const peak=rows.reduce((best,row,i)=>row.actual>rows[best].actual?i:best,0);
    const crossingDate=state.data.model?.peak_lead_time?.selected?.first_high_issue_date;
    const crossing=rows.findIndex(row=>row.issue_date===crossingDate);
    const annotation=(index,label,top,stroke)=>{if(index<0)return;ctx.strokeStyle=stroke;ctx.lineWidth=1;ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(x(index),top+5);ctx.lineTo(x(index),y(rows[index].actual)-7);ctx.stroke();ctx.setLineDash([]);ctx.font='9px "DM Sans", sans-serif';ctx.textAlign='left';const textWidth=ctx.measureText(label).width;const tx=Math.max(pad.left,Math.min(width-pad.right-textWidth,x(index)+5));ctx.fillStyle='#fff';ctx.fillRect(tx-3,top-10,textWidth+6,14);ctx.fillStyle=stroke;ctx.fillText(label,tx,top);};
    annotation(peak,'Reported peak',pad.top+12,'#6f8066');
    annotation(crossing,'First High outlook',pad.top+31,'#b08546');
    const p=rows[state.index];ctx.strokeStyle='#b4c0a5';ctx.lineWidth=1;ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(x(state.index),pad.top);ctx.lineTo(x(state.index),height-pad.bottom);ctx.stroke();ctx.setLineDash([]);
    [['actual','#244f3d'],['predicted','#8ba97c'],['baseline','#cbb687']].forEach(([key,fill])=>{if(!finite(p[key]))return;ctx.beginPath();ctx.arc(x(state.index),y(p[key]),3.5,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.stroke();});
    state.chartGeometry={x,y,pad,width,height,chartWidth};
  }
  function chartIndex(event){const rect=$('#forecast-chart').getBoundingClientRect();const g=state.chartGeometry;if(!g||!state.predictions.length)return null;return Math.max(0,Math.min(state.predictions.length-1,Math.round((event.clientX-rect.left-g.pad.left)/g.chartWidth*(state.predictions.length-1))));}
  function renderMethodology(){
    const model=state.data.model||{},c=current();
    const updates=c.cluster_updated_range||[];
    const sorted=[...updates].sort();
    const block=(iconName,title,summary,body,open=false)=>`<details class="methodology-block method-accordion"${open?' open':''}><summary><h3>${icon(iconName)} ${title}</h3><span>${summary}</span></summary>${body}</details>`;
    const link=(href,label)=>`<a class="source-link" href="${escape(href)}" target="_blank" rel="noopener">${escape(label)} ${icon('arrow-up-right')}</a>`;
    $('#methodology-content').innerHTML=[
      block('map-trifold','Priority levels','A rule of thumb from people in active clusters, not a forecast.',`<table class="method-table"><tbody><tr><td>${badge('High')}</td><td>10 or more people in active clusters</td></tr><tr><td>${badge('Medium')}</td><td>An active cluster with fewer than 10 people</td></tr><tr><td>${badge('Low')}</td><td>No active cluster in this snapshot. Not the same as no risk.</td></tr></tbody></table>`,true),
      block('calendar-dots','Data dates',`Clusters ${date(c.as_of)} · national cases to Dec 2022.`,`<table class="method-table"><tbody><tr><td>Cluster snapshot</td><td>${date(c.as_of)}${sorted.length?` (NEA updates ${date(sorted[0])}–${date(sorted.at(-1))})`:''}</td></tr><tr><td>Weather</td><td>${date(c.weather_date)}, nearest station within 15 km</td></tr><tr><td>National reports</td><td>End Dec 2022, so the forecast is a 2022 replay</td></tr></tbody></table>`),
      block('chart-line-up','How the forecast was tested',`Chosen on 2019–2021, then tested on 2022.`,`<p>A simple average and two learned models were compared on 2019–2021, with each year weighted equally. The ${escape(modelLabel().toLowerCase())} model (gradient boosting) was locked before the 2022 evaluation.</p><table class="method-table"><tbody><tr><td>Usually off by</td><td>Average absolute weekly error</td></tr><tr><td>High</td><td>At least ${number(model.thresholds?.high,1)} reported people a week</td></tr><tr><td>Lead time</td><td>First High forecast to the observed peak: ${escape(leadText(model.peak_lead_time?.selected).toLowerCase())} (simple average: ${escape(leadText(model.peak_lead_time?.baseline).toLowerCase())})</td></tr></tbody></table>`),
      block('bug','Why two weeks?','About a week from egg to mosquito, then days to symptoms.',`<p>Aedes can develop from egg to adult in about a week. Symptoms can begin 4–10 days after an infected bite. The timing varies, so clearing standing water early interrupts breeding.</p>${link('https://www.nea.gov.sg/dengue-zika/stop-dengue-now','NEA: Mozzie Wipeout')}${link('https://www.who.int/news-room/fact-sheets/detail/dengue-and-severe-dengue','WHO: dengue symptoms')}`),
      block('warning-circle','Limitations','What these numbers can’t tell you.',`<ul><li>A cluster crossing a boundary counts in both areas, so area totals shouldn’t be added up. National totals count each cluster once.</li><li>Counts are people in current clusters, not new infections this week or population-adjusted risk.</li><li>Priority thresholds are assumptions. Missing weather adds nothing; construction-site data is not scored.</li><li>The 2022 results had been viewed during earlier development.</li><li>Lead time doesn’t show that the model predicted when the peak would occur.</li><li>We assume each week’s report is available at the start of the following week.</li><li>Weather and explanation bars show associations, not causes.</li><li>Local forecast accuracy can’t be measured without historical local outcomes.</li></ul>`),
      block('database','Sources','Real, open data. No synthetic outcomes.',`<p>Boundaries use the indicative URA 2025 plan. Export data includes the detailed method and model results.</p>${(meta().sources||[]).slice(0,3).map(src=>link(src.url,src.name)).join('')}`)
    ].join('');
  }

  function bindEvents(){
    $('#replay-button').addEventListener('click',toggleReplay);
    $$('[data-about]').forEach(b=>b.addEventListener('click',()=>$('#about-dialog').showModal()));
    $('#close-about').addEventListener('click',()=>$('#about-dialog').close());
    $('#about-done').addEventListener('click',()=>{$('#about-dialog').close();switchView('signals');});

    $$('[data-view]').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.view)));
    $$('.wordmark,.brand-mark').forEach(a=>a.addEventListener('click',()=>switchView('signals')));
    $$('[data-methodology]').forEach(b=>b.addEventListener('click',()=>$('#methodology-dialog').showModal()));
    $('#close-methodology').addEventListener('click',()=>$('#methodology-dialog').close());$('#methodology-done').addEventListener('click',()=>$('#methodology-dialog').close());
    $('#methodology-dialog').addEventListener('click',e=>{if(e.target===$('#methodology-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
    $('#area-search').addEventListener('input',e=>{state.search=e.target.value.toLowerCase().trim();renderAreas();});
    $$('.filter').forEach(b=>b.addEventListener('click',()=>setFilter(b.dataset.filter)));
    $('#layers-button').addEventListener('click',()=>{const menu=$('#layers-menu');menu.hidden=!menu.hidden;$('#layers-button').setAttribute('aria-expanded',String(!menu.hidden));});
    document.addEventListener('click',e=>{if(!e.target.closest('#layers-button')&&!e.target.closest('#layers-menu')){$('#layers-menu').hidden=true;$('#layers-button').setAttribute('aria-expanded','false');}});
    $('#toggle-areas').addEventListener('click',()=>setDrawer(!$('.explorer').classList.contains('show-areas')));
    $('#close-areas').addEventListener('click',()=>setDrawer(false,true));
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('.explorer').classList.contains('show-areas'))setDrawer(false,true);});
    $('#forecast-week').addEventListener('input',e=>{stopReplay();state.index=Number(e.target.value);renderPrediction();});
    $('#forecast-chart').addEventListener('click',e=>{stopReplay();const i=chartIndex(e);if(i===null)return;state.index=i;$('#forecast-week').value=i;renderPrediction();});
    $('#forecast-chart').addEventListener('mousemove',e=>{const i=chartIndex(e);if(i===null)return;const p=state.predictions[i],tooltip=$('#chart-tooltip');tooltip.hidden=false;tooltip.innerHTML=`<strong>Week of ${date(p.target_date)}</strong><div class="tooltip-row"><span>Observed</span><strong>${number(p.actual)}</strong></div><div class="tooltip-row"><span>Model</span><strong>${number(p.predicted)}</strong></div><div class="tooltip-row"><span>Baseline</span><strong>${number(p.baseline)}</strong></div>`;const rect=$('#forecast-chart').getBoundingClientRect();tooltip.style.left=`${Math.max(0,Math.min(rect.width-180,e.clientX-rect.left+14))}px`;tooltip.style.top=`${Math.max(0,e.clientY-rect.top-95)}px`;});
    $('#forecast-chart').addEventListener('mouseleave',()=>$('#chart-tooltip').hidden=true);
    $('#download-data').addEventListener('click',()=>{if(!state.data)return toast('The saved data is still loading.');const blob=new Blob([JSON.stringify(state.data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`denguesux-evidence-${current().weather_date||'snapshot'}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Dashboard data saved.');});
    window.addEventListener('hashchange',()=>switchView(location.hash==='#forecast'?'forecast':'signals'));
    window.addEventListener('resize',()=>{if(state.map&&state.view==='signals'){state.map.invalidateSize();state.map.fitBounds(state.areaLayer.getBounds(),{padding:[24,24],animate:false});}drawChart();});
  }
  async function init(){
    bindEvents();
    document.body.classList.add('is-loading');
    const loadingCopy=$('.loading-copy>p:last-child');
    const slowLoad=setTimeout(()=>{loadingCopy.textContent='Still loading the saved evidence. This may take a moment on a slower connection.';},7000);
    try{
      if(window.DENGUESUX_DATA)state.data=window.DENGUESUX_DATA;
      else{const response=await fetch('/data/dashboard.json',{cache:'no-cache',signal:AbortSignal.timeout(20000)});if(!response.ok)throw new Error(`Saved artifact unavailable (HTTP ${response.status}). Run the prototype pipeline, then reload.`);state.data=await response.json();}
      loadingCopy.textContent='Preparing area details, inspection plans and the forecast replay.';
      await window.Fieldwork.load(state.data,{toast,open:()=>{state.view='inspection';stopReplay();},back:()=>switchView('signals')});
      $('#loading-state').hidden=true;$('#signals-view').hidden=false;
      renderCurrent();renderModel();renderMethodology();ready=true;switchView(location.hash==='#forecast'?'forecast':'signals');
      $('#main').setAttribute('aria-busy','false');
      document.body.classList.remove('is-loading');
      document.body.classList.add('is-ready');
      const areaFor=code=>state.areas.find(a=>a.code===code);
      window.Assistant?.init(state.data,{
        selectArea:code=>{switchView('signals');selectArea(code,true);$('.explorer').scrollIntoView({block:'start',behavior:reducedMotion()?'instant':'smooth'});},
        openPlan:code=>{const area=areaFor(code);if(!area)return;switchView('signals');selectArea(code);window.Fieldwork.openPlan(area);},
        openNotice:code=>{const area=areaFor(code);if(area)window.Fieldwork.openNotice(area);},
        showWeek:index=>{switchView('forecast');stopReplay();state.index=index;$('#forecast-week').value=index;renderPrediction();$('.forecast-chart-card').scrollIntoView({block:'center',behavior:reducedMotion()?'instant':'smooth'});}
      });
    }catch(error){ready=false;$('#loading-state').hidden=true;$('#signals-view').hidden=true;$('#forecast-view').hidden=true;$('#error-state').hidden=false;$('#error-message').textContent=error.name==='TimeoutError'?'The saved evidence is taking too long to load. Please try again.':'We couldn’t load the saved evidence. Please try again in a moment.';$('#data-timestamp').textContent='Evidence unavailable';$('#main').setAttribute('aria-busy','false');document.body.classList.remove('is-loading');document.body.classList.add('is-error');console.error('DengueSUX:',error);}finally{clearTimeout(slowLoad);}
  }
  init();
})();
