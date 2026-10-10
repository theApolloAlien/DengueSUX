/* Optional 3D route preview. Footprints are official HDB shapes; heights are estimates from published storeys. */
(() => {
  'use strict';
  const $=s=>document.querySelector(s), reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const empty=()=>({type:'FeatureCollection',features:[]});
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const COLORS={selected:'#e3ad3c',cluster:'#c2523c',stop:'#2f6f58',context:'#d9d4c5',flat:'#e3dfd3',route:'#1d4a3c',walked:'#c9921f'};
  // Low follow camera: 80 m up and 90 m behind the walker, looking 45 m ahead (pitch about 59°). The walker
  // sits in the lower fifth of the frame with roughly 250 m of track visible ahead. Constant pace, gentle turns,
  // no zoom changes.
  const WALK={speed:40,dwell:2.3,eye:80,behind:90,ahead:45,look:0,clearance:14,tau:.8,maxTurn:24,slowZone:60,legMin:150,nearBlocks:140,maxScale:1.6,introMs:1700,outroMs:1800};
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
  function routeTrack(plan){
    const raw=plan.route?.geometry;
    if(plan.route?.method!=='onemap_walk'||raw?.type!=='LineString'||!raw.coordinates?.every(valid)||raw.coordinates.length<2)return null;
    const points=raw.coordinates,cumulative=[0];
    for(let i=1;i<points.length;i++)cumulative.push(cumulative[i-1]+distance(points[i-1],points[i]));
    if(!cumulative.at(-1))return null;
    // Snap each stop to the original path in visit order; never draw invented connectors.
    let previous=0;
    const stopDistances=plan.stops.map(stop=>{
      const point=[stop.longitude,stop.latitude];let best={gap:Infinity,along:previous};
      for(let i=1;i<points.length;i++){
        if(cumulative[i]<previous)continue;
        const a=points[i-1],b=points[i],cos=Math.cos(point[1]*Math.PI/180),x=(b[0]-a[0])*cos,y=b[1]-a[1];
        const length=cumulative[i]-cumulative[i-1];if(!length)continue;
        const minimum=Math.max(0,(previous-cumulative[i-1])/length);
        const t=Math.max(minimum,Math.min(1,((point[0]-a[0])*cos*x+(point[1]-a[1])*y)/(x*x+y*y)));
        const projected=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t],gap=distance(point,projected);
        if(gap<best.gap)best={gap,along:cumulative[i-1]+length*t};
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
    // not at every bend of the footpath. The walker still follows the real path.
    // Stops closer than WALK.legMin are looked past, so a cluster of nearby stops does not set the camera turning.
    const legHeading=from=>{
      const next=stopDistances.findIndex(d=>d>=from+WALK.legMin),to=next>=0?stopDistances[next]:total;
      return distance(at(from),at(to))>25?bearingOf(at(from),at(to)):heading(from);
    };
    return {points,cumulative,stopDistances,total,at,heading,legHeading};
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
  function mount(plan,area,onSelect){
    dispose();
    if(!plan.stops?.length)return;
    const wrap=$('.inspection-map-wrap'),column=$('.inspection-map-column');if(!wrap||!column)return;
    const toolbar=document.createElement('div');toolbar.className='route-preview-toolbar';
    toolbar.innerHTML='<div class="route-view-tabs" role="group" aria-label="Inspection map view"><button type="button" data-map-mode="2d" aria-pressed="true"><i class="ph ph-map-trifold" aria-hidden="true"></i> 2D map</button><button type="button" data-map-mode="3d" aria-pressed="false"><i class="ph ph-cube" aria-hidden="true"></i> 3D walk preview</button></div><span class="route-preview-label">Official HDB block shapes</span>';
    column.insertBefore(toolbar,wrap);
    const container=document.createElement('div');container.id='route-3d';container.hidden=true;container.setAttribute('role','region');container.setAttribute('aria-label','3D inspection route with estimated HDB block heights');wrap.prepend(container);
    const tour=document.createElement('section');tour.className='route-tour';tour.hidden=true;tour.setAttribute('aria-label','Route preview controls');
    tour.innerHTML=`<div class="route-tour-controls"><button type="button" data-tour="previous" aria-label="Previous inspection stop"><i class="ph ph-caret-left" aria-hidden="true"></i></button><button type="button" data-tour="play" class="route-tour-play"><i class="ph ph-play" aria-hidden="true"></i><span>Walk the route</span></button><button type="button" data-tour="next" aria-label="Next inspection stop"><i class="ph ph-caret-right" aria-hidden="true"></i></button><button type="button" data-tour="speed" class="route-tour-speed" aria-label="Walking preview speed: normal">1×</button><button type="button" data-tour="fit" aria-label="Show the whole route from above"><i class="ph ph-arrows-out-simple" aria-hidden="true"></i><span>Whole route</span></button></div>
      <div class="route-scrub"><label for="route-scrub-input" class="route-scrub-label">Along the route</label><input id="route-scrub-input" type="range" min="0" max="1000" step="1" value="0"><span class="route-scrub-text" aria-hidden="true"></span></div>
      <div class="route-tour-stop"><span role="status" aria-live="polite"></span><button type="button" data-tour="checklist">Checklist <i class="ph ph-arrow-down" aria-hidden="true"></i></button></div><ul class="route-3d-legend" aria-label="3D colours"><li><b style="background:${COLORS.selected}"></b>Current stop</li><li><b style="background:${COLORS.stop}"></b>Other stops</li><li><b style="background:${COLORS.cluster}"></b>Cluster blocks</li><li><b style="background:${COLORS.context}"></b>Other HDB blocks</li><li><b class="is-flat" style="background:${COLORS.flat}"></b>Storeys unverified (flat)</li><li><b class="is-line" style="background:${COLORS.walked}"></b>Walked so far</li></ul><p class="route-3d-note"></p><p class="route-3d-status" role="status"></p>`;
    wrap.after(tour);
    const state={plan,area,onSelect,wrap,toolbar,container,tour,map:null,mode:'2d',index:0,playing:false,phase:'idle',frame:0,timer:0,track:routeTrack(plan),along:0,heading:0,eye:WALK.eye,scale:1,speedFactor:1,multiplier:1,dwellUntil:0,nextStop:0,lastFrame:0,lastPaint:0,markers:[],walker:null,callout:null,loading:false,closed:false,selectedFeature:null,popup:null,solids:[]};
    current=state;
    if(state.track){state.along=0;state.heading=state.track.heading(0);}
    toolbar.querySelectorAll('[data-map-mode]').forEach(button=>button.addEventListener('click',()=>setMode(state,button.dataset.mapMode)));
    tour.querySelector('[data-tour=previous]').onclick=()=>goToStop(state,state.index-1);
    tour.querySelector('[data-tour=next]').onclick=()=>goToStop(state,state.index+1);
    tour.querySelector('[data-tour=play]').onclick=()=>togglePlay(state);
    tour.querySelector('[data-tour=speed]').onclick=()=>{state.multiplier=state.multiplier===1?2:1;const b=tour.querySelector('[data-tour=speed]');b.textContent=`${state.multiplier}×`;b.setAttribute('aria-label',`Walking preview speed: ${state.multiplier===1?'normal':'double'}`);};
    tour.querySelector('[data-tour=fit]').onclick=()=>{pause(state);fit(state);};
    tour.querySelector('[data-tour=checklist]').onclick=()=>{const card=document.getElementById('stop-'+state.plan.stops[state.index].id);card?.scrollIntoView({block:'center',behavior:reduced.matches?'instant':'smooth'});card?.querySelector('.stop-number')?.focus({preventScroll:true});};
    const scrub=tour.querySelector('#route-scrub-input');
    scrub.addEventListener('input',()=>{if(!state.track||!state.map)return;const fraction=Number(scrub.value)/1000;pause(state);state.along=state.track.total*fraction;state.heading=state.target=state.track.legHeading(state.along);placeStreet(state,true);syncStop(state);});
    state.motionChange=()=>{if(reduced.matches)pause(state);update(state);};reduced.addEventListener('change',state.motionChange);
    state.visibility=()=>{if(document.hidden)pause(state);};document.addEventListener('visibilitychange',state.visibility);
    state.keys=event=>{if(state.mode!=='3d'||event.target.closest('input,textarea,select'))return;if(event.key==='ArrowRight'&&!event.altKey){event.preventDefault();goToStop(state,state.index+1);}else if(event.key==='ArrowLeft'&&!event.altKey){event.preventDefault();goToStop(state,state.index-1);}};
    tour.addEventListener('keydown',state.keys);container.addEventListener('keydown',state.keys);
    update(state);
  }
  function update(state){
    if(state.closed)return;
    const stops=state.plan.stops,stop=stops[state.index],play=state.tour.querySelector('[data-tour=play]'),track=state.track;
    play.disabled=reduced.matches||!track;
    play.querySelector('span').textContent=reduced.matches?'Step through stops':!track?'Walk unavailable':state.playing?'Pause':state.along>=track.total-1?'Walk again':state.along>1?'Resume walk':'Walk the route';
    play.querySelector('i').className='ph ph-'+(state.playing?'pause':reduced.matches?'hand-pointing':'person-simple-walk');play.setAttribute('aria-label',state.playing?'Pause the walking preview':'Play the walking preview along the whole route');
    state.tour.querySelector('[data-tour=speed]').hidden=reduced.matches||!track;
    state.tour.querySelector('[data-tour=previous]').disabled=state.index===0&&(!track||state.along<=track.stopDistances[0]+1);
    state.tour.querySelector('[data-tour=next]').disabled=state.index===stops.length-1;
    state.tour.querySelector('.route-scrub').hidden=!track;
    const floors=stop.max_floor_lvl?` · ${stop.max_floor_lvl} storeys`:'';
    state.tour.querySelector('.route-tour-stop span').innerHTML=`<b>Stop ${state.index+1} of ${stops.length}</b> · ${esc(stop.name)}${esc(floors)}`;
    const motion=reduced.matches?' Reduced motion is on: drag the slider or use Previous and Next (arrow keys) for still views.':!track?' Walking directions are unavailable, so the preview steps between stops.':'';
    state.tour.querySelector('.route-3d-note').textContent=`Shapes are official HDB footprints. Heights are estimates: published storeys × 2.8 m + 1.3 m roof, not surveyed. Condos, schools and other non-HDB buildings are not modelled. Places to check, not confirmed breeding sites.${motion}`;
    state.markers.forEach((marker,i)=>{const el=marker.getElement();el.classList.toggle('is-selected',i===state.index);if(i===state.index)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});
    progressText(state);highlight(state);
  }
  function progressText(state){
    const t=state.track;if(!t)return;
    const next=t.stopDistances.findIndex(d=>d>state.along+2);
    state.tour.querySelector('.route-scrub-text').textContent=`${km(state.along)} of ${km(t.total)}${next>=0?` · next: stop ${next+1}`:' · end of route'}`;
    const scrub=state.tour.querySelector('#route-scrub-input');scrub.value=String(Math.round(state.along/t.total*1000));
    scrub.setAttribute('aria-valuetext',`${km(state.along)} of ${km(t.total)}, ${next>=0?`next stop ${next+1}`:'end of route'}`);
  }
  function highlight(state){
    const map=state.map;if(!map||!map.getSource('buildings'))return;
    if(state.selectedFeature!==null)map.setFeatureState({source:'buildings',id:state.selectedFeature},{selected:false});
    const id=state.plan.stops[state.index].id,feature=state.buildings?.features.find(f=>f.properties.stop_id===id);
    state.selectedFeature=feature?feature.properties.id:null;
    if(state.selectedFeature!==null)map.setFeatureState({source:'buildings',id:state.selectedFeature},{selected:true});
  }
  function paintProgress(state){
    const map=state.map,t=state.track;if(!map||!t||!map.getLayer('walking-route'))return;
    const f=Math.max(0,Math.min(1,state.along/t.total));
    map.setPaintProperty('walking-route','line-gradient',f<=0?['step',['line-progress'],COLORS.route,0,COLORS.route]:['step',['line-progress'],COLORS.walked,f,COLORS.route]);
    if(state.walker)state.walker.setLngLat(t.at(state.along));
    state.markers.forEach((marker,i)=>marker.getElement().classList.toggle('is-far',state.phase==='walking'&&Math.abs(t.stopDistances[i]-state.along)>320));
  }
  function streetView(state,along,heading,eye){
    const t=state.track,p=t.at(along);
    return state.map.calculateCameraOptionsFromTo(offset(p,heading+180,WALK.behind*state.scale),eye,offset(p,heading,WALK.ahead*state.scale),WALK.look);
  }
  // Among tall towers the whole camera rig grows (same framing, higher and further back) so blocks stay readable.
  function rigScale(state,along){
    const p=state.track.at(along);let tallest=0;
    for(const f of state.solids)if(f.h>tallest&&distance(f.center,p)<WALK.nearBlocks)tallest=f.h;
    return Math.min(WALK.maxScale,Math.max(1,(tallest*1.15+15)/WALK.eye));
  }
  // Keep the camera above any block between it and the walker instead of flying through it.
  function requiredEye(state,along,heading){
    const k=state.scale,p=state.track.at(along),back=offset(p,heading+180,WALK.behind*k),mid=offset(p,heading+180,WALK.behind*k/2);
    return Math.max(WALK.eye*k,heightAt(state,back)+WALK.clearance,heightAt(state,mid)+WALK.clearance*.6);
  }
  function placeStreet(state,instant){
    if(!state.map||!state.track)return;
    if(instant){state.scale=rigScale(state,state.along);state.eye=requiredEye(state,state.along,state.heading);}
    state.map.jumpTo(streetView(state,state.along,state.heading,state.eye));paintProgress(state);progressText(state);
  }
  function syncStop(state){
    const t=state.track;let index=0;t.stopDistances.forEach((d,i)=>{if(d<=state.along+3)index=i;});
    if(index!==state.index)select(state,index);else update(state);
  }
  function stopMotion(state){cancelAnimationFrame(state.frame);clearTimeout(state.timer);state.frame=0;state.timer=0;state.map?.stop();}
  // While walking, every block is a little see-through so the path ahead is never fully hidden.
  function walkingLook(state,on){
    const map=state.map;if(!map?.getLayer('building-heights'))return;
    map.setPaintProperty('building-heights','fill-extrusion-opacity',on?.8:.95);map.setPaintProperty('context-heights','fill-extrusion-opacity',on?.45:.58);
  }
  function pause(state){if(state.closed)return;stopMotion(state);state.playing=false;state.phase='idle';state.callout?.remove();state.container.classList.remove('is-walking');walkingLook(state,false);paintProgress(state);update(state);}
  function select(state,index){state.index=index;state.onSelect?.(state.plan.stops[index].id);update(state);}
  function fit(state,duration=reduced.matches?0:900){
    if(!state.map)return;
    const bounds=new maplibregl.LngLatBounds();state.plan.stops.forEach(stop=>bounds.extend([stop.longitude,stop.latitude]));
    (state.track?.points||[]).forEach(point=>bounds.extend(point));
    state.map.fitBounds(bounds,{padding:{top:60,bottom:36,left:36,right:36},maxZoom:17.4,pitch:48,bearing:-18,duration});
  }
  function showCallout(state,index){
    const stop=state.plan.stops[index];state.callout?.remove();
    const checks=(stop.checklist||[]).slice(0,3).map(item=>`<li>${esc(item)}</li>`).join('');
    state.callout=new maplibregl.Popup({closeButton:false,closeOnClick:false,anchor:'bottom',offset:24,maxWidth:'250px',className:'route-stop-callout'})
      .setLngLat([stop.longitude,stop.latitude]).setHTML(`<strong>Stop ${index+1} · ${esc(stop.name)}</strong>${checks?`<ul>${checks}</ul>`:''}<small>A place to check, not a confirmed breeding site.</small>`).addTo(state.map);
  }
  // Still view of one stop from the street, in the same camera family as the walk (no zoom pumping).
  function goToStop(state,index){
    if(state.closed||!state.map||index<0||index>=state.plan.stops.length)return;
    pause(state);select(state,index);
    const stop=state.plan.stops[index],t=state.track;
    if(t){state.along=t.stopDistances[index];state.heading=state.target=t.legHeading(state.along);}
    const heading=t?state.heading:state.map.getBearing(),target=[stop.longitude,stop.latitude];
    const view=state.map.calculateCameraOptionsFromTo(offset(target,heading+180,150),120,target,10);
    if(reduced.matches)state.map.jumpTo(view);else state.map.easeTo({...view,duration:1100,easing:x=>x*(2-x)});
    paintProgress(state);progressText(state);
  }
  function togglePlay(state){
    if(state.playing){pause(state);return;}
    const t=state.track;if(reduced.matches||!t||!state.map)return;
    if(state.along>=t.total-1){state.along=0;select(state,0);}
    state.playing=true;state.phase='intro';state.container.classList.add('is-walking');
    state.heading=state.target=t.legHeading(state.along);state.scale=rigScale(state,state.along);state.eye=requiredEye(state,state.along,state.heading);walkingLook(state,true);
    state.nextStop=t.stopDistances.findIndex(d=>d>=state.along-0.5);
    // Descend from wherever the user is looking to street level, then walk.
    state.map.easeTo({...streetView(state,state.along,state.heading,state.eye),duration:WALK.introMs,easing:x=>1-Math.pow(1-x,3)});
    state.timer=setTimeout(()=>{if(!state.playing)return;state.phase='walking';state.lastFrame=performance.now();state.frame=requestAnimationFrame(now=>step(state,now));},WALK.introMs+60);
    update(state);
  }
  function step(state,now){
    if(state.closed||!state.playing||state.mode!=='3d')return;
    const t=state.track,dt=Math.min(.12,(now-state.lastFrame)/1000);state.lastFrame=now;
    if(state.phase==='dwell'){
      if(now>=state.dwellUntil){state.callout?.remove();state.phase='walking';}
    }else{
      const next=state.nextStop>=0&&state.nextStop<t.stopDistances.length?t.stopDistances[state.nextStop]:t.total;
      const prev=state.nextStop>0?t.stopDistances[state.nextStop-1]:0;
      // Ease into and out of each stop instead of braking hard.
      const target=Math.max(.22,Math.min(1,(next-state.along)/WALK.slowZone,(state.along-prev+12)/WALK.slowZone));
      state.speedFactor+=(target-state.speedFactor)*(1-Math.exp(-dt/.35));
      state.along=Math.min(next,state.along+WALK.speed*state.multiplier*state.speedFactor*dt);
      if(state.along>=next-.01){
        if(state.nextStop>=0&&state.nextStop<t.stopDistances.length){
          select(state,state.nextStop);showCallout(state,state.nextStop);state.target=t.legHeading(state.along);state.nextStop++;state.phase='dwell';state.dwellUntil=now+WALK.dwell*1000/Math.sqrt(state.multiplier);
        }else if(state.along>=t.total-.01){finishWalk(state);return;}
      }
    }
    // Ease towards the leg heading with a turn-rate limit: smooth, never a spin.
    const wanted=turn(state.heading,state.target??t.legHeading(state.along)),limit=WALK.maxTurn*dt;
    state.heading+=Math.max(-limit,Math.min(limit,wanted*(1-Math.exp(-dt/WALK.tau))));
    state.scale+=(rigScale(state,state.along)-state.scale)*(1-Math.exp(-dt/1.8));
    state.eye+=(requiredEye(state,state.along,state.heading)-state.eye)*(1-Math.exp(-dt/.6));
    state.map.jumpTo(streetView(state,state.along,state.heading,state.eye));
    if(now-state.lastPaint>110){state.lastPaint=now;paintProgress(state);progressText(state);}
    state.frame=requestAnimationFrame(next=>step(state,next));
  }
  function finishWalk(state){
    state.playing=false;state.phase='idle';state.callout?.remove();state.container.classList.remove('is-walking');walkingLook(state,false);
    state.along=state.track.total;paintProgress(state);update(state);
    fit(state,WALK.outroMs);
    state.tour.querySelector('.route-tour-stop span').innerHTML=`<b>Route complete</b> · ${esc(km(state.track.total))}, ${state.plan.stops.length} stops`;
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
  async function setMode(state,mode){
    if(state.closed)return;
    state.mode=mode;pause(state);
    state.toolbar.querySelectorAll('[data-map-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.mapMode===mode)));
    state.container.hidden=mode!=='3d';$('#inspection-map').hidden=mode==='3d';$('#fit-inspection').hidden=mode==='3d';
    state.wrap.classList.toggle('is-3d',mode==='3d');state.tour.hidden=mode!=='3d';
    $('.inspection-legend')?.classList.toggle('is-hidden-3d',mode==='3d');
    if(mode==='2d')return;
    if(state.map){state.map.resize();return;}
    if(state.loading)return;state.loading=true;
    state.tour.querySelector('.route-3d-status').textContent='Loading the route and official building shapes…';
    try{
      const [gl,artifact]=await Promise.all([loadLibrary(),loadFootprints()]);if(state.closed)return;
      if(gl.supported&&!gl.supported())throw new Error('WebGL unavailable');
      const buildings=artifact?.areas?.[state.area.code]||empty();state.buildings=buildings;state.margin=Number(artifact?.method?.context_margin_m)||null;
      state.solids=buildings.features.filter(f=>Number(f.properties.height_m)>0).map(f=>{const rings=f.geometry.type==='Polygon'?[f.geometry.coordinates[0]]:f.geometry.coordinates.map(p=>p[0]);const xs=rings.flat().map(c=>c[0]),ys=rings.flat().map(c=>c[1]);return {h:Number(f.properties.height_m),rings,box:[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)],center:[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2]};});
      state.map=new gl.Map({container:state.container,style:{version:8,sources:{onemap:{type:'raster',tiles:['https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png'],tileSize:256,maxzoom:19,attribution:'<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener">OneMap</a> © Singapore Land Authority · HDB footprints & storeys / NEA via data.gov.sg'}},layers:[{id:'background',type:'background',paint:{'background-color':'#eef0e8'}},{id:'onemap',type:'raster',source:'onemap',paint:{'raster-saturation':-.55,'raster-contrast':-.08,'raster-brightness-min':.08,'raster-opacity':.92}}]},center:[state.plan.stops[0].longitude,state.plan.stops[0].latitude],zoom:16.6,pitch:48,bearing:-18,maxZoom:22,minZoom:13,maxPitch:82,antialias:true,attributionControl:{compact:true}});
      state.map.addControl(new gl.NavigationControl({visualizePitch:true}),'bottom-right');state.map.scrollZoom.disable();state.map.keyboard.disable();
      state.map.on('error',event=>{if(event.sourceId!=='onemap'||state.tileError)return;state.tileError=true;const status=state.tour.querySelector('.route-3d-status');status.textContent=`${status.textContent} OneMap street tiles are unavailable; building shapes, stops and the saved route remain visible.`.trim();});
      state.map.getCanvas().addEventListener('webglcontextlost',()=>fallback(state,'3D graphics became unavailable. Continue with the 2D map and numbered checklist.'),{once:true});
      ['dragstart','rotatestart','pitchstart'].forEach(name=>state.map.on(name,event=>{if(event.originalEvent)pause(state);}));state.map.on('zoomstart',event=>{if(event.originalEvent)pause(state);});
      state.map.once('load',()=>{
        if(state.closed||!state.map)return;
        const map=state.map,color=['case',['boolean',['feature-state','selected'],false],COLORS.selected,['==',['get','cluster_block'],true],COLORS.cluster,['==',['get','role'],'stop'],COLORS.stop,COLORS.context];
        map.setLight({anchor:'viewport',color:'#fffaf0',intensity:.3,position:[1.2,210,30]});
        // A soft sky and distance haze keep the street-level horizon calm and hide far, blurry tiles.
        try{map.setSky({'sky-color':'#d6e6ec','horizon-color':'#eef2ea','fog-color':'#eef0e8','sky-horizon-blend':.55,'horizon-fog-blend':.7,'fog-ground-blend':.35,'atmosphere-blend':0});}catch{}
        map.addSource('buildings',{type:'geojson',data:buildings,promoteId:'id'});
        map.addLayer({id:'building-flat',type:'fill',source:'buildings',filter:['!',['>',['coalesce',['get','height_m'],0],0]],paint:{'fill-color':['case',['==',['get','role'],'context'],COLORS.flat,color],'fill-opacity':.9,'fill-outline-color':'#a59f8e'}});
        map.addLayer({id:'building-base',type:'line',source:'buildings',filter:['!=',['get','role'],'context'],paint:{'line-color':['case',['==',['get','cluster_block'],true],COLORS.cluster,COLORS.stop],'line-width':1.4}});
        // Surrounding blocks are see-through so they never hide the stop being previewed.
        map.addLayer({id:'context-heights',type:'fill-extrusion',source:'buildings',filter:['all',['>',['coalesce',['get','height_m'],0],0],['==',['get','role'],'context']],paint:{'fill-extrusion-color':COLORS.context,'fill-extrusion-height':['get','height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':.58,'fill-extrusion-vertical-gradient':true}});
        map.addLayer({id:'building-heights',type:'fill-extrusion',source:'buildings',filter:['all',['>',['coalesce',['get','height_m'],0],0],['!=',['get','role'],'context']],paint:{'fill-extrusion-color':color,'fill-extrusion-height':['get','height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':.95,'fill-extrusion-vertical-gradient':true}});
        if(state.plan.clusters?.features?.length){map.addSource('clusters',{type:'geojson',data:state.plan.clusters});map.addLayer({id:'cluster-outline',type:'line',source:'clusters',paint:{'line-color':COLORS.cluster,'line-width':1.6,'line-dasharray':[3,2]}},'context-heights');}
        if(state.plan.route?.geometry){
          map.addSource('route',{type:'geojson',lineMetrics:true,data:{type:'Feature',properties:{},geometry:state.plan.route.geometry}});
          map.addLayer({id:'route-halo',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#fffef7','line-width':['interpolate',['linear'],['zoom'],15,7,19,16,22,40]}},'context-heights');
          map.addLayer({id:'walking-route',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':COLORS.route,'line-width':['interpolate',['linear'],['zoom'],15,3.5,19,9,22,24],...(state.track?{'line-gradient':['step',['line-progress'],COLORS.route,0,COLORS.route]}:{'line-dasharray':[2,2]})}},'context-heights');
          if(state.track){map.addImage('route-chevron',chevron());map.addLayer({id:'route-direction',type:'symbol',source:'route',layout:{'symbol-placement':'line','symbol-spacing':70,'icon-image':'route-chevron','icon-size':['interpolate',['linear'],['zoom'],15,.45,19,.8,22,1.6],'icon-rotation-alignment':'map','icon-pitch-alignment':'map','icon-allow-overlap':true,'icon-ignore-placement':true}},'context-heights');}
        }
        state.plan.stops.forEach((stop,index)=>{const button=document.createElement('button');button.type='button';button.className='route-3d-pin';button.textContent=String(stop.number||index+1);button.setAttribute('aria-label',`Show stop ${index+1}: ${stop.name}`);button.onclick=event=>{event.stopPropagation();goToStop(state,index);};state.markers.push(new gl.Marker({element:button,anchor:'center'}).setLngLat([stop.longitude,stop.latitude]).addTo(map));});
        if(state.track){const dot=document.createElement('span');dot.className='route-walker';dot.setAttribute('aria-hidden','true');state.walker=new gl.Marker({element:dot,anchor:'center'}).setLngLat(state.track.at(state.along)).addTo(map);}
        state.popup=new gl.Popup({closeButton:true,closeOnClick:true,maxWidth:'240px',className:'route-3d-popup'});
        ['building-heights','context-heights','building-flat'].forEach(layer=>{map.on('click',layer,event=>{if(state.playing)return;const feature=event.features?.[0];if(!feature)return;state.popup.setLngLat(event.lngLat).setHTML(describe(feature.properties)).addTo(map);});map.on('mouseenter',layer,()=>{map.getCanvas().style.cursor='pointer';});map.on('mouseleave',layer,()=>{map.getCanvas().style.cursor='';});});
        const s=summary(buildings,state.plan),walk=state.track?` Walk: ${km(state.track.total)}${state.plan.route?.walking_seconds?`, about ${Math.round(state.plan.route.walking_seconds/60)} min on foot`:''}.`:'';
        state.tour.querySelector('.route-3d-status').textContent=(state.tileError?'OneMap street tiles are unavailable. ':'')+(s.count?`${s.count} official HDB block shapes${state.margin?` within about ${state.margin} m of the route`:''} · ${s.raised} raised from published storeys · ${s.flat} flat (storeys unverified)${s.missing.length?` · no footprint matched for stop ${s.missing.join(', ')}`:''}.${walk} Tap a block for details.`:`Building shapes are unavailable for this area. The verified stops and saved route remain visible.${walk}`);
        select(state,state.index);fit(state,0);paintProgress(state);if(state.mode==='3d')map.resize();
      });
    }catch{fallback(state,'3D is unavailable on this device. Continue with the 2D map and numbered checklist.');}
    finally{state.loading=false;}
  }
  function focusStop(id){
    if(!current||current.mode!=='3d'||!current.map)return false;
    const index=current.plan.stops.findIndex(stop=>String(stop.id)===String(id));if(index<0)return false;
    goToStop(current,index);return true;
  }
  function dispose(){
    if(!current)return;const state=current;pause(state);state.closed=true;reduced.removeEventListener('change',state.motionChange);document.removeEventListener('visibilitychange',state.visibility);
    state.popup?.remove();state.callout?.remove();state.map?.remove();state.toolbar.remove();state.tour.remove();state.container.remove();$('.inspection-legend')?.classList.remove('is-hidden-3d');current=null;
  }
  // Read-only state for automated checks and support; exposes no data beyond what is on screen.
  function snapshot(){const s=current;if(!s)return null;return {mode:s.mode,phase:s.phase,playing:s.playing,along:s.along,total:s.track?.total??null,stop:s.index+1,bearing:s.map?.getBearing()??null,pitch:s.map?.getPitch()??null,zoom:s.map?.getZoom()??null};}
  window.RouteFlythrough={mount,focusStop,dispose,snapshot};
})();
