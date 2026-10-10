/* Optional 3D route preview. Footprints are official HDB shapes; heights are estimates from published storeys. */
(() => {
  'use strict';
  const $=s=>document.querySelector(s), reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const empty=()=>({type:'FeatureCollection',features:[]});
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const COLORS={selected:'#e3ad3c',cluster:'#c2523c',stop:'#2f6f58',context:'#d9d4c5',flat:'#e3dfd3'};
  const VIEW={zoom:17.1,pitch:52,stopZoom:17.45};
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
  const valid=p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(p[0])&&Number.isFinite(p[1]);
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
    const at=along=>{
      along=Math.max(0,Math.min(cumulative.at(-1),along));
      let i=1;while(i<points.length-1&&cumulative[i]<along)i++;
      const a=points[i-1],b=points[i],length=cumulative[i]-cumulative[i-1],t=length?(along-cumulative[i-1])/length:0;
      return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];
    };
    return {points,cumulative,stopDistances,at};
  }
  function summary(buildings,plan){
    const features=buildings.features,raised=features.filter(f=>Number(f.properties.height_m)>0).length;
    const matched=new Set(features.map(f=>f.properties.stop_id).filter(Boolean));
    const missing=plan.stops.filter(stop=>!matched.has(stop.id)).map(stop=>stop.number);
    return {count:features.length,raised,flat:features.length-raised,missing};
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
    tour.innerHTML=`<div class="route-tour-controls"><button type="button" data-tour="previous" aria-label="Previous inspection stop"><i class="ph ph-caret-left" aria-hidden="true"></i></button><button type="button" data-tour="play" class="route-tour-play"><i class="ph ph-play" aria-hidden="true"></i><span>Play route</span></button><button type="button" data-tour="next" aria-label="Next inspection stop"><i class="ph ph-caret-right" aria-hidden="true"></i></button><button type="button" data-tour="fit" aria-label="Show the whole route"><i class="ph ph-arrows-out-simple" aria-hidden="true"></i><span>Whole route</span></button></div><div class="route-tour-stop"><span role="status" aria-live="polite"></span><button type="button" data-tour="checklist">Checklist <i class="ph ph-arrow-down" aria-hidden="true"></i></button></div><ul class="route-3d-legend" aria-label="3D colours"><li><b style="background:${COLORS.selected}"></b>Current stop</li><li><b style="background:${COLORS.stop}"></b>Other stops</li><li><b style="background:${COLORS.cluster}"></b>Cluster blocks</li><li><b style="background:${COLORS.context}"></b>Other HDB blocks</li><li><b class="is-flat" style="background:${COLORS.flat}"></b>Storeys unverified (flat)</li></ul><p class="route-3d-note"></p><p class="route-3d-status" role="status"></p>`;
    wrap.after(tour);
    const state={plan,area,onSelect,wrap,toolbar,container,tour,map:null,mode:'2d',index:0,playing:false,frame:0,timer:0,track:routeTrack(plan),along:0,markers:[],loading:false,closed:false,selectedFeature:null,popup:null};
    current=state;if(state.track)state.along=state.track.stopDistances[0];
    toolbar.querySelectorAll('[data-map-mode]').forEach(button=>button.addEventListener('click',()=>setMode(state,button.dataset.mapMode)));
    tour.querySelector('[data-tour=previous]').onclick=()=>go(state,state.index-1);
    tour.querySelector('[data-tour=next]').onclick=()=>go(state,state.index+1);
    tour.querySelector('[data-tour=play]').onclick=()=>togglePlay(state);
    tour.querySelector('[data-tour=fit]').onclick=()=>{pause(state);fit(state);};
    tour.querySelector('[data-tour=checklist]').onclick=()=>{const card=document.getElementById('stop-'+state.plan.stops[state.index].id);card?.scrollIntoView({block:'center',behavior:reduced.matches?'instant':'smooth'});card?.querySelector('.stop-number')?.focus({preventScroll:true});};
    state.motionChange=()=>{if(reduced.matches)pause(state);update(state);};reduced.addEventListener('change',state.motionChange);
    state.visibility=()=>{if(document.hidden)pause(state);};document.addEventListener('visibilitychange',state.visibility);
    state.keys=event=>{if(state.mode!=='3d'||event.target.closest('input,textarea,select'))return;if(event.key==='ArrowRight'&&!event.altKey){event.preventDefault();go(state,state.index+1);}else if(event.key==='ArrowLeft'&&!event.altKey){event.preventDefault();go(state,state.index-1);}};
    tour.addEventListener('keydown',state.keys);container.addEventListener('keydown',state.keys);
    update(state);
  }
  function update(state){
    if(state.closed)return;
    const stops=state.plan.stops,stop=stops[state.index],play=state.tour.querySelector('[data-tour=play]');
    play.disabled=reduced.matches||!state.track||stops.length<2;
    play.querySelector('span').textContent=reduced.matches?'Step through stops':state.playing?'Pause':'Play route';
    play.querySelector('i').className='ph ph-'+(state.playing?'pause':reduced.matches?'hand-pointing':'play');play.setAttribute('aria-label',state.playing?'Pause route preview':'Play route preview');
    state.tour.querySelector('[data-tour=previous]').disabled=state.index===0;
    state.tour.querySelector('[data-tour=next]').disabled=state.index===stops.length-1;
    const floors=stop.max_floor_lvl?` · ${stop.max_floor_lvl} storeys`:'';
    state.tour.querySelector('.route-tour-stop span').innerHTML=`<b>Stop ${state.index+1} of ${stops.length}</b> · ${esc(stop.name)}${esc(floors)}`;
    const motion=reduced.matches?' Reduced motion is on: use Previous and Next (or the arrow keys) for instant views.':!state.track?' Walking directions are unavailable, so the camera jumps between stops.':'';
    state.tour.querySelector('.route-3d-note').textContent=`Shapes are official HDB footprints. Heights are estimates: published storeys × 2.8 m + 1.3 m roof, not surveyed. Condos, schools and other non-HDB buildings are not modelled. Places to check, not confirmed breeding sites.${motion}`;
    state.markers.forEach((marker,i)=>{const el=marker.getElement();el.classList.toggle('is-selected',i===state.index);if(i===state.index)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});
    highlight(state);
  }
  function highlight(state){
    const map=state.map;if(!map||!map.getSource('buildings'))return;
    if(state.selectedFeature!==null)map.setFeatureState({source:'buildings',id:state.selectedFeature},{selected:false});
    const id=state.plan.stops[state.index].id,feature=state.buildings?.features.find(f=>f.properties.stop_id===id);
    state.selectedFeature=feature?feature.properties.id:null;
    if(state.selectedFeature!==null)map.setFeatureState({source:'buildings',id:state.selectedFeature},{selected:true});
  }
  function stopMotion(state){cancelAnimationFrame(state.frame);clearTimeout(state.timer);state.frame=0;state.timer=0;state.map?.stop();}
  function pause(state){stopMotion(state);state.playing=false;update(state);}
  function select(state,index){state.index=index;state.onSelect?.(state.plan.stops[index].id);update(state);}
  function fit(state){
    if(!state.map)return;
    const bounds=new maplibregl.LngLatBounds();state.plan.stops.forEach(stop=>bounds.extend([stop.longitude,stop.latitude]));
    (state.track?.points||[]).forEach(point=>bounds.extend(point));
    state.map.fitBounds(bounds,{padding:{top:70,bottom:40,left:40,right:40},maxZoom:17.4,pitch:50,bearing:-18,duration:reduced.matches?0:700});
  }
  function frameStop(state,stop,animate){
    const view={center:[stop.longitude,stop.latitude],zoom:VIEW.stopZoom,pitch:VIEW.pitch,bearing:state.map.getBearing()};
    if(animate&&!reduced.matches)state.map.easeTo({...view,duration:900});else state.map.jumpTo(view);
  }
  function go(state,index,continuous=false){
    if(state.closed||!state.map||index<0||index>=state.plan.stops.length)return;
    stopMotion(state);state.playing=continuous;select(state,index);
    const stop=state.plan.stops[index],target=state.track?.stopDistances[index];
    if(reduced.matches||!state.track){frameStop(state,stop,false);return;}
    const start=state.along,length=target-start,began=performance.now(),duration=Math.min(7000,Math.max(1400,Math.abs(length)*20));
    if(Math.abs(length)<1){frameStop(state,stop,true);finish(state,index);return;}
    const frame=now=>{
      if(state.closed||state.mode!=='3d')return;
      const raw=Math.min(1,(now-began)/duration),t=raw<.5?2*raw*raw:1-Math.pow(-2*raw+2,2)/2;state.along=start+length*t;
      const center=state.track.at(state.along),ahead=state.track.at(state.along+(length<0?-25:25));
      const bearing=distance(center,ahead)>.5?Math.atan2((ahead[0]-center[0])*Math.cos(center[1]*Math.PI/180),ahead[1]-center[1])*180/Math.PI:state.map.getBearing();
      // Each camera center lies on the saved OneMap walking geometry; the heading eases toward the path ahead.
      const currentBearing=state.map.getBearing(),turn=((bearing-currentBearing+540)%360)-180;
      state.map.jumpTo({center,zoom:VIEW.zoom,pitch:VIEW.pitch+2,bearing:currentBearing+turn*.05});
      if(raw<1)state.frame=requestAnimationFrame(frame);
      else{state.frame=0;frameStop(state,stop,true);finish(state,index);}
    };
    state.frame=requestAnimationFrame(frame);
  }
  function finish(state,index){
    if(state.playing&&index<state.plan.stops.length-1)state.timer=setTimeout(()=>go(state,index+1,true),1800);else{state.playing=false;update(state);}
  }
  function togglePlay(state){
    if(state.playing){pause(state);return;}
    if(reduced.matches||!state.track)return;
    if(state.index===state.plan.stops.length-1&&Math.abs(state.along-state.track.stopDistances[state.index])<1){state.along=state.track.stopDistances[0];select(state,0);state.map.jumpTo({center:state.track.at(state.along),zoom:VIEW.zoom,pitch:VIEW.pitch});}
    const unfinished=Math.abs(state.along-state.track.stopDistances[state.index])>1;
    go(state,unfinished?state.index:Math.min(state.index+1,state.plan.stops.length-1),true);
  }
  function fallback(state,message){
    if(state.closed)return;
    setMode(state,'2d');state.tour.hidden=false;state.tour.querySelector('.route-tour-controls').hidden=true;state.tour.querySelector('.route-tour-stop').hidden=true;
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
      state.map=new gl.Map({container:state.container,style:{version:8,sources:{onemap:{type:'raster',tiles:['https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png'],tileSize:256,maxzoom:19,attribution:'<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener">OneMap</a> © Singapore Land Authority · HDB footprints & storeys / NEA via data.gov.sg'}},layers:[{id:'background',type:'background',paint:{'background-color':'#eef0e8'}},{id:'onemap',type:'raster',source:'onemap',paint:{'raster-saturation':-.55,'raster-contrast':-.08,'raster-brightness-min':.08,'raster-opacity':.92}}]},center:[state.plan.stops[0].longitude,state.plan.stops[0].latitude],zoom:16.6,pitch:50,bearing:-18,maxZoom:19.5,minZoom:13,maxPitch:70,antialias:true,attributionControl:{compact:true}});
      state.map.addControl(new gl.NavigationControl({visualizePitch:true}),'bottom-right');state.map.scrollZoom.disable();state.map.keyboard.disable();
      state.map.on('error',event=>{if(event.sourceId!=='onemap'||state.tileError)return;state.tileError=true;const status=state.tour.querySelector('.route-3d-status');status.textContent=`${status.textContent} OneMap street tiles are unavailable; building shapes, stops and the saved route remain visible.`.trim();});
      state.map.getCanvas().addEventListener('webglcontextlost',()=>fallback(state,'3D graphics became unavailable. Continue with the 2D map and numbered checklist.'),{once:true});
      state.map.on('dragstart',()=>pause(state));state.map.on('zoomstart',event=>{if(event.originalEvent)pause(state);});
      state.map.once('load',()=>{
        if(state.closed||!state.map)return;
        const map=state.map,color=['case',['boolean',['feature-state','selected'],false],COLORS.selected,['==',['get','cluster_block'],true],COLORS.cluster,['==',['get','role'],'stop'],COLORS.stop,COLORS.context];
        map.setLight({anchor:'viewport',color:'#fffaf0',intensity:.3,position:[1.2,210,30]});
        map.addSource('buildings',{type:'geojson',data:buildings,promoteId:'id'});
        map.addLayer({id:'building-flat',type:'fill',source:'buildings',filter:['!',['>',['coalesce',['get','height_m'],0],0]],paint:{'fill-color':['case',['==',['get','role'],'context'],COLORS.flat,color],'fill-opacity':.9,'fill-outline-color':'#a59f8e'}});
        map.addLayer({id:'building-base',type:'line',source:'buildings',filter:['!=',['get','role'],'context'],paint:{'line-color':['case',['==',['get','cluster_block'],true],COLORS.cluster,COLORS.stop],'line-width':1.4}});
        // Surrounding blocks are see-through so they never hide the stop being previewed.
        map.addLayer({id:'context-heights',type:'fill-extrusion',source:'buildings',filter:['all',['>',['coalesce',['get','height_m'],0],0],['==',['get','role'],'context']],paint:{'fill-extrusion-color':COLORS.context,'fill-extrusion-height':['get','height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':.58,'fill-extrusion-vertical-gradient':true}});
        map.addLayer({id:'building-heights',type:'fill-extrusion',source:'buildings',filter:['all',['>',['coalesce',['get','height_m'],0],0],['!=',['get','role'],'context']],paint:{'fill-extrusion-color':color,'fill-extrusion-height':['get','height_m'],'fill-extrusion-base':0,'fill-extrusion-opacity':.95,'fill-extrusion-vertical-gradient':true}});
        if(state.plan.clusters?.features?.length){map.addSource('clusters',{type:'geojson',data:state.plan.clusters});map.addLayer({id:'cluster-outline',type:'line',source:'clusters',paint:{'line-color':COLORS.cluster,'line-width':1.6,'line-dasharray':[3,2]}},'context-heights');}
        if(state.plan.route?.geometry){map.addSource('route',{type:'geojson',data:{type:'Feature',properties:{},geometry:state.plan.route.geometry}});map.addLayer({id:'route-halo',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#fffef7','line-width':8}},'building-heights');map.addLayer({id:'walking-route',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#1d4a3c','line-width':3.5,...(!state.track?{'line-dasharray':[2,2]}:{})}},'context-heights');}
        state.plan.stops.forEach((stop,index)=>{const button=document.createElement('button');button.type='button';button.className='route-3d-pin';button.textContent=String(stop.number||index+1);button.setAttribute('aria-label',`Show stop ${index+1}: ${stop.name}`);button.onclick=event=>{event.stopPropagation();go(state,index);};state.markers.push(new gl.Marker({element:button,anchor:'center'}).setLngLat([stop.longitude,stop.latitude]).addTo(map));});
        state.popup=new gl.Popup({closeButton:true,closeOnClick:true,maxWidth:'240px',className:'route-3d-popup'});
        ['building-heights','context-heights','building-flat'].forEach(layer=>{map.on('click',layer,event=>{const feature=event.features?.[0];if(!feature)return;state.popup.setLngLat(event.lngLat).setHTML(describe(feature.properties)).addTo(map);});map.on('mouseenter',layer,()=>{map.getCanvas().style.cursor='pointer';});map.on('mouseleave',layer,()=>{map.getCanvas().style.cursor='';});});
        const s=summary(buildings,state.plan);
        state.tour.querySelector('.route-3d-status').textContent=(state.tileError?'OneMap street tiles are unavailable. ':'')+(s.count?`${s.count} official HDB block shapes${state.margin?` within about ${state.margin} m of the route`:''} · ${s.raised} raised from published storeys · ${s.flat} flat (storeys unverified)${s.missing.length?` · no footprint matched for stop ${s.missing.join(', ')}`:''}. Tap a block for details.`:'Building shapes are unavailable for this area. The verified stops and saved route remain visible.');
        select(state,state.index);fit(state);if(state.mode==='3d')map.resize();
      });
    }catch{fallback(state,'3D is unavailable on this device. Continue with the 2D map and numbered checklist.');}
    finally{state.loading=false;}
  }
  function focusStop(id){
    if(!current||current.mode!=='3d'||!current.map)return false;
    const index=current.plan.stops.findIndex(stop=>String(stop.id)===String(id));if(index<0)return false;
    go(current,index);return true;
  }
  function dispose(){
    if(!current)return;const state=current;pause(state);state.closed=true;reduced.removeEventListener('change',state.motionChange);document.removeEventListener('visibilitychange',state.visibility);
    state.popup?.remove();state.map?.remove();state.toolbar.remove();state.tour.remove();state.container.remove();$('.inspection-legend')?.classList.remove('is-hidden-3d');current=null;
  }
  window.RouteFlythrough={mount,focusStop,dispose};
})();
