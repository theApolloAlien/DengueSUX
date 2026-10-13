/* 3D walk preview for every area. Footprints are official HDB shapes; heights are estimates from published storeys.
   Non-HDB buildings (condos, schools, shops) are grey context from Overture Maps / OpenStreetMap, never data.
   Cluster plans and routine walks follow a saved OneMap walking route; areas with no verified place get a flyover. */
(() => {
  'use strict';
  const $=s=>document.querySelector(s), reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const empty=()=>({type:'FeatureCollection',features:[]});
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  // Colours come from the stylesheet's --walk-* tokens (app.css, tokens layer) so the legend, CSS and WebGL agree; the literals are fallbacks.
  const token=(name,fallback)=>{try{return getComputedStyle(document.documentElement).getPropertyValue(name).trim()||fallback;}catch{return fallback;}};
  const COLORS={selected:token('--walk-selected','#e3ad3c'),cluster:token('--walk-cluster','#c2523c'),stop:token('--walk-stop','#2f6f58'),context:token('--walk-context','#ece6d8'),flat:token('--walk-flat','#e3dfd3'),city:token('--walk-city','#d3d5d0'),roofCity:'#e6e8e3',route:token('--walk-route','#1d4a3c'),walked:token('--walk-walked','#c9921f'),
    roofSelected:'#f6d58a',roofCluster:'#de8a73',roofStop:'#6ba48b',roofContext:'#faf8f1',green:token('--walk-green','#bcd8a8'),water:token('--walk-water','#8cc3dc'),beach:'#eadfbe',glow:token('--walk-glow','#36c2f5')};
  // Low follow camera: 80 m up and 90 m behind the walker, looking 45 m ahead (pitch about 59°). The walker
  // sits in the lower fifth of the frame with roughly 250 m of track visible ahead. Constant pace, gentle turns,
  // no zoom changes. A stop pauses long enough for one 3D checklist illustration.
  const WALK={speed:40,dwell:2.3,lookDwell:4.8,eye:80,behind:90,ahead:45,look:0,clearance:14,tau:.8,maxTurn:24,slowZone:60,legMin:150,nearBlocks:140,maxScale:1.6,introMs:1700,outroMs:1800,roof:.7};
  // What each checklist item highlights on the current stop's block (an illustration of where to look, not a finding).
  const BANDS={gutter:'roof',tray:'ground',pail:'corridors',drain:'ring',containers:'ring',bin:'ring',pond:'ring',treehole:'ring'};
  // Light presets. Aedes mosquitoes bite most around dawn and dusk, so the walk can be previewed in that light.
  const LIGHTS={
    day:{label:'Day',light:{color:'#fff6e6',intensity:.38,position:[1.25,200,35]},sky:{'sky-color':'#cfe3ec','horizon-color':'#f1f3ea','fog-color':'#eef0e8'},bg:'#eef0e8',raster:{'raster-brightness-max':1,'raster-saturation':-.6}},
    dusk:{label:'Dusk',light:{color:'#ffb27a',intensity:.55,position:[1.4,260,78]},sky:{'sky-color':'#5b4a7c','horizon-color':'#f5a26b','fog-color':'#d9a17e'},bg:'#cf9f83',raster:{'raster-brightness-max':.72,'raster-saturation':-.35}},
    dawn:{label:'Dawn',light:{color:'#ffd9b0',intensity:.5,position:[1.4,95,74]},sky:{'sky-color':'#8fb6d9','horizon-color':'#ffcfa3','fog-color':'#f2d7c2'},bg:'#e9d2bf',raster:{'raster-brightness-max':.85,'raster-saturation':-.45}},
  };
  const OUTCOME_COLORS={water_found:token('--walk-outcome-water','#2f8fd8'),cleared:token('--walk-outcome-cleared','#3faa6b'),nothing:token('--walk-outcome-nothing','#9aa59a')};
  let current=null,library=null,footprints=null;
  // Sun position over Singapore (1.35°N, 103.82°E) for a clock hour today (NOAA approximation). Singapore keeps UTC+8
  // at 103.8°E, so solar noon falls near 13:05 clock time; the light and the estimated shadows follow it.
  const SG=[103.82,1.352],PRESET_HOURS={day:13,dusk:18.75,dawn:7};
  function sunAt(hour,date=new Date()){
    const day=Math.floor((Date.UTC(date.getFullYear(),date.getMonth(),date.getDate())-Date.UTC(date.getFullYear(),0,0))/864e5);
    const g=2*Math.PI/365*(day-1+(hour-12)/24);
    const decl=0.006918-0.399912*Math.cos(g)+0.070257*Math.sin(g)-0.006758*Math.cos(2*g)+0.000907*Math.sin(2*g)-0.002697*Math.cos(3*g)+0.00148*Math.sin(3*g);
    const eqt=229.18*(0.000075+0.001868*Math.cos(g)-0.032077*Math.sin(g)-0.014615*Math.cos(2*g)-0.040849*Math.sin(2*g));
    const solar=hour+(eqt+4*SG[0]-480)/60,H=(solar-12)*15*Math.PI/180,lat=SG[1]*Math.PI/180;
    const alt=Math.asin(Math.sin(lat)*Math.sin(decl)+Math.cos(lat)*Math.cos(decl)*Math.cos(H));
    const az=Math.atan2(Math.sin(H),Math.cos(H)*Math.sin(lat)-Math.tan(decl)*Math.cos(lat))+Math.PI;
    return {altitude:alt*180/Math.PI,azimuth:((az*180/Math.PI)%360+360)%360};
  }
  const clock=h=>`${String(Math.floor(h)).padStart(2,'0')}:${String(Math.round((h%1)*60)).padStart(2,'0')}`;
  // Convex hull (Andrew's monotone chain) of lon/lat points: the shadow a block casts is its footprint swept along the sun's direction.
  function hull(points){
    const p=[...points].sort((a,b)=>a[0]-b[0]||a[1]-b[1]);if(p.length<3)return p;
    const cross=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
    const lower=[];for(const q of p){while(lower.length>=2&&cross(lower[lower.length-2],lower[lower.length-1],q)<=0)lower.pop();lower.push(q);}
    const upper=[];for(let i=p.length-1;i>=0;i--){const q=p[i];while(upper.length>=2&&cross(upper[upper.length-2],upper[upper.length-1],q)<=0)upper.pop();upper.push(q);}
    upper.pop();lower.pop();return lower.concat(upper);
  }
  function shadows(state,sun){
    const map=state.map;if(!map?.getSource('shadows'))return;
    if(sun.altitude<4){map.getSource('shadows').setData(empty());return;}
    const dir=sun.azimuth+180,tan=Math.tan(sun.altitude*Math.PI/180),features=[];
    for(const f of state.buildings?.features||[]){const h=Number(f.properties.height_m)||0;if(h<=0)continue;const L=Math.min(260,h/tan);
      const rings=f.geometry.type==='Polygon'?[f.geometry.coordinates[0]]:f.geometry.coordinates.map(p=>p[0]);
      for(const ring of rings){const pts=[];for(const p of ring){pts.push(p);pts.push(offset(p,dir,L));}const h2=hull(pts);if(h2.length>=3)features.push({type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[...h2,h2[0]]]}});}}
    map.getSource('shadows').setData({type:'FeatureCollection',features});
  }
  function setHour(state,hour){
    state.hour=hour;const map=state.map,sun=sunAt(hour),up=Math.max(0,sun.altitude),warm=Math.min(1,Math.max(0,(16-up)/16));
    const lerp=(a,b,k)=>Math.round(a+(b-a)*k),hex=(r,g,b)=>'#'+[r,g,b].map(v=>v.toString(16).padStart(2,'0')).join('');
    const color=hex(255,lerp(246,178,warm),lerp(230,122,warm)),intensity=up<=0?.12:.24+.34*Math.min(1,up/35);
    const preset=up<=2?'night':warm>.55?(hour<12.5?'dawn':'dusk'):'day';
    const SKY={day:{sky:{'sky-color':'#cfe3ec','horizon-color':'#f1f3ea','fog-color':'#eef0e8'},bg:'#eef0e8',raster:{'raster-brightness-max':1,'raster-saturation':-.6},label:'Day'},
      dawn:{sky:{'sky-color':'#8fb6d9','horizon-color':'#ffcfa3','fog-color':'#f2d7c2'},bg:'#e9d2bf',raster:{'raster-brightness-max':.85,'raster-saturation':-.45},label:'Dawn'},
      dusk:{sky:{'sky-color':'#5b4a7c','horizon-color':'#f5a26b','fog-color':'#d9a17e'},bg:'#cf9f83',raster:{'raster-brightness-max':.72,'raster-saturation':-.35},label:'Dusk'},
      night:{sky:{'sky-color':'#182a3d','horizon-color':'#3b4a62','fog-color':'#2d3a4c'},bg:'#2b3747',raster:{'raster-brightness-max':.45,'raster-saturation':-.7},label:'Night'}}[preset];
    state.light=preset;
    const button=state.tour.querySelector('[data-tour=light]');if(button){button.querySelector('span').textContent=`${SKY.label} · ${clock(hour)}`;button.setAttribute('aria-label',`Light: ${SKY.label.toLowerCase()} at ${clock(hour)}. Aedes bite most around dawn and dusk.`);}
    const slider=state.tour.querySelector('#route-hour-input');if(slider&&Number(slider.value)!==hour)slider.value=String(hour);
    const text=state.tour.querySelector('#route-hour-text');if(text)text.textContent=clock(hour);
    ['dusk','dawn','night'].forEach(k=>state.container.classList.toggle('is-'+k,preset===k));
    const note=state.container.querySelector('.route-light-note');if(note)note.hidden=preset==='day';
    if(!map)return;
    map.setLight({anchor:'map',color,intensity,position:[1.3,sun.azimuth,Math.min(88,90-up)]});
    try{map.setSky({...SKY.sky,'sky-horizon-blend':.6,'horizon-fog-blend':.7,'fog-ground-blend':.3,'atmosphere-blend':0});}catch{}
    map.setPaintProperty('background','background-color',SKY.bg);
    if(map.getLayer('onemap'))Object.entries(SKY.raster).forEach(([k,v])=>map.setPaintProperty('onemap',k,v));
    cancelAnimationFrame(state.shadowFrame);state.shadowFrame=requestAnimationFrame(()=>shadows(state,sun));
  }
  // Street-level look at the current stop (an illustration of what a volunteer sees): 1.7 m up, a few metres back on the path.
  function eyeView(state,index){
    if(reduced.matches||state.isTour||!state.track)return null;const stop=state.plan.stops[index];if(!stop)return null;
    const p=state.track.at(state.along),target=[stop.longitude,stop.latitude],heading=bearingOf(p,target);
    const from=offset(p,heading+180,9);if(heightAt(state,from)>0||heightAt(state,p)>0||distance(p,target)>120)return null;
    const feature=state.buildings?.features.find(f=>f.properties.stop_id===stop.id),h=Number(feature?.properties.height_m)||0,kind=BANDS[state.bandKey]||'ring';
    const look=kind==='roof'?Math.max(4,h-1):kind==='corridors'?Math.max(3,h*.45):kind==='ground'?2:1.5;
    return state.map.calculateCameraOptionsFromTo(from,1.7,target,look);
  }
  // Arriving from the island: blocks grow out of the ground in the order of their distance from the route start.
  function riseIn(state){
    const map=state.map,feats=(state.buildings?.features||[]).filter(f=>Number(f.properties.height_m)>0);if(!feats.length||!map)return;
    const origin=state.plan.stops[0]?[state.plan.stops[0].longitude,state.plan.stops[0].latitude]:state.track?.centre;if(!origin)return;
    const first=f=>f.geometry.type==='Polygon'?f.geometry.coordinates[0][0]:f.geometry.coordinates[0][0][0];
    const dist=feats.map(f=>distance(first(f),origin)),max=Math.max(...dist,1),start=performance.now(),span=1300,grow=600;
    feats.forEach(f=>map.setFeatureState({source:'buildings',id:f.properties.id},{rise:0.001}));
    const tick=now=>{if(state.closed||!state.map)return;const t=now-start;let done=true;
      feats.forEach((f,i)=>{const k=Math.min(1,Math.max(0,(t-dist[i]/max*span)/grow));if(k<1)done=false;map.setFeatureState({source:'buildings',id:f.properties.id},{rise:Math.max(0.001,1-Math.pow(1-k,3))});});
      if(!done)requestAnimationFrame(tick);};
    requestAnimationFrame(tick);
  }

  function loadLibrary(){
    if(window.maplibregl)return Promise.resolve(window.maplibregl);
    if(library)return library;
    library=new Promise((resolve,reject)=>{
      if(!document.querySelector('link[data-maplibre]')){const css=document.createElement('link');css.rel='stylesheet';css.href='/vendor/maplibre/maplibre-gl.css';css.dataset.maplibre='';document.head.append(css);}
      const script=document.createElement('script');script.src='/vendor/maplibre/maplibre-gl.js';script.async=true;
      script.onload=()=>resolve(window.maplibregl);script.onerror=()=>{library=null;script.remove();reject(new Error('Map library unavailable'));};document.head.append(script);
    });
    return library;
  }
  async function loadFootprints(){
    if(window.DENGUESUX_DATA)return window.DENGUESUX_DATA.footprints||null;
    if(!footprints)footprints=fetch('/data/footprints.json',{cache:'no-cache',signal:AbortSignal.timeout(12000)}).then(r=>r.ok?r.json():null).catch(()=>{footprints=null;return null;});
    return footprints;
  }
  const distance=(a,b)=>{const lat=(a[1]+b[1])*Math.PI/360;return Math.hypot((a[0]-b[0])*Math.cos(lat),a[1]-b[1])*111195;};
  const bearingOf=(a,b)=>Math.atan2((b[0]-a[0])*Math.cos(a[1]*Math.PI/180),b[1]-a[1])*180/Math.PI;
  const turn=(from,to)=>((to-from+540)%360)-180;
  const offset=(p,bearing,metres)=>{const r=bearing*Math.PI/180;return [p[0]+metres*Math.sin(r)/(111320*Math.cos(p[1]*Math.PI/180)),p[1]+metres*Math.cos(r)/110540];};
  const valid=p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(p[0])&&Number.isFinite(p[1]);
  const km=m=>`${(m/1000).toFixed(m<1000?2:1)} km`;
  const circle=(center,metres,steps=28)=>{const ring=[];for(let i=0;i<=steps;i++)ring.push(offset(center,i*360/steps,metres));return ring;};
  // A footprint grown outward about its centre (illustrative highlight only).
  function grown(geometry,metres){
    const rings=geometry.type==='Polygon'?[geometry.coordinates]:geometry.coordinates;const all=rings.flat(2);
    const xs=[],ys=[];for(let i=0;i<all.length;i+=2){xs.push(all[i]);ys.push(all[i+1]);}
    const cx=(Math.min(...xs)+Math.max(...xs))/2,cy=(Math.min(...ys)+Math.max(...ys))/2,half=Math.max(4,Math.min(distance([Math.min(...xs),cy],[Math.max(...xs),cy]),distance([cx,Math.min(...ys)],[cx,Math.max(...ys)]))/2),k=1+metres/half;
    const scale=ring=>ring.map(([x,y])=>[cx+(x-cx)*k,cy+(y-cy)*k]);
    return geometry.type==='Polygon'?{type:'Polygon',coordinates:geometry.coordinates.map(scale)}:{type:'MultiPolygon',coordinates:geometry.coordinates.map(p=>p.map(scale))};
  }
  function trackFrom(points,stops,legMin){
    const cumulative=[0];
    for(let i=1;i<points.length;i++)cumulative.push(cumulative[i-1]+distance(points[i-1],points[i]));
    if(!cumulative.at(-1))return null;
    // Snap each stop to the original path in visit order; never draw invented connectors.
    let previous=0;
    const stopDistances=stops.map(stop=>{
      const point=[stop.longitude,stop.latitude];let best={gap:Infinity,along:previous};
      for(let i=1;i<points.length;i++){
        if(cumulative[i]<previous)continue;
        const a=points[i-1],b=points[i],cos=Math.cos(point[1]*Math.PI/180),x=(b[0]-a[0])*cos,y=b[1]-a[1];
        const length=cumulative[i]-cumulative[i-1];if(!length)continue;
        const minimum=Math.max(0,(previous-cumulative[i-1])/length);
        const t=Math.max(minimum,Math.min(1,((point[0]-a[0])*cos*x+(point[1]-a[1])*y)/(x*x+y*y)));
        const projected=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t],gap=distance(point,projected);
        if(gap<best.gap)best={gap,along:cumulative[i-1]+length*t};
        // Take the first close approach: a route that passes a stop again later must not skip the legs between.
        else if(best.gap<30&&gap>best.gap+40)break;
      }
      previous=best.along;return previous;
    });
    const total=cumulative.at(-1);
    const at=along=>{
      along=Math.max(0,Math.min(total,along));
      let lo=1,hi=points.length-1;while(lo<hi){const mid=(lo+hi)>>1;if(cumulative[mid]<along)lo=mid+1;else hi=mid;}
      const i=lo,a=points[i-1],b=points[i],length=cumulative[i]-cumulative[i-1],t=length?(along-cumulative[i-1])/length:0;
      return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];
    };
    // Heading over a wide window (20 m behind to 70 m ahead) smooths the zig-zags of estate footpaths.
    const heading=along=>{const a=at(along-20),b=at(along+70);return distance(a,b)>3?bearingOf(a,b):bearingOf(at(along-60),at(along+20));};
    // One steady heading per leg (this stop towards the next): the camera turns while pausing at a stop,
    // not at every bend of the footpath. Stops closer than legMin are looked past.
    const legHeading=from=>{
      const next=stopDistances.findIndex(d=>d>=from+legMin),to=next>=0?stopDistances[next]:total;
      return distance(at(from),at(to))>25?bearingOf(at(from),at(to)):heading(from);
    };
    return {points,cumulative,stopDistances,total,at,heading,legHeading};
  }
  function routeTrack(plan){
    const raw=plan.route?.geometry;
    if(plan.route?.method!=='onemap_walk'||raw?.type!=='LineString'||!raw.coordinates?.every(valid)||raw.coordinates.length<2)return null;
    return trackFrom(raw.coordinates,plan.stops,WALK.legMin);
  }
  // Flyover: a camera ring around the cluster footprint or the area, always looking at its centre. Never drawn as a route.
  function tourTrack(tour){
    if(tour?.type!=='LineString'||!tour.coordinates?.every(valid)||tour.coordinates.length<3)return null;
    const track=trackFrom(tour.coordinates,[],WALK.legMin);if(!track)return null;
    const xs=tour.coordinates.map(p=>p[0]),ys=tour.coordinates.map(p=>p[1]);
    track.centre=[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2];
    track.tour=true;return track;
  }
  function summary(buildings,plan){
    const features=buildings.features.filter(f=>f.properties.role!=='city'),city=buildings.features.length-features.length,raised=features.filter(f=>Number(f.properties.height_m)>0).length;
    const matched=new Set(features.map(f=>f.properties.stop_id).filter(Boolean));
    const missing=plan.stops.filter(stop=>!matched.has(stop.id)&&/^block/.test(String(stop.place_type||'block'))).map(stop=>stop.number);
    return {count:features.length,raised,flat:features.length-raised,missing,city};
  }
  // Point-in-polygon in lon/lat; only used to keep the camera above the block it would otherwise pass through.
  function inside(point,ring){let hit=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if((yi>point[1])!==(yj>point[1])&&point[0]<(xj-xi)*(point[1]-yi)/(yj-yi)+xi)hit=!hit;}return hit;}
  function heightAt(state,point){
    let top=0;
    for(const f of state.solids){if(f.h<=top||point[0]<f.box[0]||point[0]>f.box[2]||point[1]<f.box[1]||point[1]>f.box[3])continue;if(f.rings.some(r=>inside(point,r)))top=f.h;}
    return top;
  }
  const looksAvailable=()=>!!window.Checklist3D?.supported();
  const stopKey=(state,index)=>{const list=state.plan.stops[index]?.checklist||[];if(!list.length)return null;return window.Checklist3D?.keyFor(list[index%list.length])||null;};

  function mount(plan,area,onSelect,opts={}){
    dispose();
    // A walk needs a saved OneMap route between at least two stops; otherwise fly around the area (stops stay pinned).
    const stops=plan.stops||[],walkTrack=stops.length>1?routeTrack(plan):null,isTour=!walkTrack&&!!plan.tour;
    const track=isTour?tourTrack(plan.tour):walkTrack;
    if(!stops.length&&!track)return;
    const wrap=$('.inspection-map-wrap'),column=$('.inspection-map-column');if(!wrap||!column)return;
    const toolbar=document.createElement('div');toolbar.className='route-preview-toolbar';
    toolbar.innerHTML=`<div class="route-view-tabs" role="group" aria-label="Inspection map view"><button type="button" data-map-mode="2d" aria-pressed="true"><i class="ph ph-map-trifold" aria-hidden="true"></i> 2D map</button><button type="button" data-map-mode="3d" aria-pressed="false"><i class="ph ph-cube" aria-hidden="true"></i> ${isTour?'3D flyover':'3D walk preview'}</button><button type="button" data-map-mode="full" aria-pressed="false" title="Full screen: swipe between stops; the screen stays awake"><i class="ph ph-arrows-out" aria-hidden="true"></i> Full screen</button></div><span class="route-preview-label">Official HDB shapes · grey city context</span>`;
    column.insertBefore(toolbar,wrap);
    const container=document.createElement('div');container.id='route-3d';container.hidden=true;container.setAttribute('role','region');container.setAttribute('aria-label',isTour?'3D flyover of the area':'3D inspection route with estimated HDB block heights');wrap.prepend(container);
    const tour=document.createElement('section');tour.className='route-tour';tour.hidden=true;tour.setAttribute('aria-label','Route preview controls');
    const legend=isTour?`<li><b style="background:${COLORS.cluster};opacity:.5"></b>Cluster footprint</li><li><b style="background:${COLORS.context}"></b>HDB blocks</li><li><b style="background:${COLORS.city}"></b>Other buildings (context)</li><li><b style="background:${COLORS.green}"></b>Parks (URA zoning)</li><li><b style="background:${COLORS.water}"></b>Water</li>`
      :`<li><b style="background:${COLORS.selected}"></b>Current stop</li><li><b style="background:${COLORS.stop}"></b>Other stops</li><li><b style="background:${COLORS.cluster}"></b>Cluster blocks</li><li><b style="background:${COLORS.context}"></b>Other HDB blocks</li><li><b class="is-flat" style="background:${COLORS.flat}"></b>Storeys unverified (flat)</li><li><b style="background:${COLORS.city}"></b>Other buildings (context)</li><li><b style="background:${COLORS.green}"></b>Parks (URA zoning)</li><li><b style="background:${COLORS.water}"></b>Water</li><li><b style="background:${COLORS.glow}"></b>Where to look</li><li><b class="is-line" style="background:${COLORS.walked}"></b>Walked so far</li><li><b style="background:${OUTCOME_COLORS.water_found}"></b>Water found (field report)</li><li><b style="background:${OUTCOME_COLORS.cleared}"></b>Cleared</li><li><b style="background:#8a63c9;opacity:.5"></b>High Aedes area (NEA)</li>`;
    tour.innerHTML=`<div class="route-tour-controls"><button type="button" data-tour="previous" aria-label="Previous inspection stop"><i class="ph ph-caret-left" aria-hidden="true"></i></button><button type="button" data-tour="play" class="route-tour-play"><i class="ph ph-play" aria-hidden="true"></i><span>Walk the route</span></button><button type="button" data-tour="next" aria-label="Next inspection stop"><i class="ph ph-caret-right" aria-hidden="true"></i></button><button type="button" data-tour="speed" class="route-tour-speed" aria-label="Walking preview speed: normal">1×</button><button type="button" data-tour="fit" aria-label="Show the whole route from above"><i class="ph ph-arrows-out-simple" aria-hidden="true"></i><span>${isTour?'Whole area':'Whole route'}</span></button></div><div class="route-tour-scene" aria-label="Scene"><button type="button" data-tour="light" class="route-tour-light" aria-label="Light: day. Aedes bite most around dawn and dusk." title="Aedes mosquitoes bite most around dawn and dusk"><i class="ph ph-sun-horizon" aria-hidden="true"></i><span>Day</span></button><label class="route-hour" title="Time of day: the light and estimated shadows follow the sun over Singapore"><span class="sr-only">Time of day</span><input type="range" id="route-hour-input" min="6" max="19.5" step="0.25" value="13" aria-label="Time of day"><span id="route-hour-text" aria-hidden="true">13:00</span></label><button type="button" data-tour="rain" class="route-tour-rain" aria-pressed="false" hidden><i class="ph ph-cloud-rain" aria-hidden="true"></i><span>Rain</span></button><button type="button" data-tour="record" class="route-tour-record" aria-label="Record the walk as a video" ${typeof MediaRecorder==='undefined'?'hidden':''}><i class="ph ph-record" aria-hidden="true"></i><span>Record</span></button></div>
      <div class="route-scrub"><label for="route-scrub-input" class="route-scrub-label">${isTour?'Around the area':'Along the route'}</label><input id="route-scrub-input" type="range" min="0" max="1000" step="1" value="0"><span class="route-scrub-text" aria-hidden="true"></span></div>
      <div class="route-tour-stop"><span role="status" aria-live="polite"></span><button type="button" data-tour="checklist">Checklist <i class="ph ph-arrow-down" aria-hidden="true"></i></button></div><ul class="route-3d-legend" aria-label="3D colours">${legend}</ul><p class="route-3d-note"></p><p class="route-3d-status" role="status"></p>`;
    wrap.after(tour);
    if(isTour){tour.querySelectorAll('[data-tour=previous],[data-tour=next],[data-tour=checklist]').forEach(b=>b.hidden=true);}
    // Flyovers and rain: the toggle only means something along a walked route with a nearby station reading.
    if(isTour)tour.querySelector('[data-tour=rain]').hidden=true;
    const state={plan,area,onSelect,opts,wrap,toolbar,container,tour,isTour,map:null,mode:'2d',index:0,playing:false,phase:'idle',frame:0,timer:0,track,along:0,heading:0,eye:WALK.eye,scale:1,speedFactor:1,multiplier:1,dwellUntil:0,nextStop:0,lastFrame:0,lastPaint:0,markers:[],walker:null,callout:null,look:null,lookHost:null,loading:false,closed:false,selectedFeature:null,popup:null,solids:[],pulse:0,bandKey:null};
    if(isTour){const length=track.total;state.cfg={...WALK,eye:Math.max(180,Math.min(900,length/22)),speed:Math.max(60,length/48),clearance:40};}else state.cfg=WALK;
    current=state;
    if(state.track){state.along=0;state.heading=state.track.heading(0);}
    toolbar.querySelectorAll('[data-map-mode]').forEach(button=>button.addEventListener('click',()=>setMode(state,button.dataset.mapMode)));
    tour.querySelector('[data-tour=previous]').onclick=()=>goToStop(state,state.index-1);
    tour.querySelector('[data-tour=next]').onclick=()=>goToStop(state,state.index+1);
    tour.querySelector('[data-tour=play]').onclick=()=>togglePlay(state);
    tour.querySelector('[data-tour=speed]').onclick=()=>{state.multiplier=state.multiplier===1?2:1;const b=tour.querySelector('[data-tour=speed]');b.textContent=`${state.multiplier}×`;b.setAttribute('aria-label',`Walking preview speed: ${state.multiplier===1?'normal':'double'}`);};
    tour.querySelector('[data-tour=fit]').onclick=()=>{pause(state);fit(state);};
    tour.querySelector('[data-tour=light]').onclick=()=>{const order=['day','dusk','dawn'];setHour(state,PRESET_HOURS[order[(order.indexOf(state.light||'day')+1)%order.length]]);};
    tour.querySelector('#route-hour-input').oninput=e=>setHour(state,Number(e.target.value));
    tour.querySelector('[data-tour=rain]').onclick=()=>toggleRain(state);
    tour.querySelector('[data-tour=record]').onclick=()=>toggleRecord(state);
    tour.querySelector('[data-tour=checklist]').onclick=()=>{const card=document.getElementById('stop-'+state.plan.stops[state.index]?.id);card?.scrollIntoView({block:'center',behavior:reduced.matches?'instant':'smooth'});card?.querySelector('.stop-number')?.focus({preventScroll:true});};
    const scrub=tour.querySelector('#route-scrub-input');
    scrub.addEventListener('input',()=>{if(!state.track||!state.map)return;const fraction=Number(scrub.value)/1000;pause(state);state.along=state.track.total*fraction;state.heading=state.target=state.track.legHeading(state.along);placeStreet(state,true);syncStop(state);});
    state.motionChange=()=>{if(reduced.matches)pause(state);update(state);};reduced.addEventListener('change',state.motionChange);
    state.visibility=()=>{if(document.hidden)pause(state);};document.addEventListener('visibilitychange',state.visibility);
    state.keys=event=>{if(state.mode!=='3d'||state.isTour||event.target.closest('input,textarea,select'))return;if(event.key==='ArrowRight'&&!event.altKey){event.preventDefault();goToStop(state,state.index+1);}else if(event.key==='ArrowLeft'&&!event.altKey){event.preventDefault();goToStop(state,state.index-1);}};
    tour.addEventListener('keydown',state.keys);container.addEventListener('keydown',state.keys);
    update(state);
    if(opts.start3d||window.RouteFlythrough.autoplay)setMode(state,'3d');
  }
  function setLight(state,name){return setHour(state,PRESET_HOURS[name]??13);}
  // Observed rain at the area's nearest station, drawn as falling streaks (a custom three.js layer); never a forecast.
  function toggleRain(state){
    const button=state.tour.querySelector('[data-tour=rain]'),on=button.getAttribute('aria-pressed')!=='true';
    if(!window.Weather3D||!state.map||!state.rain)return;
    button.setAttribute('aria-pressed',String(on));button.classList.toggle('is-on',on);
    window.Weather3D.set(state.map,{on,mm:state.rain.value,center:state.plan.stops[0]?[state.plan.stops[0].longitude,state.plan.stops[0].latitude]:state.track?.centre});
  }
  function setLightLegacy(state,name){
    const preset=LIGHTS[name]||LIGHTS.day,map=state.map;state.light=name;
    const button=state.tour.querySelector('[data-tour=light]');button.querySelector('span').textContent=preset.label;
    button.setAttribute('aria-label',`Light: ${preset.label.toLowerCase()}. Aedes bite most around dawn and dusk.`);
    state.container.classList.toggle('is-dusk',name==='dusk');state.container.classList.toggle('is-dawn',name==='dawn');
    const note=state.container.querySelector('.route-light-note');if(note)note.hidden=name==='day';
    if(!map)return;
    map.setLight({anchor:'viewport',...preset.light});
    try{map.setSky({...preset.sky,'sky-horizon-blend':.6,'horizon-fog-blend':.7,'fog-ground-blend':.3,'atmosphere-blend':0});}catch{}
    map.setPaintProperty('background','background-color',preset.bg);
    if(map.getLayer('onemap'))Object.entries(preset.raster).forEach(([k,v])=>map.setPaintProperty('onemap',k,v));
  }
  // Record the 3D view as a short video (WebM) for residents' chat groups. Stays in this browser until saved.
  function toggleRecord(state){
    const button=state.tour.querySelector('[data-tour=record]');
    if(state.recorder){state.recorder.stop();return;}
    const canvas=state.map?.getCanvas();if(!canvas?.captureStream)return;
    const type=['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));if(!type)return;
    // The recording is drawn from a composite: the WebGL frame plus the stop pins, walker, cluster labels and the stop card.
    const composite=document.createElement('canvas');composite.width=canvas.width;composite.height=canvas.height;state.composite=composite;
    const compose=()=>{if(!state.recorder||!state.map)return;const c=composite.getContext('2d'),dpr=canvas.width/Math.max(1,canvas.clientWidth),map=state.map;
      c.drawImage(canvas,0,0);c.font=`700 ${13*dpr}px "DM Sans",sans-serif`;c.textAlign='center';c.textBaseline='middle';
      state.markers.forEach((m,i)=>{const p=map.project(m.getLngLat()),sel=i===state.index,r=(sel?17:15)*dpr;c.beginPath();c.arc(p.x*dpr,p.y*dpr,r,0,Math.PI*2);c.fillStyle=sel?COLORS.selected:COLORS.stop;c.fill();c.lineWidth=2*dpr;c.strokeStyle='#fff';c.stroke();c.fillStyle=sel?'#14382d':'#fff';c.fillText(String(i+1),p.x*dpr,p.y*dpr+dpr);});
      if(state.walker){const p=map.project(state.walker.getLngLat());c.beginPath();c.arc(p.x*dpr,p.y*dpr,10*dpr,0,Math.PI*2);c.fillStyle=COLORS.selected;c.fill();c.lineWidth=3*dpr;c.strokeStyle='#fff';c.stroke();}
      (state.labels||[]).forEach(m=>{const p=map.project(m.getLngLat()),text=m.getElement().textContent.replace(/\s+/g,' ').trim().slice(0,46);c.font=`600 ${12*dpr}px "DM Sans",sans-serif`;const w=c.measureText(text).width+16*dpr;c.fillStyle='#fffdf5ee';c.fillRect(p.x*dpr-w/2,p.y*dpr-34*dpr,w,22*dpr);c.fillStyle='#7a2e1f';c.fillText(text,p.x*dpr,p.y*dpr-23*dpr);});
      const card=state.container.querySelector('.route-stop-card');
      if(card){const title=card.querySelector('strong')?.textContent.trim()||'',items=[...card.querySelectorAll('li')].map(l=>l.textContent.trim()).slice(0,3),look=card.querySelector('canvas');
        const x=12*dpr,y=12*dpr,w=250*dpr,lh=18*dpr,h=(42+items.length*18+(look?110:0))*dpr;c.fillStyle='#fffdf5f2';c.fillRect(x,y,w,h);c.fillStyle=COLORS.selected;c.fillRect(x,y,w,3*dpr);
        c.textAlign='left';c.fillStyle='#163f35';c.font=`700 ${13*dpr}px "DM Sans",sans-serif`;c.fillText(title.slice(0,34),x+10*dpr,y+18*dpr);
        let yy=y+30*dpr;if(look&&look.width){c.drawImage(look,x+10*dpr,yy,w-20*dpr,100*dpr);yy+=108*dpr;}
        c.font=`${12*dpr}px "DM Sans",sans-serif`;items.forEach((t,i)=>{c.fillStyle=i===0?'#163f35':'#7d8a72';c.fillText('• '+t.slice(0,40),x+10*dpr,yy+i*lh+8*dpr);});c.textAlign='center';}
      state.composeFrame=requestAnimationFrame(compose);};
    const chunks=[],recorder=new MediaRecorder(composite.captureStream(30),{mimeType:type,videoBitsPerSecond:5e6});
    state.composeFrame=requestAnimationFrame(compose);
    recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
    recorder.onstop=()=>{state.recorder=null;cancelAnimationFrame(state.composeFrame);button.classList.remove('is-recording');button.querySelector('span').textContent='Record';
      const blob=new Blob(chunks,{type}),url=URL.createObjectURL(blob),link=document.createElement('a');
      link.href=url;link.download=`denguesux-walk-${state.area.code.toLowerCase()}.${type.includes('mp4')?'mp4':'webm'}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),4000);};
    recorder.start(500);state.recorder=recorder;button.classList.add('is-recording');button.querySelector('span').textContent='Stop';
    if(!state.playing)togglePlay(state);
  }
  function titleCard(state){
    if(reduced.matches||state.isTour)return;
    const impact=state.plan.impact||{},homes=impact.homes??impact.homes_total??state.plan.stops.reduce((n,s)=>n+(Number(s.homes_nearby)||0),0);
    const card=document.createElement('div');card.className='route-title-card';
    card.innerHTML=`<span>${esc(state.area.name)}</span><strong>${state.plan.stops.length} places to check</strong><small>${state.track?km(state.track.total)+' on foot':''}${homes?` · ${Number(homes).toLocaleString('en-SG')} homes nearby`:''}</small>`;
    state.container.append(card);setTimeout(()=>card.classList.add('is-leaving'),WALK.introMs+400);setTimeout(()=>card.remove(),WALK.introMs+1300);
  }
  function update(state){
    if(state.closed)return;
    const stops=state.plan.stops||[],stop=stops[state.index],play=state.tour.querySelector('[data-tour=play]'),track=state.track;
    play.disabled=reduced.matches||!track||!state.ready;
    const verb=state.isTour?'Fly around':'Walk the route';
    play.querySelector('span').textContent=reduced.matches?(state.isTour?'Drag the slider':'Step through stops'):!track?'Walk unavailable':state.playing?'Pause':state.along>=track.total-1?(state.isTour?'Fly again':'Walk again'):state.along>1?'Resume':verb;
    play.querySelector('i').className='ph ph-'+(state.playing?'pause':reduced.matches?'hand-pointing':state.isTour?'airplane-tilt':'person-simple-walk');play.setAttribute('aria-label',state.playing?'Pause the preview':state.isTour?'Fly around the area':'Play the walking preview along the whole route');
    state.tour.querySelector('[data-tour=speed]').hidden=reduced.matches||!track;
    if(!state.isTour){
      state.tour.querySelector('[data-tour=previous]').disabled=!state.ready||state.index===0&&(!track||state.along<=track.stopDistances[0]+1);
      state.tour.querySelector('[data-tour=next]').disabled=!state.ready||state.index===stops.length-1;
    }
    state.tour.querySelector('.route-scrub').hidden=!track;
    const label=state.tour.querySelector('.route-tour-stop span');
    if(stop){const floors=stop.max_floor_lvl?` · ${stop.max_floor_lvl} storeys`:'';label.innerHTML=`<b>Stop ${state.index+1} of ${stops.length}</b> · ${esc(stop.name)}${esc(floors)}`;}
    else label.innerHTML=`<b>${esc(state.area.name)}</b> · ${state.plan.tour?.kind==='cluster_footprint'?'around the cluster footprint':'around the planning area'}`;
    const motion=reduced.matches?(state.isTour?' Reduced motion is on: drag the slider to move around.':' Reduced motion is on: drag the slider or use Previous and Next (arrow keys) for still views.'):!track?' Walking directions are unavailable, so the preview steps between stops.':'';
    state.tour.querySelector('.route-3d-note').textContent=state.isTour?`No official HDB block, hawker centre or park lies close enough to walk, so this is a camera flyover, not a route. Parks and water are URA Master Plan 2025 zoning (planned use).${motion}`
      :`Shapes are official HDB footprints. Heights are estimates: published storeys × 2.8 m + 1.3 m roof, not surveyed. Grey buildings are non-HDB context from Overture Maps and OpenStreetMap, raised only where a height is listed. Parks and water are URA Master Plan zoning. At each stop a 3D illustration shows what to look for; glowing roofs or corridors mark where, not a finding. Places to check, not confirmed breeding sites.${motion}`;
    state.markers.forEach((marker,i)=>{const el=marker.getElement();el.classList.toggle('is-selected',i===state.index);if(i===state.index)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});
    progressText(state);highlight(state);
  }
  function progressText(state){
    const t=state.track;if(!t)return;
    const next=t.stopDistances.findIndex(d=>d>state.along+2);
    state.tour.querySelector('.route-scrub-text').textContent=state.isTour?`${Math.round(state.along/t.total*100)}% around`:`${km(state.along)} of ${km(t.total)}${next>=0?` · next: stop ${next+1}`:' · end of route'}`;
    const scrub=state.tour.querySelector('#route-scrub-input');scrub.value=String(Math.round(state.along/t.total*1000));
    scrub.setAttribute('aria-valuetext',state.isTour?`${Math.round(state.along/t.total*100)} percent around`:`${km(state.along)} of ${km(t.total)}, ${next>=0?`next stop ${next+1}`:'end of route'}`);
  }
  function highlight(state){
    const map=state.map;if(!map||!map.getSource('buildings'))return;
    if(state.selectedFeature!==null)map.setFeatureState({source:'buildings',id:state.selectedFeature},{selected:false});
    const id=state.plan.stops[state.index]?.id,feature=id&&state.buildings?.features.find(f=>f.properties.stop_id===id);
    state.selectedFeature=feature?feature.properties.id:null;
    if(state.selectedFeature!==null)map.setFeatureState({source:'buildings',id:state.selectedFeature},{selected:true});
    if(map.getSource('beacons'))state.plan.stops.forEach((s,i)=>map.setFeatureState({source:'beacons',id:i},{selected:i===state.index}));
  }
  // Where to look on the current stop: the roof edge (gutters), the ground floor (planter trays) or corridor
  // levels (pails); a ground ring for hawker centres and parks. Drawn only while a stop is in view.
  function setBands(state,key){
    const map=state.map;if(!map?.getSource('inspect'))return;
    state.bandKey=key;const stop=state.plan.stops[state.index];
    if(!key||!stop){map.getSource('inspect').setData(empty());return;}
    const feature=state.buildings?.features.find(f=>f.properties.stop_id===stop.id),h=Number(feature?.properties.height_m)||0,kind=BANDS[key];
    const out=[];
    if(feature&&h>0&&kind==='roof')out.push({geometry:grown(feature.geometry,1.3),properties:{base:Math.max(0,h-WALK.roof-.6),top:h+1.4,color:COLORS.glow}});
    else if(feature&&h>0&&kind==='ground')out.push({geometry:grown(feature.geometry,1.1),properties:{base:0,top:3.8,color:COLORS.glow}});
    else if(feature&&h>0&&kind==='corridors'){const floors=Number(feature.properties.max_floor_lvl)||Math.round((h-1.3)/2.8);for(let k=1;k<floors;k+=Math.max(1,Math.round(floors/6)))out.push({geometry:grown(feature.geometry,1.2),properties:{base:k*2.8+.35,top:k*2.8+1.6,color:COLORS.glow}});}
    else out.push({geometry:{type:'Polygon',coordinates:[[...circle([stop.longitude,stop.latitude],26),...circle([stop.longitude,stop.latitude],20).reverse()]]},properties:{base:0,top:1.2,color:COLORS.glow}});
    map.getSource('inspect').setData({type:'FeatureCollection',features:out.map((f,i)=>({type:'Feature',id:i,...f}))});
  }
  function pulse(state){
    cancelAnimationFrame(state.pulse);
    const map=state.map;if(!map||reduced.matches)return;
    const loop=now=>{if(state.closed||!state.map||state.mode!=='3d')return;
      if(document.hidden||!state.container.offsetParent){state.pulse=requestAnimationFrame(loop);return;}
      const k=(Math.sin(now/380)+1)/2;
      if(map.getLayer('inspect-bands'))map.setPaintProperty('inspect-bands','fill-extrusion-opacity',.45+k*.45);
      if(map.getLayer('stop-beacons'))map.setPaintProperty('stop-beacons','fill-extrusion-opacity',.22+k*.14);
      state.pulse=requestAnimationFrame(loop);};
    state.pulse=requestAnimationFrame(loop);
  }
  function paintProgress(state){
    const map=state.map,t=state.track;if(!map||!t||!map.getLayer('walking-route'))return;
    const f=Math.max(0,Math.min(1,state.along/t.total));
    map.setPaintProperty('walking-route','line-gradient',f<=0?['step',['line-progress'],COLORS.route,0,COLORS.route]:['step',['line-progress'],COLORS.walked,f,COLORS.route]);
    if(state.walker){state.walker.setLngLat(t.at(state.along));state.walker.setRotation(t.heading(state.along));}
    state.markers.forEach((marker,i)=>marker.getElement().classList.toggle('is-far',state.phase==='walking'&&Math.abs(t.stopDistances[i]-state.along)>320));
  }
  function streetView(state,along,heading,eye){
    const t=state.track,p=t.at(along),c=state.cfg;
    if(state.isTour)return state.map.calculateCameraOptionsFromTo(p,eye,t.centre,0);
    return state.map.calculateCameraOptionsFromTo(offset(p,heading+180,c.behind*state.scale),eye,offset(p,heading,c.ahead*state.scale),c.look);
  }
  // Among tall towers the whole camera rig grows (same framing, higher and further back) so blocks stay readable.
  function rigScale(state,along){
    if(state.isTour)return 1;
    const p=state.track.at(along);let tallest=0;
    for(const f of state.solids)if(f.h>tallest&&distance(f.center,p)<WALK.nearBlocks)tallest=f.h;
    return Math.min(WALK.maxScale,Math.max(1,(tallest*1.15+15)/WALK.eye));
  }
  // Keep the camera above any block between it and the walker instead of flying through it.
  function requiredEye(state,along,heading){
    const c=state.cfg,k=state.scale,p=state.track.at(along);
    if(state.isTour)return Math.max(c.eye,heightAt(state,p)+c.clearance);
    const back=offset(p,heading+180,c.behind*k),mid=offset(p,heading+180,c.behind*k/2);
    return Math.max(c.eye*k,heightAt(state,back)+c.clearance,heightAt(state,mid)+c.clearance*.6);
  }
  function placeStreet(state,instant){
    if(!state.map||!state.track)return;
    if(instant){state.scale=rigScale(state,state.along);state.eye=requiredEye(state,state.along,state.heading);}
    state.map.jumpTo(streetView(state,state.along,state.heading,state.eye));paintProgress(state);progressText(state);
  }
  function syncStop(state){
    if(state.isTour){update(state);return;}
    const t=state.track;let index=0;t.stopDistances.forEach((d,i)=>{if(d<=state.along+3)index=i;});
    if(index!==state.index)select(state,index);else update(state);
  }
  function stopMotion(state){cancelAnimationFrame(state.frame);clearTimeout(state.timer);state.frame=0;state.timer=0;state.map?.stop();}
  // While walking, every block is a little see-through so the path ahead is never fully hidden.
  function walkingLook(state,on){
    const map=state.map;if(!map?.getLayer('building-heights'))return;
    map.setPaintProperty('building-heights','fill-extrusion-opacity',on?.8:.95);map.setPaintProperty('building-roofs','fill-extrusion-opacity',on?.8:.95);
    map.setPaintProperty('context-heights','fill-extrusion-opacity',on?.45:.62);map.setPaintProperty('context-roofs','fill-extrusion-opacity',on?.45:.62);
    if(map.getLayer('city-heights')){map.setPaintProperty('city-heights','fill-extrusion-opacity',on?.4:.55);map.setPaintProperty('city-roofs','fill-extrusion-opacity',on?.4:.55);}
  }
  function closeCallout(state){state.callout?.remove();state.callout=null;state.look?.dispose();state.look=null;setBands(state,null);}
  function pause(state){if(state.closed)return;stopMotion(state);state.playing=false;state.phase='idle';closeCallout(state);state.container.classList.remove('is-walking');walkingLook(state,false);paintProgress(state);update(state);}
  function select(state,index){state.index=index;state.onSelect?.(state.plan.stops[index]?.id);update(state);}
  function fit(state,duration=reduced.matches?0:900){
    if(!state.map)return;
    const bounds=new maplibregl.LngLatBounds();state.plan.stops.forEach(stop=>bounds.extend([stop.longitude,stop.latitude]));
    (state.track?.points||[]).forEach(point=>bounds.extend(point));
    if(bounds.isEmpty())return;
    try{state.map.fitBounds(bounds,{padding:{top:60,bottom:36,left:36,right:36},maxZoom:17.4,pitch:state.isTour?55:48,bearing:-18,duration});}
    catch(error){
      // MapLibre occasionally cannot frame bounds while the container is still being laid out; show the route centre now and frame again next frame.
      state.fitDebug={error:String(error&&error.message||error).slice(0,200),size:[state.container.clientWidth,state.container.clientHeight]};
      try{state.map.jumpTo({center:bounds.getCenter(),zoom:state.isTour?13.5:16.4,pitch:state.isTour?55:48,bearing:-18});}catch{}
      if(!state.fitRetried){state.fitRetried=true;requestAnimationFrame(()=>{if(!state.closed&&state.map)fit(state,duration);});}
    }
  }
  // The stop callout: the checklist, with one item shown as a live 3D illustration and highlighted on the block.
  function showCallout(state,index){
    closeCallout(state);
    const stop=state.plan.stops[index];if(!stop||!state.map)return;
    const key=stopKey(state,index),list=stop.checklist||[],current=key?list.findIndex(item=>window.Checklist3D.keyFor(item)===key):-1;
    // A card pinned inside the 3D view (never clipped, never covering the stop); the beacon and glow mark the place.
    const box=document.createElement('aside');box.className='route-callout-body route-stop-card';box.setAttribute('aria-label',`Stop ${index+1} checklist`);
    box.innerHTML=`<strong><span>${index+1}</span>${esc(stop.name)}</strong>${key&&looksAvailable()?'<div class="route-callout-look"></div>':''}${list.length?`<ul>${list.slice(0,3).map((item,i)=>`<li class="${i===current?'is-now':''}">${esc(item)}</li>`).join('')}</ul>`:''}<small>${key&&looksAvailable()?'Illustration of what to look for · ':''}A place to check, not a confirmed breeding site.</small>`;
    state.container.append(box);state.callout={remove:()=>box.remove()};
    const host=box.querySelector('.route-callout-look');
    if(host){state.look=window.Checklist3D.live(host,key);setBands(state,key);}
    else setBands(state,null);
  }
  // Still view of one stop from the street, in the same camera family as the walk (no zoom pumping).
  function goToStop(state,index){
    if(state.closed||!state.map||!state.ready||state.isTour||index<0||index>=state.plan.stops.length)return;
    pause(state);select(state,index);
    const stop=state.plan.stops[index],t=state.track;
    if(t){state.along=t.stopDistances[index];state.heading=state.target=t.legHeading(state.along);}
    const heading=t?state.heading:state.map.getBearing(),target=[stop.longitude,stop.latitude];
    const view=state.map.calculateCameraOptionsFromTo(offset(target,heading+180,150),120,target,10);
    if(reduced.matches)state.map.jumpTo(view);else state.map.easeTo({...view,duration:1100,easing:x=>x*(2-x)});
    paintProgress(state);progressText(state);showCallout(state,index);
  }
  function togglePlay(state){
    if(state.playing){pause(state);return;}
    const t=state.track;if(reduced.matches||!t||!state.map||!state.ready)return;
    if(state.along>=t.total-1){state.along=0;if(!state.isTour)select(state,0);}
    closeCallout(state);
    state.playing=true;state.phase='intro';state.container.classList.add('is-walking');
    state.heading=state.target=t.legHeading(state.along);state.scale=rigScale(state,state.along);state.eye=requiredEye(state,state.along,state.heading);walkingLook(state,!state.isTour);
    state.nextStop=t.stopDistances.findIndex(d=>d>=state.along-0.5);
    // Descend from wherever the user is looking to street level, then walk.
    if(state.along<1)titleCard(state);
    state.map.easeTo({...streetView(state,state.along,state.heading,state.eye),duration:WALK.introMs,easing:x=>1-Math.pow(1-x,3)});
    state.timer=setTimeout(()=>{if(!state.playing)return;state.phase='walking';state.lastFrame=performance.now();state.frame=requestAnimationFrame(now=>step(state,now));},WALK.introMs+60);
    update(state);
  }
  function step(state,now){
    if(state.closed||!state.playing||state.mode!=='3d')return;
    const t=state.track,c=state.cfg,dt=Math.min(.12,(now-state.lastFrame)/1000);state.lastFrame=now;
    if(state.phase==='dwell'){
      // First a street-level look at the stop (the camera eases down and holds), then a slow quarter-turn while the checklist shows.
      if(now<state.eyeUntil){state.frame=requestAnimationFrame(next=>step(state,next));return;}
      if(state.eyeUntil){state.eyeUntil=0;state.eyeReturn=now+640;state.map.easeTo({...streetView(state,state.along,state.heading,state.eye),duration:620,easing:x=>x*(2-x)});}
      if(now<state.eyeReturn){state.frame=requestAnimationFrame(next=>step(state,next));return;}
      if(!state.isTour)state.heading+=7*dt;
      if(now>=state.dwellUntil){closeCallout(state);state.phase='walking';}
    }else{
      const next=state.nextStop>=0&&state.nextStop<t.stopDistances.length?t.stopDistances[state.nextStop]:t.total;
      const prev=state.nextStop>0?t.stopDistances[state.nextStop-1]:0;
      // Ease into and out of each stop instead of braking hard (a flyover keeps a steady pace).
      const target=state.isTour?1:Math.max(.22,Math.min(1,(next-state.along)/WALK.slowZone,(state.along-prev+12)/WALK.slowZone));
      state.speedFactor+=(target-state.speedFactor)*(1-Math.exp(-dt/.35));
      state.along=Math.min(next,state.along+c.speed*state.multiplier*state.speedFactor*dt);
      if(state.along>=next-.01){
        if(state.nextStop>=0&&state.nextStop<t.stopDistances.length){
          const looking=!!stopKey(state,state.nextStop)&&looksAvailable();
          select(state,state.nextStop);showCallout(state,state.nextStop);state.target=t.legHeading(state.along);state.nextStop++;state.phase='dwell';state.dwellUntil=now+(looking?WALK.lookDwell:WALK.dwell)*1000/Math.sqrt(state.multiplier);
          const eye=eyeView(state,state.index);state.eyeUntil=0;state.eyeReturn=0;
          // The street-level ease must not be cancelled by this frame's follow-camera jump: schedule the next frame and leave.
          if(eye){state.eyeUntil=now+2400/Math.sqrt(state.multiplier);state.dwellUntil+=1200;state.map.easeTo({...eye,duration:700,easing:x=>1-Math.pow(1-x,2)});paintProgress(state);progressText(state);state.frame=requestAnimationFrame(next=>step(state,next));return;}
        }else if(state.along>=t.total-.01){finishWalk(state);return;}
      }
    }
    // Ease towards the leg heading with a turn-rate limit: smooth, never a spin.
    if(!state.isTour&&state.phase!=='dwell'){const wanted=turn(state.heading,state.target??t.legHeading(state.along)),limit=WALK.maxTurn*dt;
      state.heading+=Math.max(-limit,Math.min(limit,wanted*(1-Math.exp(-dt/WALK.tau))));}
    state.scale+=(rigScale(state,state.along)-state.scale)*(1-Math.exp(-dt/1.8));
    state.eye+=(requiredEye(state,state.along,state.heading)-state.eye)*(1-Math.exp(-dt/.6));
    state.map.jumpTo(streetView(state,state.along,state.heading,state.eye));
    if(now-state.lastPaint>110){state.lastPaint=now;paintProgress(state);progressText(state);}
    state.frame=requestAnimationFrame(next=>step(state,next));
  }
  function finishWalk(state){
    state.playing=false;state.phase='idle';closeCallout(state);state.container.classList.remove('is-walking');walkingLook(state,false);
    state.along=state.track.total;paintProgress(state);update(state);
    fit(state,WALK.outroMs);
    state.tour.querySelector('.route-tour-stop span').innerHTML=state.isTour?`<b>Flyover complete</b> · ${esc(state.area.name)}`:`<b>Route complete</b> · ${esc(km(state.track.total))}, ${state.plan.stops.length} stops`;
    (state.done||[]).splice(0).forEach(r=>r());
  }
  // For the story and automated checks: resolves when the current walk reaches its end (or after maxMs).
  function whenDone(maxMs=120000){const s=current;if(!s)return Promise.resolve();return new Promise(resolve=>{(s.done||(s.done=[])).push(resolve);setTimeout(resolve,maxMs);});}
  function setSpeed(m){const s=current;if(!s)return;s.multiplier=m===2?2:1;const b=s.tour.querySelector('[data-tour=speed]');if(b){b.textContent=`${s.multiplier}×`;b.setAttribute('aria-label',`Walking preview speed: ${s.multiplier===1?'normal':'double'}`);}}
  function fallback(state,message){
    if(state.closed)return;
    setMode(state,'2d');state.tour.hidden=false;state.tour.querySelector('.route-tour-controls').hidden=true;state.tour.querySelector('.route-tour-scene').hidden=true;state.tour.querySelector('.route-tour-stop').hidden=true;state.tour.querySelector('.route-scrub').hidden=true;
    state.tour.querySelector('.route-3d-legend').hidden=true;state.tour.querySelector('.route-3d-note').hidden=true;state.tour.querySelector('.route-3d-status').textContent=message;
    state.toolbar.querySelector('[data-map-mode="3d"]').disabled=true;
    state.map?.remove();state.map=null;
  }
  function describe(p){
    if(p.role==='city'){const kind=p.kind?esc(String(p.kind).replace(/_/g,' ')):'building';const h=Number(p.height_m)>0?`about ${Math.round(p.height_m)} m${p.height_method==='overture_num_floors_x3m'?` (${esc(p.max_floor_lvl)} floors × 3 m)`:' (listed height)'}`:'Height not listed · shown flat';return `<strong>${esc(p.name||'Building')}</strong><span>${kind} · not HDB · context only</span><span>${h}</span><small>Overture Maps · © OpenStreetMap contributors</small>`;}
    const name=`Blk ${esc(p.block)}${p.road?` ${esc(p.road)}`:''}`;
    const role=p.role==='stop'?`Stop ${esc(p.stop_number??'')}${p.cluster_block?' · cluster block':''}`:p.cluster_block?'Cluster block':'Nearby HDB block';
    const height=Number(p.height_m)>0?`${esc(p.max_floor_lvl)} storeys · about ${Math.round(p.height_m)} m (estimate)`:'Storeys not verified · shown flat';
    const homes=Number(p.dwelling_units)>0?`<span>${Number(p.dwelling_units).toLocaleString('en-SG')} homes${Number(p.year_completed)>0?` · completed ${esc(p.year_completed)}`:''}</span>`:'';
    let uses=p.uses;if(typeof uses==='string'){try{uses=JSON.parse(uses);}catch{uses=[];}}
    return `<strong>${name}</strong><span>${role}</span><span>${height}</span>${homes}${Array.isArray(uses)&&uses.length?`<span>${esc(uses.join(', '))}</span>`:''}<small>HDB footprint · data.gov.sg</small>`;
  }
  function chevron(){
    const size=32,canvas=document.createElement('canvas');canvas.width=canvas.height=size;const c=canvas.getContext('2d');
    c.strokeStyle='#fffef7';c.lineWidth=4;c.lineCap='round';c.lineJoin='round';c.beginPath();c.moveTo(10,9);c.lineTo(22,16);c.lineTo(10,23);c.stroke();
    return c.getImageData(0,0,size,size);
  }
  function beacons(state){
    return {type:'FeatureCollection',features:state.plan.stops.map((stop,i)=>{
      const f=state.buildings?.features.find(b=>b.properties.stop_id===stop.id),h=Number(f?.properties.height_m)||0;
      const outcome=window.Insights?.community()?.by_stop?.[stop.id]?.outcome||stop.field_outcome?.outcome||null;
      return {type:'Feature',id:i,properties:{base:h+6,top:h+46,outcome},geometry:{type:'Polygon',coordinates:[circle([stop.longitude,stop.latitude],3.2,20)]}};})};
  }
  async function enterFullscreen(state){
    if(state.fullscreen||state.closed)return;
    // Nothing moves in the DOM (a reparented WebGL canvas stops painting): the map wrap and the controls become fixed layers.
    const head=document.createElement('div');head.className='walk-fullscreen-head';head.setAttribute('role','dialog');head.setAttribute('aria-label',`3D walk, ${state.area.name}`);
    head.innerHTML=`<strong>${esc(state.area.name)}</strong><span>${state.isTour?'3D flyover':'Swipe for the next stop'}</span><button type="button" class="icon-button walk-fullscreen-close" aria-label="Close full screen"><i class="ph ph-x" aria-hidden="true"></i></button>`;
    document.body.append(head);state.fullscreen=head;document.body.classList.add('walk-fullscreen-open');state.wrap.classList.add('is-fullscreen');state.tour.classList.add('is-fullscreen');
    head.querySelector('.walk-fullscreen-close').onclick=()=>exitFullscreen(state);
    state.fsKey=e=>{if(e.key==='Escape'){e.preventDefault();exitFullscreen(state);}};document.addEventListener('keydown',state.fsKey);
    // Swipe left or right for the next or previous stop (a tap or drag on the map itself still rotates it).
    let sx=null,sy=null;
    state.fsStart=e=>{if(e.touches.length===1){sx=e.touches[0].clientX;sy=e.touches[0].clientY;}};
    state.fsEnd=e=>{if(sx==null)return;const dx=e.changedTouches[0].clientX-sx,dy=e.changedTouches[0].clientY-sy;sx=null;if(Math.abs(dx)>70&&Math.abs(dx)>Math.abs(dy)*1.5&&!state.isTour)goToStop(state,state.index+(dx<0?1:-1));};
    state.wrap.addEventListener('touchstart',state.fsStart,{passive:true});state.wrap.addEventListener('touchend',state.fsEnd,{passive:true});
    try{state.wakeLock=await navigator.wakeLock?.request('screen');}catch{}
    try{await document.documentElement.requestFullscreen?.();}catch{}
    const settle=()=>{state.map?.resize();};requestAnimationFrame(settle);setTimeout(settle,350);setTimeout(settle,900);
  }
  function exitFullscreen(state){
    const head=state.fullscreen;if(!head)return;state.fullscreen=null;
    document.removeEventListener('keydown',state.fsKey);state.wrap.removeEventListener('touchstart',state.fsStart);state.wrap.removeEventListener('touchend',state.fsEnd);
    try{state.wakeLock?.release();}catch{}state.wakeLock=null;
    if(document.fullscreenElement)document.exitFullscreen?.().catch(()=>{});
    head.remove();document.body.classList.remove('walk-fullscreen-open');state.wrap.classList.remove('is-fullscreen');state.tour.classList.remove('is-fullscreen');
    requestAnimationFrame(()=>state.map?.resize());setTimeout(()=>state.map?.resize(),300);
  }
  async function setMode(state,mode){
    if(state.closed)return;
    if(mode==='full'){if(state.mode!=='3d')await setMode(state,'3d');return enterFullscreen(state);}
    state.mode=mode;pause(state);
    state.toolbar.querySelectorAll('[data-map-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.mapMode===mode)));
    state.container.hidden=mode!=='3d';$('#inspection-map').hidden=mode==='3d';$('#fit-inspection').hidden=mode==='3d';
    state.wrap.classList.toggle('is-3d',mode==='3d');state.tour.hidden=mode!=='3d';
    $('.inspection-legend')?.classList.toggle('is-hidden-3d',mode==='3d');
    state.opts.onMode?.(mode);
    if(mode==='2d'){cancelAnimationFrame(state.pulse);return;}
    if(state.map){state.map.resize();pulse(state);return;}
    if(state.loading)return;state.loading=true;
    state.tour.querySelector('.route-3d-status').textContent=state.isTour?'Loading the area, parks and water…':'Loading the route and official building shapes…';
    state.container.classList.add('is-loading');
    try{
      const [gl,artifact,walk]=await Promise.all([loadLibrary(),state.opts.buildings?Promise.resolve(null):loadFootprints(),state.opts.loadWalk?state.opts.loadWalk(state.area.code).catch(()=>null):Promise.resolve(null)]);if(state.closed)return;
      if(gl.supported&&!gl.supported())throw new Error('WebGL unavailable');
      const buildings=state.opts.buildings||artifact?.areas?.[state.area.code]||empty();state.buildings=buildings;state.margin=Number(state.opts.margin||artifact?.method?.context_margin_m)||null;
      const landuse=walk?.landuse||empty();
      state.solids=buildings.features.filter(f=>Number(f.properties.height_m)>0).map(f=>{const rings=f.geometry.type==='Polygon'?[f.geometry.coordinates[0]]:f.geometry.coordinates.map(p=>p[0]);const xs=rings.flat().map(c=>c[0]),ys=rings.flat().map(c=>c[1]);return {h:Number(f.properties.height_m),rings,box:[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)],center:[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2]};});
      const start=state.plan.stops[0]?[state.plan.stops[0].longitude,state.plan.stops[0].latitude]:state.track.centre;
      state.map=new gl.Map({container:state.container,style:{version:8,sources:{onemap:{type:'raster',tiles:['https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png'],tileSize:256,maxzoom:19,attribution:'<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener">OneMap</a> © Singapore Land Authority · HDB footprints & storeys / NEA / URA via data.gov.sg · other buildings © OpenStreetMap contributors via Overture Maps'}},layers:[{id:'background',type:'background',paint:{'background-color':'#eef0e8'}},{id:'onemap',type:'raster',source:'onemap',paint:{'raster-saturation':-.6,'raster-contrast':-.1,'raster-brightness-min':.1,'raster-opacity':.9}}]},...(window.RouteFlythrough.arrival?{center:window.RouteFlythrough.arrival.center,zoom:Math.max(10,window.RouteFlythrough.arrival.zoom),pitch:Math.min(82,window.RouteFlythrough.arrival.pitch),bearing:window.RouteFlythrough.arrival.bearing}:{center:start,zoom:state.isTour?13.5:16.6,pitch:48,bearing:-18}),maxZoom:22,minZoom:10,maxPitch:82,antialias:true,attributionControl:{compact:true},cooperativeGestures:true});
      state.map.addControl(new gl.NavigationControl({visualizePitch:true}),"bottom-right");state.map.keyboard.disable();
      state.map.on('error',event=>{if(event.sourceId!=='onemap'||state.tileError)return;state.tileError=true;const status=state.tour.querySelector('.route-3d-status');status.textContent=`${status.textContent} OneMap street tiles are unavailable; building shapes, stops and the saved route remain visible.`.trim();});
      state.map.getCanvas().addEventListener('webglcontextlost',()=>fallback(state,'3D graphics became unavailable. Continue with the 2D map and numbered checklist.'),{once:true});
      ['dragstart','rotatestart','pitchstart'].forEach(name=>state.map.on(name,event=>{if(event.originalEvent)pause(state);}));state.map.on('zoomstart',event=>{if(event.originalEvent)pause(state);});
      // Build the scene as soon as the (inline) style is ready; 'load' also waits for OneMap tiles, which can take
      // many seconds on a slow network. Whichever comes first wins.
      // (isStyleLoaded() also waits for tiles, so check the parsed style itself.)
      let built=false;const whenReady=()=>{const m=state.map;if(built||state.closed||!m||!(m.style?._loaded??m.isStyleLoaded()))return false;built=true;build();return true;};
      state.map.once('load',whenReady);state.map.once('style.load',whenReady);state.map.on('styledata',whenReady);
      const poll=setInterval(()=>{if(built||state.closed||whenReady())clearInterval(poll);},250);
      const build=()=>{try{buildScene();}catch(error){state.buildError=String(error&&error.stack||error).slice(0,400);state.container.classList.remove('is-loading');state.tour.querySelector('.route-3d-status').textContent='The 3D scene could not be built on this device. Continue with the 2D map and numbered checklist.';setMode(state,'2d');}};
      const buildScene=()=>{
        if(state.closed||!state.map)return;
        state.map.off('styledata',whenReady);
        const map=state.map,rise=['coalesce',['feature-state','rise'],1],roofAt=['*',['max',0,['-',['get','height_m'],WALK.roof]],rise],fullH=['*',['get','height_m'],rise];
        const color=['case',['boolean',['feature-state','selected'],false],COLORS.selected,['==',['get','cluster_block'],true],COLORS.cluster,['==',['get','role'],'stop'],COLORS.stop,COLORS.context];
        const roof=['case',['boolean',['feature-state','selected'],false],COLORS.roofSelected,['==',['get','cluster_block'],true],COLORS.roofCluster,['==',['get','role'],'stop'],COLORS.roofStop,COLORS.roofContext];
        map.setLight({anchor:'viewport',color:'#fff6e6',intensity:.38,position:[1.25,200,35]});
        // A soft sky and distance haze keep the street-level horizon calm and hide far, blurry tiles.
        try{map.setSky({'sky-color':'#cfe3ec','horizon-color':'#f1f3ea','fog-color':'#eef0e8','sky-horizon-blend':.6,'horizon-fog-blend':.7,'fog-ground-blend':.3,'atmosphere-blend':0});}catch{}
        // URA Master Plan zoning: parks and water sit on the base map, under everything else.
        map.addSource('landuse',{type:'geojson',data:landuse});
        map.addLayer({id:'landuse-green',type:'fill',source:'landuse',filter:['==',['get','kind'],'green'],paint:{'fill-color':COLORS.green,'fill-opacity':.62}});
        map.addLayer({id:'landuse-beach',type:'fill',source:'landuse',filter:['==',['get','kind'],'beach'],paint:{'fill-color':COLORS.beach,'fill-opacity':.7}});
        map.addLayer({id:'landuse-water',type:'fill',source:'landuse',filter:['==',['get','kind'],'water'],paint:{'fill-color':COLORS.water,'fill-opacity':.85}});
        map.addLayer({id:'landuse-water-edge',type:'line',source:'landuse',filter:['==',['get','kind'],'water'],paint:{'line-color':'#5fa6c6','line-width':1.2,'line-opacity':.7}});
        map.addSource('buildings',{type:'geojson',data:buildings,promoteId:'id'});
        // A blurred line along each footprint grounds the blocks with a soft contact shadow.
        map.addLayer({id:'building-shadow',type:'line',source:'buildings',filter:['>',['coalesce',['get','height_m'],0],0],paint:{'line-color':'#26332b','line-width':['interpolate',['linear'],['zoom'],14,2,17,9,19,26],'line-blur':['interpolate',['linear'],['zoom'],14,2,17,8,19,22],'line-opacity':.2}});
        // Shadows cast by the estimated block heights along today's sun (an estimate of an estimate; labelled as such).
        map.addSource('shadows',{type:'geojson',data:empty()});
        map.addLayer({id:'shadows',type:'fill',source:'shadows',paint:{'fill-color':'#16231c','fill-opacity':.17,'fill-antialias':false}},'building-shadow');
        map.addLayer({id:'building-flat',type:'fill',source:'buildings',filter:['!',['>',['coalesce',['get','height_m'],0],0]],paint:{'fill-color':['case',['==',['get','role'],'city'],COLORS.city,['==',['get','role'],'context'],COLORS.flat,color],'fill-opacity':.9,'fill-outline-color':'#a59f8e'}});
        map.addLayer({id:'building-base',type:'line',source:'buildings',filter:['all',['!=',['get','role'],'context'],['!=',['get','role'],'city']],paint:{'line-color':['case',['==',['get','cluster_block'],true],COLORS.cluster,COLORS.stop],'line-width':1.4}});
        // Surrounding blocks are see-through so they never hide the stop being previewed. A lighter roof cap
        // (the top 0.7 m) gives every block a crisp roofline.
        const raised=['>',['coalesce',['get','height_m'],0],0];
        // Non-HDB buildings first (lowest), in a neutral grey so the official data stands out.
        map.addLayer({id:'city-heights',type:'fill-extrusion',source:'buildings',filter:['all',raised,['==',['get','role'],'city']],paint:{'fill-extrusion-color':COLORS.city,'fill-extrusion-height':roofAt,'fill-extrusion-base':0,'fill-extrusion-opacity':.55,'fill-extrusion-vertical-gradient':true}});
        map.addLayer({id:'city-roofs',type:'fill-extrusion',source:'buildings',filter:['all',raised,['==',['get','role'],'city']],paint:{'fill-extrusion-color':COLORS.roofCity,'fill-extrusion-height':fullH,'fill-extrusion-base':roofAt,'fill-extrusion-opacity':.55,'fill-extrusion-vertical-gradient':false}});
        map.addLayer({id:'context-heights',type:'fill-extrusion',source:'buildings',filter:['all',raised,['==',['get','role'],'context']],paint:{'fill-extrusion-color':COLORS.context,'fill-extrusion-height':roofAt,'fill-extrusion-base':0,'fill-extrusion-opacity':.62,'fill-extrusion-vertical-gradient':true}});
        map.addLayer({id:'context-roofs',type:'fill-extrusion',source:'buildings',filter:['all',raised,['==',['get','role'],'context']],paint:{'fill-extrusion-color':COLORS.roofContext,'fill-extrusion-height':fullH,'fill-extrusion-base':roofAt,'fill-extrusion-opacity':.62,'fill-extrusion-vertical-gradient':false}});
        map.addLayer({id:'building-heights',type:'fill-extrusion',source:'buildings',filter:['all',raised,['!=',['get','role'],'context'],['!=',['get','role'],'city']],paint:{'fill-extrusion-color':color,'fill-extrusion-height':roofAt,'fill-extrusion-base':0,'fill-extrusion-opacity':.95,'fill-extrusion-vertical-gradient':true}});
        map.addLayer({id:'building-roofs',type:'fill-extrusion',source:'buildings',filter:['all',raised,['!=',['get','role'],'context'],['!=',['get','role'],'city']],paint:{'fill-extrusion-color':roof,'fill-extrusion-height':fullH,'fill-extrusion-base':roofAt,'fill-extrusion-opacity':.95,'fill-extrusion-vertical-gradient':false}});
        // Where to look on the current stop (roof edge, ground floor, corridor levels or a ground ring).
        map.addSource('inspect',{type:'geojson',data:empty()});
        map.addLayer({id:'inspect-bands',type:'fill-extrusion',source:'inspect',paint:{'fill-extrusion-color':['get','color'],'fill-extrusion-height':['get','top'],'fill-extrusion-base':['get','base'],'fill-extrusion-opacity':.8}});
        if(state.plan.clusters?.features?.length){map.addSource('clusters',{type:'geojson',data:state.plan.clusters});map.addLayer({id:'cluster-fill',type:'fill',source:'clusters',paint:{'fill-color':COLORS.cluster,'fill-opacity':.1}},'building-shadow');map.addLayer({id:'cluster-outline',type:'line',source:'clusters',paint:{'line-color':COLORS.cluster,'line-width':1.8,'line-dasharray':[3,2]}},'city-heights');
          // The cluster as a translucent volume: its height grows with the people in it (2 m a person, capped at 160 m).
          map.addLayer({id:'cluster-volume',type:'fill-extrusion',source:'clusters',paint:{'fill-extrusion-color':COLORS.cluster,'fill-extrusion-height':['min',160,['*',2,['coalesce',['get','cases'],0]]],'fill-extrusion-base':0,'fill-extrusion-opacity':.13,'fill-extrusion-vertical-gradient':false}});
          state.plan.clusters.features.forEach(f=>{const p=f.properties||{};if(!Number.isFinite(p.longitude)||!Number.isFinite(p.latitude))return;const label=document.createElement('span');label.className='route-cluster-label';label.innerHTML=`<b>${Number(p.cases)||0}</b> people in this cluster<small>${esc(String(p.name||'NEA cluster').split('/')[0].replace(/\s*\(.*$/,'').slice(0,38))}${p.growth_cases>0?` · +${p.growth_cases} in a week`:''}</small>`;(state.labels||(state.labels=[])).push(new gl.Marker({element:label,anchor:'bottom',offset:[0,-6]}).setLngLat([p.longitude,p.latitude]).addTo(map));});}
        // NEA areas with a high Aedes population, as faint violet volumes, where they fall inside this view.
        const aedes=window.DengueData?.aedes;
        if(aedes?.available!==false&&aedes?.features?.length){const box=[...(state.track?.points||[]),...state.plan.stops.map(s=>[s.longitude,s.latitude])];
          const xs=box.map(p=>p[0]),ys=box.map(p=>p[1]),near=f=>{const flat=JSON.stringify(f.geometry.coordinates).match(/-?\d+\.\d+/g)?.map(Number)||[];for(let i=0;i<flat.length;i+=2){if(flat[i]>Math.min(...xs)-.01&&flat[i]<Math.max(...xs)+.01&&flat[i+1]>Math.min(...ys)-.01&&flat[i+1]<Math.max(...ys)+.01)return true;}return false;};
          const nearby=aedes.features.filter(near);
          if(nearby.length){map.addSource('aedes',{type:'geojson',data:{type:'FeatureCollection',features:nearby}});map.addLayer({id:'aedes-volume',type:'fill-extrusion',source:'aedes',paint:{'fill-extrusion-color':'#8a63c9','fill-extrusion-height':24,'fill-extrusion-base':0,'fill-extrusion-opacity':.12}},'building-shadow');map.addLayer({id:'aedes-outline',type:'line',source:'aedes',paint:{'line-color':'#8a63c9','line-width':1.4,'line-opacity':.6}},'building-shadow');state.aedesNearby=nearby.length;}}
        if(state.opts.outline){map.addSource('outline',{type:'geojson',data:state.opts.outline});map.addLayer({id:'area-outline',type:'line',source:'outline',paint:{'line-color':COLORS.route,'line-width':2.2,'line-dasharray':[4,3],'line-opacity':.8}});}
        if(state.plan.route?.geometry&&!state.isTour){
          map.addSource('route',{type:'geojson',lineMetrics:true,data:{type:'Feature',properties:{},geometry:state.plan.route.geometry}});
          map.addLayer({id:'route-halo',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#fffef7','line-width':['interpolate',['linear'],['zoom'],15,7,19,16,22,40]}},'city-heights');
          map.addLayer({id:'walking-route',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':COLORS.route,'line-width':['interpolate',['linear'],['zoom'],15,3.5,19,9,22,24],...(state.track?{'line-gradient':['step',['line-progress'],COLORS.route,0,COLORS.route]}:{'line-dasharray':[2,2]})}},'city-heights');
          if(state.track){map.addImage('route-chevron',chevron());map.addLayer({id:'route-direction',type:'symbol',source:'route',layout:{'symbol-placement':'line','symbol-spacing':70,'icon-image':'route-chevron','icon-size':['interpolate',['linear'],['zoom'],15,.45,19,.8,22,1.6],'icon-rotation-alignment':'map','icon-pitch-alignment':'map','icon-allow-overlap':true,'icon-ignore-placement':true}},'city-heights');}
        }
        // A light column floats above every stop so the next ones stay findable among the towers.
        if(state.plan.stops.length){map.addSource('beacons',{type:'geojson',data:beacons(state)});map.addLayer({id:'stop-beacons',type:'fill-extrusion',source:'beacons',paint:{'fill-extrusion-color':['case',['boolean',['feature-state','selected'],false],COLORS.selected,['==',['get','outcome'],'water_found'],OUTCOME_COLORS.water_found,['==',['get','outcome'],'cleared'],OUTCOME_COLORS.cleared,['==',['get','outcome'],'nothing'],OUTCOME_COLORS.nothing,'#8fd1b4'],'fill-extrusion-height':['get','top'],'fill-extrusion-base':['get','base'],'fill-extrusion-opacity':.3,'fill-extrusion-vertical-gradient':true}});}
        state.plan.stops.forEach((stop,index)=>{const button=document.createElement('button');button.type='button';button.className='route-3d-pin';button.textContent=String(stop.number||index+1);button.setAttribute('aria-label',`Show stop ${index+1}: ${stop.name}`);button.onclick=event=>{event.stopPropagation();goToStop(state,index);};state.markers.push(new gl.Marker({element:button,anchor:'center'}).setLngLat([stop.longitude,stop.latitude]).addTo(map));});
        if(state.track&&!state.isTour){const dot=document.createElement('span');dot.className='route-walker';dot.setAttribute('aria-hidden','true');dot.innerHTML='<b class="route-walker-cone"></b><i class="ph ph-person-simple-walk"></i>';state.walker=new gl.Marker({element:dot,anchor:'center',rotationAlignment:'map',pitchAlignment:'viewport'}).setLngLat(state.track.at(state.along)).setRotation(state.track.heading(state.along)).addTo(map);}
        state.popup=new gl.Popup({closeButton:true,closeOnClick:true,maxWidth:'240px',className:'route-3d-popup'});
        ['building-heights','building-roofs','context-heights','context-roofs','city-heights','city-roofs','building-flat'].forEach(layer=>{map.on('click',layer,event=>{if(state.playing)return;const feature=event.features?.[0];if(!feature)return;state.popup.setLngLat(event.lngLat).setHTML(describe(feature.properties)).addTo(map);});map.on('mouseenter',layer,()=>{map.getCanvas().style.cursor='pointer';});map.on('mouseleave',layer,()=>{map.getCanvas().style.cursor='';});});
        const parks=landuse.features.filter(f=>f.properties.kind==='green').length,water=landuse.features.filter(f=>f.properties.kind==='water').length;
        const scene=landuse.features.length?` ${parks} park and ${water} water areas from URA zoning.`:'';
        if(state.isTour)state.tour.querySelector('.route-3d-status').textContent=(state.tileError?'OneMap street tiles are unavailable. ':'')+`${(()=>{const s=summary(buildings,state.plan);return (s.count?`${s.count} official HDB block shapes`:'No HDB blocks here')+(s.city?` and ${s.city} other buildings in grey (context).`:'.');})()}${scene}`;
        else{const s=summary(buildings,state.plan),walkText=state.track?` Walk: ${km(state.track.total)}${state.plan.route?.walking_seconds?`, about ${Math.round(state.plan.route.walking_seconds/60)} min on foot`:''}.`:'';
          state.tour.querySelector('.route-3d-status').textContent=(state.tileError?'OneMap street tiles are unavailable. ':'')+(s.count?`${s.count} official HDB block shapes${state.margin?` within about ${state.margin} m of the route`:''} · ${s.raised} raised from published storeys · ${s.flat} flat (storeys unverified)${s.city?` · ${s.city} other buildings in grey (Overture/OpenStreetMap, context only)`:''}${s.missing.length?` · no footprint matched for stop ${s.missing.join(', ')}`:''}.${scene}${walkText} Tap a block for details.`:`Building shapes are unavailable for this area. The verified stops and saved route remain visible.${scene}${walkText}`);}
        if(!state.isTour)select(state,state.index);
        // Arriving from the 3D island: the camera is still up where the island left it, so descend onto the route while
        // the blocks rise out of the ground; otherwise cut straight to the overview.
        const arriving=!!window.RouteFlythrough.arrival&&!reduced.matches;window.RouteFlythrough.arrival=null;
        if(arriving){riseIn(state);fit(state,1900);}else fit(state,0);
        paintProgress(state);if(state.mode==='3d')map.resize();
        state.container.classList.remove('is-loading');state.ready=true;update(state);pulse(state);
        const note=document.createElement('p');note.className='route-light-note';note.hidden=true;note.textContent='Aedes mosquitoes bite most in the two hours after sunrise and before sunset.';state.container.append(note);
        setHour(state,state.hour??13);
        const rain=window.DengueData?.current?.areas?.find(a=>a.code===state.area.code)?.weather?.rainfall;
        if(rain&&Number.isFinite(rain.value)&&window.Weather3D){state.rain=rain;const b=state.tour.querySelector('[data-tour=rain]');b.hidden=false;b.querySelector('span').textContent=`Rain · ${rain.value} mm`;b.title=`${rain.value} mm on ${new Date(rain.date+'T12:00:00+08:00').toLocaleDateString('en-SG',{day:'numeric',month:'short'})} at ${rain.station_name} (nearest NEA station, ${rain.distance_km} km away). Observed, not forecast.`;b.setAttribute('aria-label',b.title);}
        const openStop=window.RouteFlythrough.openStop;window.RouteFlythrough.openStop=null;
        if(openStop!=null&&!state.isTour&&openStop>=1&&openStop<=state.plan.stops.length)setTimeout(()=>{if(!state.closed)goToStop(state,openStop-1);},arriving?2100:400);
        else if(window.RouteFlythrough.autoplay){window.RouteFlythrough.autoplay=false;setTimeout(()=>{if(!state.closed&&state.mode==='3d')togglePlay(state);},arriving?2000:350);}
      };
    }catch{state.container.classList.remove('is-loading');fallback(state,'3D is unavailable on this device. Continue with the 2D map and numbered checklist.');}
    finally{state.loading=false;}
  }
  function focusStop(id){
    if(!current||current.mode!=='3d'||!current.map)return false;
    const index=current.plan.stops.findIndex(stop=>String(stop.id)===String(id));if(index<0)return false;
    goToStop(current,index);return true;
  }
  function dispose(){
    if(!current)return;const state=current;if(state.recorder){try{state.recorder.stop();}catch{}}pause(state);state.closed=true;(state.done||[]).splice(0).forEach(r=>r());cancelAnimationFrame(state.pulse);reduced.removeEventListener('change',state.motionChange);document.removeEventListener('visibilitychange',state.visibility);
    if(state.fullscreen)exitFullscreen(state);state.popup?.remove();closeCallout(state);state.map?.remove();state.toolbar.remove();state.tour.remove();state.container.remove();$('.inspection-legend')?.classList.remove('is-hidden-3d');current=null;
  }
  // Read-only state for automated checks and support; exposes no data beyond what is on screen.
  function snapshot(){const s=current;if(!s)return null;return {mode:s.mode,tour:s.isTour,phase:s.phase,playing:s.playing,along:s.along,total:s.track?.total??null,stop:s.index+1,stops:s.plan.stops.length,bearing:s.map?.getBearing()??null,pitch:s.map?.getPitch()??null,zoom:s.map?.getZoom()??null,look:s.callout?stopKey(s,s.index):null,bands:s.bandKey,eye:!!(s.eyeUntil&&performance.now()<s.eyeUntil),buildError:s.buildError||null,fitDebug:s.fitDebug||null,hour:s.hour??null,rain:!!s.rain,shadows:s.map?.getSource('shadows')?._data?.features?.length??null,landuse:s.map?.getSource("landuse")?._data?.features?.length??null,city:s.buildings?.features.filter(f=>f.properties.role==='city').length??null,ready:!!s.ready};}
  window.RouteFlythrough={mount,focusStop,dispose,snapshot,whenDone,setSpeed,setHour:h=>current&&setHour(current,h),sunAt,autoplay:false,arrival:null,openStop:null};
})();
