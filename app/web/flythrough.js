/* 3D walk preview for every area. Footprints are official HDB shapes; heights are estimates from published storeys.
   Cluster plans and routine walks follow a saved OneMap walking route; areas with no verified place get a flyover. */
(() => {
  'use strict';
  const $=s=>document.querySelector(s), reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const empty=()=>({type:'FeatureCollection',features:[]});
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const COLORS={selected:'#e3ad3c',cluster:'#c2523c',stop:'#2f6f58',context:'#ece6d8',flat:'#e3dfd3',route:'#1d4a3c',walked:'#c9921f',
    roofSelected:'#f6d58a',roofCluster:'#de8a73',roofStop:'#6ba48b',roofContext:'#faf8f1',green:'#bcd8a8',water:'#8cc3dc',beach:'#eadfbe',glow:'#36c2f5'};
  // Low follow camera: 80 m up and 90 m behind the walker, looking 45 m ahead (pitch about 59°). The walker
  // sits in the lower fifth of the frame with roughly 250 m of track visible ahead. Constant pace, gentle turns,
  // no zoom changes. A stop pauses long enough for one 3D checklist illustration.
  const WALK={speed:40,dwell:2.3,lookDwell:4.8,eye:80,behind:90,ahead:45,look:0,clearance:14,tau:.8,maxTurn:24,slowZone:60,legMin:150,nearBlocks:140,maxScale:1.6,introMs:1700,outroMs:1800,roof:.7};
  // What each checklist item highlights on the current stop's block (an illustration of where to look, not a finding).
  const BANDS={gutter:'roof',tray:'ground',pail:'corridors',drain:'ring',containers:'ring',bin:'ring',pond:'ring',treehole:'ring'};
  let current=null,library=null,footprints=null;

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
    const features=buildings.features,raised=features.filter(f=>Number(f.properties.height_m)>0).length;
    const matched=new Set(features.map(f=>f.properties.stop_id).filter(Boolean));
    const missing=plan.stops.filter(stop=>!matched.has(stop.id)&&/^block/.test(String(stop.place_type||'block'))).map(stop=>stop.number);
    return {count:features.length,raised,flat:features.length-raised,missing};
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
    toolbar.innerHTML=`<div class="route-view-tabs" role="group" aria-label="Inspection map view"><button type="button" data-map-mode="2d" aria-pressed="true"><i class="ph ph-map-trifold" aria-hidden="true"></i> 2D map</button><button type="button" data-map-mode="3d" aria-pressed="false"><i class="ph ph-cube" aria-hidden="true"></i> ${isTour?'3D flyover':'3D walk preview'}</button></div><span class="route-preview-label">Official HDB block shapes</span>`;
    column.insertBefore(toolbar,wrap);
    const container=document.createElement('div');container.id='route-3d';container.hidden=true;container.setAttribute('role','region');container.setAttribute('aria-label',isTour?'3D flyover of the area':'3D inspection route with estimated HDB block heights');wrap.prepend(container);
    const tour=document.createElement('section');tour.className='route-tour';tour.hidden=true;tour.setAttribute('aria-label','Route preview controls');
    const legend=isTour?`<li><b style="background:${COLORS.cluster};opacity:.5"></b>Cluster footprint</li><li><b style="background:${COLORS.context}"></b>HDB blocks</li><li><b style="background:${COLORS.green}"></b>Parks (URA zoning)</li><li><b style="background:${COLORS.water}"></b>Water</li>`
      :`<li><b style="background:${COLORS.selected}"></b>Current stop</li><li><b style="background:${COLORS.stop}"></b>Other stops</li><li><b style="background:${COLORS.cluster}"></b>Cluster blocks</li><li><b style="background:${COLORS.context}"></b>Other HDB blocks</li><li><b class="is-flat" style="background:${COLORS.flat}"></b>Storeys unverified (flat)</li><li><b style="background:${COLORS.green}"></b>Parks (URA zoning)</li><li><b style="background:${COLORS.water}"></b>Water</li><li><b style="background:${COLORS.glow}"></b>Where to look</li><li><b class="is-line" style="background:${COLORS.walked}"></b>Walked so far</li>`;
    tour.innerHTML=`<div class="route-tour-controls"><button type="button" data-tour="previous" aria-label="Previous inspection stop"><i class="ph ph-caret-left" aria-hidden="true"></i></button><button type="button" data-tour="play" class="route-tour-play"><i class="ph ph-play" aria-hidden="true"></i><span>Walk the route</span></button><button type="button" data-tour="next" aria-label="Next inspection stop"><i class="ph ph-caret-right" aria-hidden="true"></i></button><button type="button" data-tour="speed" class="route-tour-speed" aria-label="Walking preview speed: normal">1×</button><button type="button" data-tour="fit" aria-label="Show the whole route from above"><i class="ph ph-arrows-out-simple" aria-hidden="true"></i><span>${isTour?'Whole area':'Whole route'}</span></button></div>
      <div class="route-scrub"><label for="route-scrub-input" class="route-scrub-label">${isTour?'Around the area':'Along the route'}</label><input id="route-scrub-input" type="range" min="0" max="1000" step="1" value="0"><span class="route-scrub-text" aria-hidden="true"></span></div>
      <div class="route-tour-stop"><span role="status" aria-live="polite"></span><button type="button" data-tour="checklist">Checklist <i class="ph ph-arrow-down" aria-hidden="true"></i></button></div><ul class="route-3d-legend" aria-label="3D colours">${legend}</ul><p class="route-3d-note"></p><p class="route-3d-status" role="status"></p>`;
    wrap.after(tour);
    if(isTour){tour.querySelectorAll('[data-tour=previous],[data-tour=next],[data-tour=checklist]').forEach(b=>b.hidden=true);}
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
    tour.querySelector('[data-tour=checklist]').onclick=()=>{const card=document.getElementById('stop-'+state.plan.stops[state.index]?.id);card?.scrollIntoView({block:'center',behavior:reduced.matches?'instant':'smooth'});card?.querySelector('.stop-number')?.focus({preventScroll:true});};
    const scrub=tour.querySelector('#route-scrub-input');
    scrub.addEventListener('input',()=>{if(!state.track||!state.map)return;const fraction=Number(scrub.value)/1000;pause(state);state.along=state.track.total*fraction;state.heading=state.target=state.track.legHeading(state.along);placeStreet(state,true);syncStop(state);});
    state.motionChange=()=>{if(reduced.matches)pause(state);update(state);};reduced.addEventListener('change',state.motionChange);
    state.visibility=()=>{if(document.hidden)pause(state);};document.addEventListener('visibilitychange',state.visibility);
    state.keys=event=>{if(state.mode!=='3d'||state.isTour||event.target.closest('input,textarea,select'))return;if(event.key==='ArrowRight'&&!event.altKey){event.preventDefault();goToStop(state,state.index+1);}else if(event.key==='ArrowLeft'&&!event.altKey){event.preventDefault();goToStop(state,state.index-1);}};
    tour.addEventListener('keydown',state.keys);container.addEventListener('keydown',state.keys);
    update(state);
    if(opts.start3d)setMode(state,'3d');
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
      :`Shapes are official HDB footprints. Heights are estimates: published storeys × 2.8 m + 1.3 m roof, not surveyed. Condos, schools and other non-HDB buildings are not modelled. Parks and water are URA Master Plan zoning. At each stop a 3D illustration shows what to look for; glowing roofs or corridors mark where, not a finding. Places to check, not confirmed breeding sites.${motion}`;
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
    const loop=now=>{if(state.closed||!state.map||state.mode!=='3d')return;const k=(Math.sin(now/380)+1)/2;
      if(map.getLayer('inspect-bands'))map.setPaintProperty('inspect-bands','fill-extrusion-opacity',.45+k*.45);
      if(map.getLayer('stop-beacons'))map.setPaintProperty('stop-beacons','fill-extrusion-opacity',.22+k*.14);
      state.pulse=requestAnimationFrame(loop);};
    state.pulse=requestAnimationFrame(loop);
  }
  function paintProgress(state){
    const map=state.map,t=state.track;if(!map||!t||!map.getLayer('walking-route'))return;
    const f=Math.max(0,Math.min(1,state.along/t.total));
    map.setPaintProperty('walking-route','line-gradient',f<=0?['step',['line-progress'],COLORS.route,0,COLORS.route]:['step',['line-progress'],COLORS.walked,f,COLORS.route]);
    if(state.walker)state.walker.setLngLat(t.at(state.along));
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
  }
  function closeCallout(state){state.callout?.remove();state.callout=null;state.look?.dispose();state.look=null;setBands(state,null);}
  function pause(state){if(state.closed)return;stopMotion(state);state.playing=false;state.phase='idle';closeCallout(state);state.container.classList.remove('is-walking');walkingLook(state,false);paintProgress(state);update(state);}
  function select(state,index){state.index=index;state.onSelect?.(state.plan.stops[index]?.id);update(state);}
  function fit(state,duration=reduced.matches?0:900){
    if(!state.map)return;
    const bounds=new maplibregl.LngLatBounds();state.plan.stops.forEach(stop=>bounds.extend([stop.longitude,stop.latitude]));
    (state.track?.points||[]).forEach(point=>bounds.extend(point));
    if(bounds.isEmpty())return;
    state.map.fitBounds(bounds,{padding:{top:60,bottom:36,left:36,right:36},maxZoom:17.4,pitch:state.isTour?55:48,bearing:-18,duration});
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
    state.map.easeTo({...streetView(state,state.along,state.heading,state.eye),duration:WALK.introMs,easing:x=>1-Math.pow(1-x,3)});
    state.timer=setTimeout(()=>{if(!state.playing)return;state.phase='walking';state.lastFrame=performance.now();state.frame=requestAnimationFrame(now=>step(state,now));},WALK.introMs+60);
    update(state);
  }
  function step(state,now){
    if(state.closed||!state.playing||state.mode!=='3d')return;
    const t=state.track,c=state.cfg,dt=Math.min(.12,(now-state.lastFrame)/1000);state.lastFrame=now;
    if(state.phase==='dwell'){
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
        }else if(state.along>=t.total-.01){finishWalk(state);return;}
      }
    }
    // Ease towards the leg heading with a turn-rate limit: smooth, never a spin.
    if(!state.isTour){const wanted=turn(state.heading,state.target??t.legHeading(state.along)),limit=WALK.maxTurn*dt;
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
  }
  function fallback(state,message){
    if(state.closed)return;
    setMode(state,'2d');state.tour.hidden=false;state.tour.querySelector('.route-tour-controls').hidden=true;state.tour.querySelector('.route-tour-stop').hidden=true;state.tour.querySelector('.route-scrub').hidden=true;
    state.tour.querySelector('.route-3d-legend').hidden=true;state.tour.querySelector('.route-3d-note').hidden=true;state.tour.querySelector('.route-3d-status').textContent=message;
    state.toolbar.querySelector('[data-map-mode="3d"]').disabled=true;
    state.map?.remove();state.map=null;
  }
  function describe(p){
    const name=`Blk ${esc(p.block)}${p.road?` ${esc(p.road)}`:''}`;
    const role=p.role==='stop'?`Stop ${esc(p.stop_number??'')}${p.cluster_block?' · cluster block':''}`:p.cluster_block?'Cluster block':'Nearby HDB block';
    const height=Number(p.height_m)>0?`${esc(p.max_floor_lvl)} storeys · about ${Math.round(p.height_m)} m (estimate)`:'Storeys not verified · shown flat';
    let uses=p.uses;if(typeof uses==='string'){try{uses=JSON.parse(uses);}catch{uses=[];}}
    return `<strong>${name}</strong><span>${role}</span><span>${height}</span>${Array.isArray(uses)&&uses.length?`<span>${esc(uses.join(', '))}</span>`:''}<small>HDB footprint · data.gov.sg</small>`;
  }
  function chevron(){
    const size=32,canvas=document.createElement('canvas');canvas.width=canvas.height=size;const c=canvas.getContext('2d');
    c.strokeStyle='#fffef7';c.lineWidth=4;c.lineCap='round';c.lineJoin='round';c.beginPath();c.moveTo(10,9);c.lineTo(22,16);c.lineTo(10,23);c.stroke();
    return c.getImageData(0,0,size,size);
  }
  function beacons(state){
    return {type:'FeatureCollection',features:state.plan.stops.map((stop,i)=>{
      const f=state.buildings?.features.find(b=>b.properties.stop_id===stop.id),h=Number(f?.properties.height_m)||0;
      return {type:'Feature',id:i,properties:{base:h+6,top:h+46},geometry:{type:'Polygon',coordinates:[circle([stop.longitude,stop.latitude],3.2,20)]}};})};
  }
  async function setMode(state,mode){
    if(state.closed)return;
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
      state.map=new gl.Map({container:state.container,style:{version:8,sources:{onemap:{type:'raster',tiles:['https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png'],tileSize:256,maxzoom:19,attribution:'<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener">OneMap</a> © Singapore Land Authority · HDB footprints & storeys / NEA / URA via data.gov.sg'}},layers:[{id:'background',type:'background',paint:{'background-color':'#eef0e8'}},{id:'onemap',type:'raster',source:'onemap',paint:{'raster-saturation':-.6,'raster-contrast':-.1,'raster-brightness-min':.1,'raster-opacity':.9}}]},center:start,zoom:state.isTour?13.5:16.6,pitch:48,bearing:-18,maxZoom:22,minZoom:10,maxPitch:82,antialias:true,attributionControl:{compact:true}});
      state.map.addControl(new gl.NavigationControl({visualizePitch:true}),"bottom-right");state.map.scrollZoom.disable();state.map.keyboard.disable();
      state.map.on('error',event=>{if(event.sourceId!=='onemap'||state.tileError)return;state.tileError=true;const status=state.tour.querySelector('.route-3d-status');status.textContent=`${status.textContent} OneMap street tiles are unavailable; building shapes, stops and the saved route remain visible.`.trim();});
      state.map.getCanvas().addEventListener('webglcontextlost',()=>fallback(state,'3D graphics became unavailable. Continue with the 2D map and numbered checklist.'),{once:true});
      ['dragstart','rotatestart','pitchstart'].forEach(name=>state.map.on(name,event=>{if(event.originalEvent)pause(state);}));state.map.on('zoomstart',event=>{if(event.originalEvent)pause(state);});
      // Build the scene as soon as the (inline) style is ready; 'load' also waits for OneMap tiles, which can take
      // many seconds on a slow network. Whichever comes first wins.
      // (isStyleLoaded() also waits for tiles, so check the parsed style itself.)
      let built=false;const whenReady=()=>{const m=state.map;if(built||state.closed||!m||!(m.style?._loaded??m.isStyleLoaded()))return false;built=true;build();return true;};
      state.map.once('load',whenReady);state.map.once('style.load',whenReady);state.map.on('styledata',whenReady);
      const poll=setInterval(()=>{if(built||state.closed||whenReady())clearInterval(poll);},250);
      const build=()=>{
        if(state.closed||!state.map)return;
        state.map.off('styledata',whenReady);
        const map=state.map,roofAt=['max',0,['-',['get','height_m'],WALK.roof]];
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
        map.addLayer({id:'building-flat',type:'fill',source:'buildings',filter:['!',['>',['coalesce',['get','height_m'],0],0]],paint:{'fill-color':['case',['==',['get','role'],'context'],COLORS.flat,color],'fill-opacity':.9,'fill-outline-color':'#a59f8e'}});
        map.addLayer({id:'building-base',type:'line',source:'buildings',filter:['!=',['get','role'],'context'],paint:{'line-color':['case',['==',['get','cluster_block'],true],COLORS.cluster,COLORS.stop],'line-width':1.4}});
        // Surrounding blocks are see-through so they never hide the stop being previewed. A lighter roof cap
        // (the top 0.7 m) gives every block a crisp roofline.
        const raised=['>',['coalesce',['get','height_m'],0],0];
        map.addLayer({id:'context-heights',type:'fill-extrusion',source:'buildings',filter:['all',raised,['==',['get','role'],'context']],paint:{'fill-extrusion-color':COLORS.context,'fill-extrusion-height':roofAt,'fill-extrusion-base':0,'fill-extrusion-opacity':.62,'fill-extrusion-vertical-gradient':true}});
        map.addLayer({id:'context-roofs',type:'fill-extrusion',source:'buildings',filter:['all',raised,['==',['get','role'],'context']],paint:{'fill-extrusion-color':COLORS.roofContext,'fill-extrusion-height':['get','height_m'],'fill-extrusion-base':roofAt,'fill-extrusion-opacity':.62,'fill-extrusion-vertical-gradient':false}});
        map.addLayer({id:'building-heights',type:'fill-extrusion',source:'buildings',filter:['all',raised,['!=',['get','role'],'context']],paint:{'fill-extrusion-color':color,'fill-extrusion-height':roofAt,'fill-extrusion-base':0,'fill-extrusion-opacity':.95,'fill-extrusion-vertical-gradient':true}});
        map.addLayer({id:'building-roofs',type:'fill-extrusion',source:'buildings',filter:['all',raised,['!=',['get','role'],'context']],paint:{'fill-extrusion-color':roof,'fill-extrusion-height':['get','height_m'],'fill-extrusion-base':roofAt,'fill-extrusion-opacity':.95,'fill-extrusion-vertical-gradient':false}});
        // Where to look on the current stop (roof edge, ground floor, corridor levels or a ground ring).
        map.addSource('inspect',{type:'geojson',data:empty()});
        map.addLayer({id:'inspect-bands',type:'fill-extrusion',source:'inspect',paint:{'fill-extrusion-color':['get','color'],'fill-extrusion-height':['get','top'],'fill-extrusion-base':['get','base'],'fill-extrusion-opacity':.8}});
        if(state.plan.clusters?.features?.length){map.addSource('clusters',{type:'geojson',data:state.plan.clusters});map.addLayer({id:'cluster-fill',type:'fill',source:'clusters',paint:{'fill-color':COLORS.cluster,'fill-opacity':.1}},'building-shadow');map.addLayer({id:'cluster-outline',type:'line',source:'clusters',paint:{'line-color':COLORS.cluster,'line-width':1.8,'line-dasharray':[3,2]}},'context-heights');}
        if(state.opts.outline){map.addSource('outline',{type:'geojson',data:state.opts.outline});map.addLayer({id:'area-outline',type:'line',source:'outline',paint:{'line-color':COLORS.route,'line-width':2.2,'line-dasharray':[4,3],'line-opacity':.8}});}
        if(state.plan.route?.geometry&&!state.isTour){
          map.addSource('route',{type:'geojson',lineMetrics:true,data:{type:'Feature',properties:{},geometry:state.plan.route.geometry}});
          map.addLayer({id:'route-halo',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#fffef7','line-width':['interpolate',['linear'],['zoom'],15,7,19,16,22,40]}},'context-heights');
          map.addLayer({id:'walking-route',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':COLORS.route,'line-width':['interpolate',['linear'],['zoom'],15,3.5,19,9,22,24],...(state.track?{'line-gradient':['step',['line-progress'],COLORS.route,0,COLORS.route]}:{'line-dasharray':[2,2]})}},'context-heights');
          if(state.track){map.addImage('route-chevron',chevron());map.addLayer({id:'route-direction',type:'symbol',source:'route',layout:{'symbol-placement':'line','symbol-spacing':70,'icon-image':'route-chevron','icon-size':['interpolate',['linear'],['zoom'],15,.45,19,.8,22,1.6],'icon-rotation-alignment':'map','icon-pitch-alignment':'map','icon-allow-overlap':true,'icon-ignore-placement':true}},'context-heights');}
        }
        // A light column floats above every stop so the next ones stay findable among the towers.
        if(state.plan.stops.length){map.addSource('beacons',{type:'geojson',data:beacons(state)});map.addLayer({id:'stop-beacons',type:'fill-extrusion',source:'beacons',paint:{'fill-extrusion-color':['case',['boolean',['feature-state','selected'],false],COLORS.selected,'#8fd1b4'],'fill-extrusion-height':['get','top'],'fill-extrusion-base':['get','base'],'fill-extrusion-opacity':.3,'fill-extrusion-vertical-gradient':true}});}
        state.plan.stops.forEach((stop,index)=>{const button=document.createElement('button');button.type='button';button.className='route-3d-pin';button.textContent=String(stop.number||index+1);button.setAttribute('aria-label',`Show stop ${index+1}: ${stop.name}`);button.onclick=event=>{event.stopPropagation();goToStop(state,index);};state.markers.push(new gl.Marker({element:button,anchor:'center'}).setLngLat([stop.longitude,stop.latitude]).addTo(map));});
        if(state.track&&!state.isTour){const dot=document.createElement('span');dot.className='route-walker';dot.setAttribute('aria-hidden','true');dot.innerHTML='<i class="ph ph-person-simple-walk"></i>';state.walker=new gl.Marker({element:dot,anchor:'center'}).setLngLat(state.track.at(state.along)).addTo(map);}
        state.popup=new gl.Popup({closeButton:true,closeOnClick:true,maxWidth:'240px',className:'route-3d-popup'});
        ['building-heights','building-roofs','context-heights','context-roofs','building-flat'].forEach(layer=>{map.on('click',layer,event=>{if(state.playing)return;const feature=event.features?.[0];if(!feature)return;state.popup.setLngLat(event.lngLat).setHTML(describe(feature.properties)).addTo(map);});map.on('mouseenter',layer,()=>{map.getCanvas().style.cursor='pointer';});map.on('mouseleave',layer,()=>{map.getCanvas().style.cursor='';});});
        const parks=landuse.features.filter(f=>f.properties.kind==='green').length,water=landuse.features.filter(f=>f.properties.kind==='water').length;
        const scene=landuse.features.length?` ${parks} park and ${water} water areas from URA zoning.`:'';
        if(state.isTour)state.tour.querySelector('.route-3d-status').textContent=(state.tileError?'OneMap street tiles are unavailable. ':'')+`${buildings.features.length?`${buildings.features.length} official HDB block shapes.`:'No HDB blocks here.'}${scene}`;
        else{const s=summary(buildings,state.plan),walkText=state.track?` Walk: ${km(state.track.total)}${state.plan.route?.walking_seconds?`, about ${Math.round(state.plan.route.walking_seconds/60)} min on foot`:''}.`:'';
          state.tour.querySelector('.route-3d-status').textContent=(state.tileError?'OneMap street tiles are unavailable. ':'')+(s.count?`${s.count} official HDB block shapes${state.margin?` within about ${state.margin} m of the route`:''} · ${s.raised} raised from published storeys · ${s.flat} flat (storeys unverified)${s.missing.length?` · no footprint matched for stop ${s.missing.join(', ')}`:''}.${scene}${walkText} Tap a block for details.`:`Building shapes are unavailable for this area. The verified stops and saved route remain visible.${scene}${walkText}`);}
        if(!state.isTour)select(state,state.index);fit(state,0);paintProgress(state);if(state.mode==='3d')map.resize();
        state.container.classList.remove('is-loading');state.ready=true;update(state);pulse(state);
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
    if(!current)return;const state=current;pause(state);state.closed=true;cancelAnimationFrame(state.pulse);reduced.removeEventListener('change',state.motionChange);document.removeEventListener('visibilitychange',state.visibility);
    state.popup?.remove();closeCallout(state);state.map?.remove();state.toolbar.remove();state.tour.remove();state.container.remove();$('.inspection-legend')?.classList.remove('is-hidden-3d');current=null;
  }
  // Read-only state for automated checks and support; exposes no data beyond what is on screen.
  function snapshot(){const s=current;if(!s)return null;return {mode:s.mode,tour:s.isTour,phase:s.phase,playing:s.playing,along:s.along,total:s.track?.total??null,stop:s.index+1,stops:s.plan.stops.length,bearing:s.map?.getBearing()??null,pitch:s.map?.getPitch()??null,zoom:s.map?.getZoom()??null,look:s.callout?stopKey(s,s.index):null,bands:s.bandKey,landuse:s.map?.getSource("landuse")?._data?.features?.length??null,ready:!!s.ready};}
  window.RouteFlythrough={mount,focusStop,dispose,snapshot};
})();
