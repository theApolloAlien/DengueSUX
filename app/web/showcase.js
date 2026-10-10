/* Showcase answers: tappable prompts answered with maps, charts and diagrams drawn from the saved, dated data.
   Nothing here calls a model or invents a number; every figure is read from the dashboard bundle. */
(() => {
 'use strict';
 const C=()=>window.ChatHome,fin=Number.isFinite;
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const num=(v,d=0)=>fin(v)?Number(v).toLocaleString('en-SG',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
 const icon=n=>`<i class="ph ph-${n}" aria-hidden="true"></i>`;
 const day=(v,o={day:'numeric',month:'short'})=>v?new Date(String(v).length===10?v+'T12:00:00+08:00':v).toLocaleDateString('en-SG',{...o,timeZone:'Asia/Singapore'}):'—';
 const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
 const slug=n=>String(n).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/-$/,'');
 const RISK={High:'#ff7a5c',Medium:'#f3b847',Low:'#2c6150'};
 const DEMO=['hotspots','outlook','drivers','route','accuracy','how'];
 let data,geo,seq=0,demo=null,narrow=false;
 const uid=p=>p+(++seq);
 const live=()=>data?.model?.live_forecast?.available!==false?data?.model?.live_forecast:null;
 const head=()=>live()?.headline;
 const topArea=()=>data.current.areas.find(a=>a.cluster_count&&data.inspection?.areas?.[a.code]?.stops?.length);
 const active=()=>data.current.areas.filter(a=>a.cluster_count>0);
 function usual(h){const m=h?.normal?.median,r=fin(h?.prediction)&&fin(m)?h.prediction/Math.max(m,1):null;return r==null?null:r<.8?['quieter','Quieter than usual']:r>1.25?['busier','Busier than usual']:['usual','About usual'];}

 function prompts(){
  const t=data.current.totals||{},a=topArea(),h=head(),stops=a?data.inspection.areas[a.code].stops.length:0;
  return [
   {id:'demo',featured:true,icon:'play',title:'Play the demo briefing',sub:`${DEMO.length} visual steps: hotspots, forecast, a field walk and how it works. Press Next as you talk.`,q:'Walk me through this week'},
   {id:'hotspots',icon:'map-trifold',title:'Map this week’s hotspots',sub:`${num(t.clusters)} clusters across ${active().length} areas`,q:'Show this week’s hotspots on a map'},
   {id:'outlook',icon:'chart-line-up',title:'Forecast for next week',sub:h?`About ${num(h.prediction)} people, with its range`:'Latest official reports',q:'Show next week’s forecast',hide:!h},
   a&&{id:'route',icon:'path',title:`Walk a check in ${a.name}`,sub:`${stops} stops on a saved walking route`,q:`Plan a walk in ${a.name}`,area:a.code},
   {id:'drivers',icon:'chart-bar-horizontal',title:'What drives the forecast?',sub:'From the model’s average week to this one',q:'What is driving the forecast?',hide:!h?.top_features?.length},
   {id:'accuracy',icon:'target',title:'How accurate is it?',sub:`${num(data.model.prospective?.overall?.n)} weeks checked since 2023`,q:'How accurate is the forecast?',hide:!data.model.prospective?.overall},
   {id:'changes',icon:'arrows-clockwise',title:'What changed lately?',sub:'New, growing and closed clusters',q:'What changed since the last snapshot?',hide:!data.growth?.changes?.summary},
   {id:'how',icon:'flow-arrow',title:'How does DengueSUX work?',sub:'Open data to field plan, on Databricks',q:'How does DengueSUX work?'},
  ].filter(p=>p&&!p.hide);
 }
 function gallery(host){
  if(!host||host.querySelector('.showcase'))return;
  const box=document.createElement('section');box.className='showcase';box.setAttribute('aria-labelledby','showcase-title');
  box.innerHTML=`<h2 id="showcase-title">Explore visually</h2><div class="showcase-grid">${prompts().map((p,i)=>`<button type="button" class="showcase-card${p.featured?' is-featured':''}" data-showcase="${p.id}" style="--i:${i}"><span class="showcase-icon">${icon(p.icon)}</span><span class="showcase-copy"><strong>${esc(p.title)}</strong><small>${esc(p.sub)}</small></span>${p.featured?'<span class="showcase-wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>':icon('arrow-right')}</button>`).join('')}</div>`;
  host.append(box);box.addEventListener('click',e=>{const b=e.target.closest('[data-showcase]');if(b)press(b.dataset.showcase);});
 }
 function press(id){
  if(id==='demo')return startDemo();
  const p=prompts().find(p=>p.id===id);if(p)C().visual(id,p.q,{area:p.area});
 }
 function lead(id,t={}){
  const tot=data.current.totals||{},h=head(),u=usual(h);
  if(id==='hotspots'){const top=active().sort((a,b)=>b.cluster_cases-a.cluster_cases);return `${num(tot.clusters)} active clusters with ${num(tot.cluster_cases)} people, across ${top.length} planning areas. ${top.slice(0,2).map(a=>a.name).join(' and ')} lead the list.`;}
  if(id==='outlook')return h?`About ${num(h.prediction)} people are expected in the week of ${day(h.target_date,{day:'numeric',month:'long'})}${u?`, ${u[1].toLowerCase()} for this time of year`:''}.`:'The current outlook is unavailable from the saved official reports.';
  if(id==='drivers')return h?`The model starts from its average week (${num(h.explanation_base)}) and lands on ${num(h.prediction)}. Recent cases explain most of the gap.`:'';
  if(id==='route'){const a=data.current.areas.find(a=>a.code===t.area)||topArea(),p=data.inspection?.areas?.[a?.code];return p?`A ${num((p.route?.distance_m||0)/1000,1)} km walk past ${p.stops.length} places near ${a.name}’s active clusters.`:'No saved route for this area.';}
  if(id==='accuracy'){const o=data.model.prospective.overall;return `Across ${num(o.n)} weeks since 2023, the forecast was off by ${num(o.selected.mae,1)} people a week on average, ${num(o.error_reduction*100)}% less than a four-week average.`;}
  if(id==='changes'){const g=data.growth.changes,s=g.summary;return `Between ${day(g.from_date)} and ${day(g.to_date)}: ${s.new} new, ${s.growing} growing and ${s.closed} closed clusters.`;}
  if(id==='how')return 'DengueSUX turns Singapore’s open data into a weekly plan. Daily serverless jobs on Databricks keep it current.';
  return '';
 }
 function sources(id){
  const meta=n=>(data.meta?.sources||[]).find(s=>s.name.includes(n))?.url;
  const nea={name:'NEA dengue clusters',url:'https://www.nea.gov.sg/dengue-zika/dengue/dengue-clusters',date:data.current.as_of},moh={name:'Weekly national infectious disease bulletin (MOH/CDA)',url:meta('infectious disease'),date:live()?.issued_from_week_end||data.model.latest_label};
  return {hotspots:[nea],outlook:[moh],drivers:[moh],accuracy:[moh],route:[nea,{name:'OneMap walking route · HDB footprints',url:'https://www.onemap.gov.sg/',date:data.inspection?.generated_at}],changes:[nea],how:[nea,moh]}[id]||[];
 }

 // ---- Map geometry: URA planning areas, projected once and lightly simplified for SVG. ----
 function polys(g){return g?.type==='Polygon'?[g.coordinates]:g?.type==='MultiPolygon'?g.coordinates:[];}
 function projector(lon0,lat1,k,s){return ([x,y])=>[(x-lon0)*k*s,(lat1-y)*s];}
 function pathFor(g,P,tol=1.2){return polys(g).map(p=>p.map(r=>{let out=[],last=null;for(const c of r){const q=P(c);if(!last||Math.hypot(q[0]-last[0],q[1]-last[1])>tol){out.push(q);last=q;}}return out.length>2?'M'+out.map(q=>q[0].toFixed(1)+' '+q[1].toFixed(1)).join('L')+'Z':'';}).join('')).join('');}
 function island(){
  if(geo)return geo;const feats=data.current.boundaries?.features||[];if(!feats.length)return null;
  const lon0=103.6,lon1=104.09,lat0=1.155,lat1=1.475,k=Math.cos(1.33*Math.PI/180),W=800,s=W/((lon1-lon0)*k),H=Math.round((lat1-lat0)*s),P=projector(lon0,lat1,k,s);
  const by=new Map(data.current.areas.map(a=>[a.code,a]));
  const areas=feats.map(f=>{const a=by.get(f.properties.code)||{};return {code:f.properties.code,name:a.name||f.properties.name,risk:a.risk||'Low',people:a.cluster_cases||0,clusters:a.cluster_count||0,d:pathFor(f.geometry,P),c:a.centroid?P([a.centroid[1],a.centroid[0]]):null};});
  const clusters=(data.current.clusters?.features||[]).map(f=>{const pts=polys(f.geometry).flat(2);return {name:f.properties.name,people:f.properties.cases,c:P([pts.reduce((t,p)=>t+p[0],0)/pts.length,pts.reduce((t,p)=>t+p[1],0)/pts.length])};});
  return geo={W,H,areas,clusters};
 }
 // Nudge numbered markers apart so neighbouring areas (Jurong West and East) never overlap (viewBox units).
 function place(items){const r=17,done=[];return items.map(it=>{for(const [dx,dy] of [[0,0],[0,-2*r],[2*r,0],[-2*r,0],[0,2*r],[1.6*r,-1.6*r],[-1.6*r,-1.6*r]]){const x=it.c[0]+dx,y=it.c[1]+dy;if(!done.some(o=>Math.hypot(o.x-x,o.y-y)<2*r+2)){done.push({x,y});return {...it,x,y};}}return {...it,x:it.c[0],y:it.c[1]};});}
 function stat(v,label,d=0){return `<div class="viz-stat"><b data-count="${fin(v)?v:''}" data-dp="${d}">${num(v,d)}</b><span>${esc(label)}</span></div>`;}

 function hotspots(el){
  const g=island(),t=data.current.totals||{},list=active().sort((a,b)=>b.cluster_cases-a.cluster_cases),top=list.slice(0,6),max=Math.max(1,...top.map(a=>a.cluster_cases)),grad=uid('halo');
  const pins=g?place(top.map(a=>g.areas.find(x=>x.code===a.code)).filter(a=>a?.c)):[];
  const map=g?`<figure class="viz-map" style="aspect-ratio:${g.W}/${g.H}"><svg viewBox="0 0 ${g.W} ${g.H}" role="img" aria-label="Map of Singapore’s ${g.areas.length} planning areas coloured by priority, with ${num(t.clusters)} active dengue clusters"><defs><radialGradient id="${grad}"><stop offset="0" stop-color="#ff5a3c" stop-opacity=".75"/><stop offset="1" stop-color="#ff5a3c" stop-opacity="0"/></radialGradient></defs>
   <g class="viz-areas">${g.areas.map(a=>`<path d="${a.d}" class="area risk-${a.risk.toLowerCase()}" data-code="${esc(a.code)}" style="--d:${a.c?Math.round(a.c[0]/g.W*600):0}ms"/>`).join('')}</g>
   <g class="viz-clusters">${g.clusters.map((c,i)=>{const r=5+Math.sqrt(c.people)*1.9;return `<g transform="translate(${c.c[0].toFixed(1)} ${c.c[1].toFixed(1)})" style="--d:${800+i*110}ms"><circle class="halo" r="${(r*2.4).toFixed(1)}" fill="url(#${grad})"/><circle class="ring" r="${r.toFixed(1)}"/><circle class="core" r="${Math.max(3,r*.4).toFixed(1)}"/></g>`;}).join('')}</g>
   ${pins.filter(l=>l.x!==l.c[0]||l.y!==l.c[1]).map(l=>`<line class="viz-leader" x1="${l.c[0].toFixed(1)}" y1="${l.c[1].toFixed(1)}" x2="${l.x.toFixed(1)}" y2="${l.y.toFixed(1)}"/>`).join('')}</svg>
   ${pins.map((l,i)=>`<a class="viz-pin risk-${l.risk.toLowerCase()}" data-code="${esc(l.code)}" href="#map/${slug(l.name)}" aria-label="${i+1}. ${esc(l.name)}: ${num(l.people)} people" style="left:${(l.x/g.W*100).toFixed(2)}%;top:${(l.y/g.H*100).toFixed(2)}%;--d:${1100+i*110}ms">${i+1}</a>`).join('')}<div class="viz-tip" hidden></div></figure>`:'';
  el.innerHTML=`<div class="viz-stats">${stat(t.clusters,'active clusters')}${stat(t.cluster_cases,'people in clusters')}${stat(list.length,'areas affected')}</div>
   <div class="viz-split">${map}<div class="viz-side"><h4>People in active clusters</h4><ol class="viz-bars">${top.map((a,i)=>`<li style="--i:${i}" data-code="${esc(a.code)}"><a href="#plan/${slug(a.name)}" aria-label="${esc(a.name)}: ${a.cluster_cases} people. Open field plan"><span><em class="risk-${a.risk.toLowerCase()}">${i+1}</em>${esc(a.name)}</span><b>${num(a.cluster_cases)}</b><i style="--w:${(a.cluster_cases/max).toFixed(3)};--c:${RISK[a.risk]}"></i></a></li>`).join('')}</ol>
   <div class="viz-legend"><span><b style="background:${RISK.High}"></b>High</span><span><b style="background:${RISK.Medium}"></b>Medium</span><span><b class="dot"></b>Cluster, sized by people</span></div></div></div>
   <p class="viz-source">NEA clusters saved ${day(data.current.as_of,{day:'numeric',month:'short',year:'numeric'})}. A cluster that crosses a boundary counts in both areas.</p>
   <div class="viz-actions"><a class="viz-button" href="#map">${icon('map-trifold')} Open the map</a><a class="viz-button ghost" href="#plan/${slug(list[0]?.name||'')}">${icon('footprints')} Plan a check in ${esc(list[0]?.name||'')}</a></div>`;
  if(!g)return;const tip=el.querySelector('.viz-tip'),fig=el.querySelector('.viz-map'),by=new Map(g.areas.map(a=>[a.code,a]));
  // Hovering a ranked row or a marker lights up the same area on the map.
  const hot=code=>{el.querySelectorAll('.is-hot').forEach(n=>n.classList.remove('is-hot'));if(code)el.querySelectorAll(`[data-code="${CSS.escape(code)}"]`).forEach(n=>n.classList.add('is-hot'));};
  el.querySelectorAll('.viz-bars li,.viz-pin').forEach(n=>{n.addEventListener('pointerenter',()=>hot(n.dataset.code));n.addEventListener('pointerleave',()=>hot(null));n.addEventListener('focusin',()=>hot(n.dataset.code));n.addEventListener('focusout',()=>hot(null));});
  fig.addEventListener('pointermove',e=>{const a=by.get(e.target.dataset?.code);if(!a){tip.hidden=true;return;}const r=fig.getBoundingClientRect();tip.hidden=false;tip.innerHTML=`<b>${esc(a.name)}</b><span>${a.people?`${num(a.people)} ${a.people===1?'person':'people'} · ${a.clusters} ${a.clusters===1?'cluster':'clusters'}`:'No active cluster'}</span>`;tip.style.left=Math.min(r.width-170,Math.max(0,e.clientX-r.left+12))+'px';tip.style.top=Math.max(0,e.clientY-r.top-58)+'px';});
  fig.addEventListener('pointerleave',()=>tip.hidden=true);
  fig.addEventListener('click',e=>{const a=e.target.tagName==='path'&&by.get(e.target.dataset?.code);if(a)window.Product?.go('map',a.code);});
 }

 // ---- Weekly chart shared by the outlook and the accuracy check. ----
 function weekly(past,ahead=[],opt={}){
  const rows=[...past.map(r=>({...r,kind:'past'})),...ahead.map(r=>({...r,kind:'ahead'}))];if(rows.length<3)return '';
  const W=narrow?420:760,H=narrow?230:opt.h||250,L=narrow?34:42,R=ahead.length?(narrow?40:56):(narrow?10:16),T=22,B=30,n=rows.length,top=Math.max(...rows.map(r=>Math.max(r.actual??0,r.upper??0,r.prediction??0)))*1.1||1,id=uid('wk');
  const x=i=>L+i*(W-L-R)/Math.max(1,n-1),y=v=>T+(H-T-B)*(1-v/top),pts=l=>l.map(([i,v])=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const band=(a,b)=>{const s=rows.map((r,i)=>[i,r]).slice(a,b).filter(([,r])=>fin(r.lower)&&fin(r.upper));return s.length>1?pts(s.map(([i,r])=>[i,r.upper]))+' '+pts(s.map(([i,r])=>[i,r.lower]).reverse()):'';};
  const split=past.length-1,step=Math.pow(10,Math.floor(Math.log10(top/2))),tick=Math.ceil(top/3/step)*step,ticks=[0,tick,tick*2,tick*3].filter(v=>v<top);
  const years=[];rows.forEach((r,i)=>{const yr=String(r.target_date).slice(0,4);if(i&&yr!==String(rows[i-1].target_date).slice(0,4))years.push([i,yr]);});
  const last=ahead.at(-1),li=n-1,model=rows.map((r,i)=>[i,r.prediction]).filter(([i,v])=>fin(v)&&i<=split);
  const svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.label||'Weekly reported dengue cases')}"><defs><linearGradient id="${id}a" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#f3b847" stop-opacity=".6"/><stop offset="1" stop-color="#f3b847" stop-opacity=".1"/></linearGradient><linearGradient id="${id}p" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#8fd1ab" stop-opacity=".28"/><stop offset="1" stop-color="#8fd1ab" stop-opacity=".04"/></linearGradient><linearGradient id="${id}f" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#cfe6d6" stop-opacity=".22"/><stop offset="1" stop-color="#cfe6d6" stop-opacity="0"/></linearGradient></defs>
   ${ticks.map(v=>`<line class="wk-grid" x1="${L}" x2="${W-R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text class="wk-axis" x="${L-8}" y="${(y(v)+4).toFixed(1)}" text-anchor="end">${num(v)}</text>`).join('')}
   ${years.map(([i,yr])=>`<line class="wk-year" x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${T}" y2="${H-B}"/><text class="wk-axis" x="${(x(i)+5).toFixed(1)}" y="${T+8}">${yr}</text>`).join('')}
   <polygon class="wk-band" points="${band(0,split+1)}" fill="url(#${id}p)"/>
   <polygon class="wk-fill" points="${x(0)},${H-B} ${pts(past.map((r,i)=>[i,r.actual]))} ${x(split)},${H-B}" fill="url(#${id}f)"/>
   <polyline class="wk-model" points="${pts(model)}"/>
   <polyline class="wk-actual" pathLength="1" points="${pts(past.map((r,i)=>[i,r.actual]))}"/>
   ${ahead.length?`<polygon class="wk-ahead-band" points="${band(split,n)}" fill="url(#${id}a)"/><line class="wk-now" x1="${x(split).toFixed(1)}" x2="${x(split).toFixed(1)}" y1="${T-8}" y2="${H-B}"/><text class="wk-now-label" x="${(x(split)-6).toFixed(1)}" y="${T-10+8}" text-anchor="end">Latest report</text>
   <polyline class="wk-ahead" points="${pts([[split,past.at(-1).actual],...ahead.map((r,i)=>[split+1+i,r.prediction])])}"/>
   ${ahead.map((r,i)=>fin(r.normal?.median)?`<line class="wk-normal" x1="${(x(split+1+i)-8).toFixed(1)}" x2="${(x(split+1+i)+8).toFixed(1)}" y1="${y(r.normal.median).toFixed(1)}" y2="${y(r.normal.median).toFixed(1)}"/>`:'').join('')}
   <circle class="wk-pulse" cx="${x(li).toFixed(1)}" cy="${y(last.prediction).toFixed(1)}" r="8"/><circle class="wk-dot ahead" cx="${x(li).toFixed(1)}" cy="${y(last.prediction).toFixed(1)}" r="6"/><text class="wk-value" x="${(x(li)+2).toFixed(1)}" y="${(y(last.prediction)-16).toFixed(1)}" text-anchor="middle">${num(last.prediction)}</text>`:''}
   <circle class="wk-dot" cx="${x(split).toFixed(1)}" cy="${y(past.at(-1).actual).toFixed(1)}" r="4.5"/>
   <line class="wk-cursor" x1="0" x2="0" y1="${T}" y2="${H-B}" hidden/>
   <text class="wk-axis" x="${L}" y="${H-8}">${day(rows[0].target_date,{month:'short',year:'numeric'})}</text><text class="wk-axis" x="${W-R}" y="${H-8}" text-anchor="end">${day(rows.at(-1).target_date,{day:'numeric',month:'short'})}</text></svg>`;
  return `<figure class="viz-chart${narrow?' is-narrow':''}" data-l="${L}" data-r="${R}">${svg}<div class="viz-tip" hidden></div><figcaption><span><b class="k actual"></b>Reported</span><span><b class="k model"></b>Model at the time</span><span><b class="k band"></b>80% range</span>${ahead.length?'<span><b class="k ahead"></b>Forecast</span><span><b class="k normal"></b>Typical week</span>':''}</figcaption></figure>`;
 }
 function chartHover(el,past,ahead=[]){
  const fig=el.querySelector('.viz-chart');if(!fig)return;const rows=[...past,...ahead],svg=fig.querySelector('svg'),tip=fig.querySelector('.viz-tip'),cur=svg.querySelector('.wk-cursor'),vb=svg.viewBox.baseVal,L=Number(fig.dataset.l),R=Number(fig.dataset.r);
  fig.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect(),vx=(e.clientX-r.left)/r.width*vb.width,i=Math.max(0,Math.min(rows.length-1,Math.round((vx-L)/(vb.width-L-R)*(rows.length-1)))),row=rows[i],cx=L+i*(vb.width-L-R)/Math.max(1,rows.length-1);
   cur.hidden=false;cur.setAttribute('x1',cx);cur.setAttribute('x2',cx);tip.hidden=false;
   tip.innerHTML=`<b>Week of ${day(row.target_date,{day:'numeric',month:'short',year:'numeric'})}</b>${fin(row.actual)?`<span>Reported <strong>${num(row.actual)}</strong></span>`:'<span>Not reported yet</span>'}${fin(row.prediction)?`<span>${fin(row.actual)?'Model said':'Forecast'} ${num(row.prediction)}${fin(row.lower)?` (${num(row.lower)}–${num(row.upper)})`:''}</span>`:''}`;
   const px=cx/vb.width*r.width;tip.style.left=Math.min(r.width-190,Math.max(0,px+12))+'px';tip.style.top='8px';});
  fig.addEventListener('pointerleave',()=>{tip.hidden=true;cur.hidden=true;});
 }
 function outlook(el){
  const lf=live(),h=head();if(!h){el.innerHTML='<p class="viz-empty">No current forecast is available from the saved official reports.</p>';return;}
  const past=(data.model.prospective?.predictions||[]).filter(r=>fin(r.actual)).slice(narrow?-18:-30),ahead=(lf.forecasts||[]).filter(r=>fin(r.prediction)),u=usual(h),n=h.normal;
  const scale=Math.max(h.upper,n?.high??0,h.prediction)*1.06||1,pos=v=>(Math.max(0,Math.min(1,v/scale))*100).toFixed(2)+'%';
  el.innerHTML=`<div class="viz-head"><div><span class="viz-kicker">Week of ${day(h.target_date,{day:'numeric',month:'long'})}</span><div class="viz-hero"><b data-count="${Math.round(h.prediction)}">${num(h.prediction)}</b><span>people expected nationally</span></div><p>${num(h.lower)}–${num(h.upper)} · 80% range. Past error, not a guarantee.</p></div>${u?`<span class="viz-chip ${u[0]}">${u[1]}</span>`:''}</div>
   ${weekly(past,ahead,{label:`Reported weekly cases for ${past.length} weeks, then the forecast of about ${num(h.prediction)} for the week of ${day(h.target_date)}`})}
   ${n?`<div class="viz-gauge" role="img" aria-label="Forecast ${num(h.lower)} to ${num(h.upper)}; typical weeks ${num(n.low)} to ${num(n.high)}, median ${num(n.median)}"><div class="g-track"><span class="g-normal" style="left:${pos(n.low)};width:calc(${pos(n.high)} - ${pos(n.low)})"></span><span class="g-range" style="left:${pos(h.lower)};width:calc(${pos(h.upper)} - ${pos(h.lower)})"></span><span class="g-median" style="left:${pos(n.median)}"></span><span class="g-point" style="left:${pos(h.prediction)}"></span></div><div class="g-labels"><span style="left:${pos(h.prediction)}">This week ${num(h.prediction)}</span><span style="left:${pos(n.median)}">Typical ${num(n.median)}</span></div><small>Typical: the same week in ${esc(n.years)}, from ${num(n.low)} to ${num(n.high)}.</small></div>`:''}
   <p class="viz-source">Official weekly reports through ${day(lf.issued_from_week_end,{day:'numeric',month:'short',year:'numeric'})} (${esc(lf.latest_epi_week||'')}).</p>
   <div class="viz-actions"><a class="viz-button" href="#forecast">${icon('chart-line-up')} Open the forecast</a></div>`;
  chartHover(el,past,ahead);
 }
 function drivers(el){
  const h=head();if(!h?.top_features?.length){el.innerHTML='<p class="viz-empty">Forecast explanations are unavailable.</p>';return;}
  let run=h.explanation_base;const steps=[{label:'Model’s average week',from:0,to:run,kind:'base'}];
  h.top_features.forEach(f=>{steps.push({label:f.feature,from:run,to:run+f.value,kind:f.value<0?'down':'up',delta:f.value});run+=f.value;});
  steps.push({label:`Week of ${day(h.target_date)}`,from:0,to:h.prediction,kind:'end'});
  const max=Math.max(...steps.map(s=>Math.max(s.from,s.to)))*1.05,p=v=>(Math.max(0,v)/max*100).toFixed(2);
  el.innerHTML=`<div class="viz-head"><div><span class="viz-kicker">Why about ${num(h.prediction)}?</span><div class="viz-hero small"><b>${num(h.explanation_base)}</b><span>${icon('arrow-right')}</span><b data-count="${Math.round(h.prediction)}">${num(h.prediction)}</b></div><p>Each bar moves the forecast from the model’s average week toward this one.</p></div></div>
   <ol class="viz-waterfall">${steps.map((s,i)=>`<li class="${s.kind}" style="--i:${i}"><span class="w-label">${esc(s.label)}</span><span class="w-track"><i style="left:${p(Math.min(s.from,s.to))}%;width:max(3px,${(p(Math.max(s.from,s.to))-p(Math.min(s.from,s.to))).toFixed(2)}%)"></i></span><b>${s.delta!=null?(s.delta<0?'−':'+')+num(Math.abs(s.delta)):num(s.to)}</b></li>`).join('')}</ol>
   <div class="viz-legend"><span><b style="background:#8fd1ab"></b>Pulls the forecast down</span><span><b style="background:#ff8f73"></b>Pushes it up</span></div>
   <p class="viz-source">${esc(h.explanation_method||'Model explanation')} for the forecast issued ${day(h.issue_date)}. These show what the model associated with this number, not causes.</p>`;
 }
 function accuracy(el){
  const pr=data.model.prospective,o=pr.overall,rows=(pr.predictions||[]).filter(r=>fin(r.actual)),years=Object.entries(pr.by_year||{}),cov=o.interval_coverage,R=46,circ=2*Math.PI*R;
  const ymax=Math.max(...years.flatMap(([,v])=>[v.selected.mae,v.baseline.mae]))*1.08;
  el.innerHTML=`<div class="viz-stats">${stat(o.n,'weeks checked')}${stat(o.selected.mae,'people a week, average error',1)}${stat(Math.round(o.error_reduction*100),'% lower than a four-week average')}</div>
   ${weekly(rows,[],{h:230,label:`Reported weekly cases and the model’s forecast at the time, ${rows.length} weeks from ${day(rows[0]?.target_date)} to ${day(rows.at(-1)?.target_date)}`})}
   <div class="viz-split even"><div class="viz-compare"><h4>Average error, people a week</h4>${[['DengueSUX forecast',o.selected.mae,'#8fd1ab'],['Four-week average',o.baseline.mae,'#7f978a']].map(([l,v,c],i)=>`<div class="c-row" style="--i:${i}"><span>${l}</span><span class="c-track"><i style="--w:${(v/o.baseline.mae).toFixed(3)};--c:${c}"></i></span><b>${num(v,1)}</b></div>`).join('')}
    <h4>By year</h4><div class="viz-years">${years.map(([yr,v],i)=>`<div style="--i:${i}"><span class="y-bars"><i style="--h:${(v.selected.mae/ymax).toFixed(3)}" title="Forecast ${num(v.selected.mae,1)}"></i><i class="base" style="--h:${(v.baseline.mae/ymax).toFixed(3)}" title="Four-week average ${num(v.baseline.mae,1)}"></i></span><b>${yr}</b><small>${v.error_reduction>=0?`${num(v.error_reduction*100)}% better`:`${num(-v.error_reduction*100)}% worse`}</small></div>`).join('')}</div></div>
   <div class="viz-ring"><svg viewBox="0 0 120 120" role="img" aria-label="${num(cov*100)}% of weeks fell inside the 80% range"><circle cx="60" cy="60" r="${R}" class="r-bg"/><circle cx="60" cy="60" r="${R}" class="r-target" stroke-dasharray="${(circ*.8).toFixed(1)} ${circ.toFixed(1)}"/><circle cx="60" cy="60" r="${R}" class="r-value" stroke-dasharray="${(circ*cov).toFixed(1)} ${circ.toFixed(1)}" style="--c:${circ.toFixed(1)}"/></svg><div><b data-count="${Math.round(cov*100)}">${num(cov*100)}</b><span>%</span></div><p>of weeks landed inside the 80% range (aim: 80%).</p></div></div>
   <p class="viz-source">Retrospective check ${esc(pr.window||'')}: recipe fixed on 2019–2021, refitted each year on earlier reports only. Lower error is better.</p>`;
  chartHover(el,rows);
 }
 function route(el,t={}){
  const a=data.current.areas.find(x=>x.code===t.area)||topArea(),p=data.inspection?.areas?.[a?.code],line=p?.route?.geometry?.coordinates||[];
  if(!p?.stops?.length||line.length<2){el.innerHTML='<p class="viz-empty">No saved route for this area.</p>';return;}
  const pts=[...line,...p.stops.map(s=>[s.longitude,s.latitude])],lons=pts.map(q=>q[0]),lats=pts.map(q=>q[1]),k=Math.cos(lats[0]*Math.PI/180);
  let x0=Math.min(...lons),x1=Math.max(...lons),y0=Math.min(...lats),y1=Math.max(...lats);const padx=(x1-x0)*.14+.0006,pady=(y1-y0)*.14+.0006;x0-=padx;x1+=padx;y0-=pady;y1+=pady;
  // Widen the shorter side so the route sits centred in a 720 × 440 frame.
  const W=720,H=440,gw=(x1-x0)*k,gh=y1-y0;if(gw/gh<W/H){const e=(W/H*gh-gw)/k/2;x0-=e;x1+=e;}else{const e=(gw*H/W-gh)/2;y0-=e;y1+=e;}
  const s=W/((x1-x0)*k),P=([x,y])=>[(x-x0)*k*s,(y1-y)*s],in_=f=>polys(f.geometry).flat(2).some(([x,y])=>x>x0&&x<x1&&y>y0&&y<y1);
  const blocks=(data.footprints?.areas?.[a.code]?.features||[]).filter(in_),clusters=(p.clusters?.features||[]).filter(in_),rid=uid('route'),d='M'+line.map(c=>P(c).map(v=>v.toFixed(1)).join(' ')).join('L');
  const km=(p.route.distance_m||0)/1000,mins=Math.round((p.route.walking_seconds||0)/60),homes=p.impact?.homes_in_route_blocks,checks=p.stops[0].checklist||[];
  const order=p.stops.map(s=>{const sp=P([s.longitude,s.latitude]);let best=0,bd=Infinity;line.forEach((c,i)=>{const q=P(c),dd=Math.hypot(q[0]-sp[0],q[1]-sp[1]);if(dd<bd){bd=dd;best=i;}});return best/(line.length-1);});
  const draw=Math.max(2.4,Math.min(4,km*1.6)),dur=Math.max(9,Math.min(20,km*8));
  el.innerHTML=`<div class="viz-stats">${stat(p.stops.length,'places to check')}${stat(km,'km walking route',1)}${fin(mins)&&mins?stat(mins,'minutes on foot'):''}${fin(homes)?stat(homes,'homes in these blocks'):''}</div>
   <div class="viz-split"><figure class="viz-routemap" style="aspect-ratio:${W}/${H}"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Walking route through ${p.stops.length} places to check in ${esc(a.name)}, ${num(km,1)} km">
    <g class="r-blocks">${blocks.map((f,i)=>`<path d="${pathFor(f.geometry,P,.6)}" style="--d:${(i%24)*25}ms"/>`).join('')}</g>
    <g class="r-clusters">${clusters.map(f=>`<path d="${pathFor(f.geometry,P,.8)}"/>`).join('')}</g>
    <path id="${rid}" class="r-path-shadow" d="${d}"/><path class="r-path" d="${d}" pathLength="1" style="--dur:${draw.toFixed(1)}s"/>
    ${reduced()?'':`<circle class="r-walker" r="7"><animateMotion dur="${dur.toFixed(1)}s" begin="${(draw+.4).toFixed(1)}s" repeatCount="indefinite" rotate="0"><mpath href="#${rid}"/></animateMotion></circle>`}
    ${p.stops.map((s,i)=>{const [x,y]=P([s.longitude,s.latitude]);return `<g class="r-stop" transform="translate(${x.toFixed(1)} ${y.toFixed(1)})" style="--d:${Math.round(300+order[i]*draw*1000)}ms"><circle r="13"/><text y="4.5" text-anchor="middle">${s.number||i+1}</text></g>`;}).join('')}</svg>
    <figcaption><span><b class="k route"></b>Walking route</span><span><b class="k cluster"></b>Cluster footprint</span><span><b class="k block"></b>HDB block</span></figcaption></figure>
   <div class="viz-side"><h4>${esc(a.name)} · in order</h4><ol class="viz-stops">${p.stops.map((s,i)=>`<li style="--i:${i}"><span>${s.number||i+1}</span>${esc(s.name)}</li>`).join('')}</ol>${checks.length?`<h4>At each stop</h4><ul class="viz-checks">${checks.map(c=>`<li>${icon('check-circle')}${esc(c)}</li>`).join('')}</ul>`:''}</div></div>
   <p class="viz-source">Places to check, not confirmed breeding sites. OneMap route and HDB footprints saved ${day(p.as_of||data.inspection.as_of)}.</p>
   <div class="viz-actions"><a class="viz-button" href="#plan/${slug(a.name)}">${icon('footprints')} Open the field plan</a><button class="viz-button ghost" type="button" data-walk3d="${slug(a.name)}">${icon('cube')} Walk it in 3D</button></div>`;
  el.querySelector('[data-walk3d]').onclick=e=>{location.hash='#plan/'+e.currentTarget.dataset.walk3d;let tries=0;const t=setInterval(()=>{const b=document.querySelector('[data-map-mode="3d"]');if(b&&b.offsetParent){clearInterval(t);b.click();}else if(++tries>30)clearInterval(t);},100);};
 }
 function changes(el){
  const g=data.growth.changes,s=g.summary,parts=[['new','New',s.new,'#ff7a5c'],['growing','Growing',s.growing,'#f3b847'],['stable','Stable',s.stable,'#8fd1ab'],['shrinking','Shrinking',s.shrinking,'#5fa98a'],['closed','Closed',s.closed,'#56786b']].filter(p=>p[2]>0),total=parts.reduce((t,p)=>t+p[2],0)||1,items=g.items||[];
  el.innerHTML=`<div class="viz-then-now"><div><span>${day(g.from_date)}</span><b>${num(s.clusters_then)}</b><small>clusters · ${num(s.people_then)} people</small></div><div class="tn-arrow" aria-hidden="true"><i></i>${icon('arrow-right')}<small>${num(g.days)} days</small></div><div class="now"><span>${day(g.to_date)}</span><b data-count="${s.clusters_now}">${num(s.clusters_now)}</b><small>clusters · ${num(s.people_now)} people</small></div></div>
   <div class="viz-stack" role="img" aria-label="${parts.map(p=>`${p[2]} ${p[1].toLowerCase()}`).join(', ')}">${parts.map((p,i)=>`<span style="--w:${(p[2]/total*100).toFixed(2)}%;--c:${p[3]};--i:${i}" title="${p[1]}: ${p[2]}"><b>${p[2]}</b>${p[1]}</span>`).join('')}</div>
   <ul class="viz-changelist">${items.slice(0,8).map((c,i)=>`<li style="--i:${i}"><span class="ch-kind ${esc(String(c.kind).toLowerCase())}">${esc(c.label||c.kind)}</span><span class="ch-name">${esc(String(c.locality||'').split(' / ')[0])}</span><b>${fin(c.people)?num(c.people)+' people':''}${fin(c.change)&&c.change?` <small>${c.change>0?'+':'−'}${num(Math.abs(c.change))}</small>`:''}</b></li>`).join('')}</ul>
   <p class="viz-source">${esc(g.note||'Compares the two latest saved snapshots.')}</p>`;
 }
 function how(el){
  const t=data.current.totals||{},lf=live(),pr=data.model.prospective?.overall,notices=Object.keys(data.notices?.notices||{}).length*Object.keys(data.notices?.languages||{}).length,stops=Object.values(data.inspection?.areas||{}).reduce((n,a)=>n+(a.stops?.length||0),0);
  const cols=[
   ['database','Open data',['NEA dengue clusters, daily','MOH/CDA weekly case reports','NEA weather stations','HDB, URA and OneMap maps','SingStat population']],
   ['stack','Databricks lakehouse',['Unity Catalog Volume lands each file','Auto Loader ingests what is new','Bronze → Silver → Gold Delta tables','Serverless jobs, daily at 08:15 SGT','MLflow logs the selected model']],
   ['lightning','Models and rules',[`Weekly forecast with an 80% range${lf?` · ${num(lf.training_rows)} weeks to learn from`:''}`,`Back-tested on ${num(pr?.n)} weeks since 2023`,'Areas ranked by people in active clusters',`${num(stops)} places to check on walking routes`]],
   ['users-three','What people get',['This week: where to check first','Field plans with a 3D walk',`${num(notices)} resident notices in 4 languages`,'Ask DengueSUX, with Genie SQL']],
  ];
  el.innerHTML=`<div class="viz-flow">${cols.map(([ic,h,items],i)=>`<section class="flow-col${i===1?' is-core':''}" style="--i:${i}"><header>${icon(ic)}<h4>${h}</h4></header><ul>${items.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></section>${i<cols.length-1?'<span class="flow-link" aria-hidden="true"><i></i><i></i><i></i></span>':''}`).join('')}</div>
   <div class="viz-stats">${stat(t.areas||55,'planning areas scored')}${stat(t.clusters,'clusters tracked today')}${stat(pr?.n,'weeks back-tested')}${stat(notices,'notice drafts')}</div>
   <p class="viz-source">Same open data, same numbers, from the field sheet to the forecast. Each number carries its source date.</p>`;
 }
 const RENDER={hotspots,outlook,drivers,accuracy,route,changes,how};
 function render(container,id,t={}){
  if(!RENDER[id]||!data)return;narrow=!!container.closest('.ask-panel')||innerWidth<1100;const el=document.createElement('section');el.className=`viz viz-${id}`;el.setAttribute('aria-label',(prompts().find(p=>p.id===id)?.title)||'Visual answer');
  try{RENDER[id](el,t);}catch(e){console.error('DengueSUX visual:',e);el.innerHTML='<p class="viz-empty">This view could not be drawn from the saved data.</p>';}
  if(!demo||!t.demo){const next=prompts().filter(p=>p.id!==id&&p.id!=='demo').slice(0,8),i=next.findIndex(p=>DEMO.indexOf(p.id)>DEMO.indexOf(id));const pick=[...next.slice(Math.max(0,i)),...next.slice(0,Math.max(0,i))].slice(0,3);
   el.insertAdjacentHTML('beforeend',`<div class="viz-next"><span>Explore next</span>${pick.map(p=>`<button type="button" data-showcase="${p.id}">${icon(p.icon)}${esc(p.title)}</button>`).join('')}</div>`);
   el.querySelector('.viz-next').addEventListener('click',e=>{const b=e.target.closest('[data-showcase]');if(b)press(b.dataset.showcase);});}
  container.append(el);animate(el);
 }
 // Count numbers up once the view is on screen. The final value is in the HTML first, so a paused tab still shows it.
 function animate(el){
  if(reduced())return;el.classList.add('is-animating');
  const io=new IntersectionObserver(es=>es.forEach(e=>{if(!e.isIntersecting)return;io.disconnect();el.classList.add('is-in');
   el.querySelectorAll('[data-count]').forEach(n=>{const end=Number(n.dataset.count),dp=Number(n.dataset.dp||0);if(!fin(end)||n.dataset.count==='')return;const t0=performance.now(),dur=1100;
    const tick=now=>{const k=Math.min(1,(now-t0)/dur),v=end*(1-Math.pow(1-k,3));n.textContent=num(v,dp);if(k<1)requestAnimationFrame(tick);else n.textContent=num(end,dp);};requestAnimationFrame(tick);});}),{threshold:.15});
  io.observe(el);
 }
 // Typed questions that clearly ask for one of these views get it too (English phrasing only).
 function match(q){
  const s=String(q).toLowerCase();
  if(/\b(walk me through|briefing|demo)\b/.test(s))return 'demo';
  if(/how (does|do|is) (dengue ?sux|this|it|the app)\b.*(work|built|made)|architecture|pipeline|databricks|data flow/.test(s))return 'how';
  if(/accura|how good|reliab|how wrong|track record|back.?test/.test(s))return 'accuracy';
  if(/driv(es|ing|er)|what shapes|why .*(forecast|outlook|prediction)|explain .*(forecast|outlook)/.test(s))return 'drivers';
  if(/what changed|what'?s new|new clusters?|since (the )?last|growing clusters?/.test(s))return 'changes';
  if(/\b(map|hotspots?)\b/.test(s))return 'hotspots';
  if(/(walk|route|plan).*\b(in|for|around)\b/.test(s)){const a=data.current.areas.find(a=>s.includes(a.name.toLowerCase()));if(a&&data.inspection?.areas?.[a.code]?.stops?.length)return 'route:'+a.code;}
  if(/forecast|outlook|next week|cases (rise|go up|increase)|will cases/.test(s))return 'outlook';
  return null;
 }
 // ---- Demo briefing: one visual per step; the presenter advances. ----
 function startDemo(){
  stopDemo();demo={step:0};const bar=document.createElement('div');bar.className='demo-bar';bar.setAttribute('role','region');bar.setAttribute('aria-label','Demo briefing');
  bar.innerHTML=`<span class="demo-dots">${DEMO.map(()=>'<i></i>').join('')}</span><span class="demo-label"></span><button type="button" class="demo-next solid-button"></button><button type="button" class="icon-button demo-end" aria-label="End the briefing">${icon('x')}</button>`;
  document.body.append(bar);bar.querySelector('.demo-next').onclick=nextDemo;bar.querySelector('.demo-end').onclick=stopDemo;
  demo.key=e=>{if(e.target.closest('input,textarea,select,[contenteditable]'))return;if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();nextDemo();}if(e.key==='Escape')stopDemo();};document.addEventListener('keydown',demo.key);
  document.body.classList.add('demo-on');if(!['','#week'].includes(location.hash))location.hash='#week';C().clear?.(true);showDemo();
 }
 function showDemo(){
  const id=DEMO[demo.step],p=prompts().find(p=>p.id===id);if(!p){nextDemo();return;}const bar=document.querySelector('.demo-bar');
  bar.querySelectorAll('.demo-dots i').forEach((d,i)=>d.className=i<demo.step?'done':i===demo.step?'on':'');
  bar.querySelector('.demo-label').innerHTML=`<b>${demo.step+1} of ${DEMO.length}</b> ${esc(p.title)}`;
  const last=demo.step===DEMO.length-1;bar.querySelector('.demo-next').innerHTML=last?`Finish ${icon('check')}`:`Next ${icon('arrow-right')}`;
  C().visual(id,p.q,{area:p.area,demo:true});
 }
 function nextDemo(){if(!demo)return;if(demo.step>=DEMO.length-1){stopDemo();return;}demo.step++;showDemo();}
 function stopDemo(){document.body.classList.remove('demo-on');if(!demo)return;document.removeEventListener('keydown',demo.key);document.querySelector('.demo-bar')?.remove();demo=null;}
 function init(payload){data=payload;geo=null;}
 window.Showcase={init,gallery,render,lead,sources,match,press,prompts,startDemo,stopDemo,get demo(){return !!demo;}};
})();
