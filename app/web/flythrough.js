/* Optional 3D route preview. Geometry is observed; floor-derived heights are illustrative. */
(() => {
  'use strict';
  const $=s=>document.querySelector(s), reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const empty=()=>({type:'FeatureCollection',features:[]});
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
    if(!footprints)footprints=fetch('/data/footprints.json',{cache:'no-cache',signal:AbortSignal.timeout(12000)}).then(r=>r.ok?r.json():null).catch(()=>null);
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
  function mount(plan,area,onSelect){
    dispose();
    if(!plan.stops?.length)return;
    const wrap=$('.inspection-map-wrap'),column=$('.inspection-map-column');if(!wrap||!column)return;
    const toolbar=document.createElement('div');toolbar.className='route-preview-toolbar';
    toolbar.innerHTML='<div class="route-view-tabs" role="group" aria-label="Inspection map view"><button type="button" data-map-mode="2d" aria-pressed="true">2D map</button><button type="button" data-map-mode="3d" aria-pressed="false"><i class="ph ph-cube" aria-hidden="true"></i> 3D route</button></div><span class="route-preview-label">Preview your walk</span>';
    column.insertBefore(toolbar,wrap);
    const container=document.createElement('div');container.id='route-3d';container.hidden=true;container.setAttribute('aria-label','3D inspection route with approximate building heights');wrap.prepend(container);
    const tour=document.createElement('section');tour.className='route-tour';tour.hidden=true;tour.setAttribute('aria-label','Route preview controls');
    tour.innerHTML='<div class="route-tour-controls"><button type="button" data-tour="previous" aria-label="Previous inspection stop"><i class="ph ph-caret-left" aria-hidden="true"></i></button><button type="button" data-tour="play" class="route-tour-play"><i class="ph ph-play" aria-hidden="true"></i><span>Play route</span></button><button type="button" data-tour="next" aria-label="Next inspection stop"><i class="ph ph-caret-right" aria-hidden="true"></i></button><button type="button" data-tour="fit" aria-label="Fit the complete 3D route"><i class="ph ph-arrows-out-simple" aria-hidden="true"></i></button></div><div class="route-tour-stop"><span role="status" aria-live="polite"></span><button type="button" data-tour="checklist">Checklist <i class="ph ph-arrow-down" aria-hidden="true"></i></button></div><p class="route-3d-note"></p><p class="route-3d-status" role="status"></p>';
    wrap.after(tour);
    const state={plan,area,onSelect,wrap,toolbar,container,tour,map:null,mode:'2d',index:0,playing:false,frame:0,timer:0,track:routeTrack(plan),along:0,markers:[],loading:false,closed:false};
    current=state;if(state.track)state.along=state.track.stopDistances[0];
    toolbar.querySelectorAll('[data-map-mode]').forEach(button=>button.addEventListener('click',()=>setMode(state,button.dataset.mapMode)));
    tour.querySelector('[data-tour=previous]').onclick=()=>go(state,state.index-1);
    tour.querySelector('[data-tour=next]').onclick=()=>go(state,state.index+1);
    tour.querySelector('[data-tour=play]').onclick=()=>togglePlay(state);
    tour.querySelector('[data-tour=fit]').onclick=()=>{pause(state);fit(state);};
    tour.querySelector('[data-tour=checklist]').onclick=()=>document.getElementById('stop-'+state.plan.stops[state.index].id)?.scrollIntoView({block:'center',behavior:reduced.matches?'instant':'smooth'});
    state.motionChange=()=>{if(reduced.matches)pause(state);update(state);};reduced.addEventListener('change',state.motionChange);
    state.visibility=()=>{if(document.hidden)pause(state);};document.addEventListener('visibilitychange',state.visibility);
    update(state);
  }
  function update(state){
    if(state.closed)return;
    const stops=state.plan.stops,stop=stops[state.index],play=state.tour.querySelector('[data-tour=play]');
    play.disabled=reduced.matches||!state.track||stops.length<2;
    play.querySelector('span').textContent=reduced.matches?'Manual preview':state.playing?'Pause route':'Play route';
    play.querySelector('i').className='ph ph-'+(state.playing?'pause':'play');play.setAttribute('aria-label',state.playing?'Pause route preview':'Play route preview');
    state.tour.querySelector('[data-tour=previous]').disabled=state.index===0;
    state.tour.querySelector('[data-tour=next]').disabled=state.index===stops.length-1;
    state.tour.querySelector('.route-tour-stop span').textContent=`Stop ${state.index+1} of ${stops.length} · ${stop.name}`;
    const motion=reduced.matches?' Reduced motion: use Previous and Next for instant views.':!state.track?' Walking directions unavailable: preview each stop manually.':'';
    state.tour.querySelector('.route-3d-note').textContent='Building heights ≈ storeys × 3 m, for illustration; unknown heights stay flat. Red = cluster blocks. Places to check, not confirmed breeding sites.'+motion;
    state.markers.forEach((marker,i)=>marker.getElement().classList.toggle('is-selected',i===state.index));
  }
  function stopMotion(state){cancelAnimationFrame(state.frame);clearTimeout(state.timer);state.frame=0;state.timer=0;state.map?.stop();}
  function pause(state){stopMotion(state);state.playing=false;update(state);}
  function select(state,index){state.index=index;state.onSelect?.(state.plan.stops[index].id);update(state);}
  function fit(state){
    if(!state.map)return;
    const bounds=new maplibregl.LngLatBounds();state.plan.stops.forEach(stop=>bounds.extend([stop.longitude,stop.latitude]));
    state.map.fitBounds(bounds,{padding:65,maxZoom:17.7,pitch:53,bearing:-22,duration:reduced.matches?0:550});
  }
  function go(state,index,continuous=false){
    if(state.closed||!state.map||index<0||index>=state.plan.stops.length)return;
    stopMotion(state);state.playing=continuous;select(state,index);
    const stop=state.plan.stops[index],target=state.track?.stopDistances[index];
    if(reduced.matches||!state.track){state.map.jumpTo({center:[stop.longitude,stop.latitude],zoom:18.2,pitch:55});return;}
    const start=state.along,length=target-start,began=performance.now(),duration=Math.min(6500,Math.max(1600,Math.abs(length)*22));
    const frame=now=>{
      if(state.closed||state.mode!=='3d')return;
      const t=Math.min(1,(now-began)/duration);state.along=start+length*t;
      const center=state.track.at(state.along),ahead=state.track.at(state.along+(length<0?-8:8));
      const bearing=distance(center,ahead)>.3?Math.atan2((ahead[0]-center[0])*Math.cos(center[1]*Math.PI/180),ahead[1]-center[1])*180/Math.PI:state.map.getBearing();
      // Each camera center lies on a segment of the saved OneMap walking geometry.
      const currentBearing=state.map.getBearing(),turn=((bearing-currentBearing+540)%360)-180;
      state.map.jumpTo({center,zoom:18.2,pitch:60,bearing:currentBearing+turn*.06});
      if(t<1)state.frame=requestAnimationFrame(frame);
      else{state.frame=0;if(state.playing&&index<state.plan.stops.length-1)state.timer=setTimeout(()=>go(state,index+1,true),1400);else{state.playing=false;update(state);}}
    };
    state.frame=requestAnimationFrame(frame);
  }
  function togglePlay(state){
    if(state.playing){pause(state);return;}
    if(reduced.matches||!state.track)return;
    if(state.index===state.plan.stops.length-1&&Math.abs(state.along-state.track.stopDistances[state.index])<1){state.along=state.track.stopDistances[0];select(state,0);state.map.jumpTo({center:state.track.at(state.along),zoom:18.2,pitch:60});}
    const unfinished=Math.abs(state.along-state.track.stopDistances[state.index])>1;
    go(state,unfinished?state.index:Math.min(state.index+1,state.plan.stops.length-1),true);
  }
  function fallback(state,message){
    if(state.closed)return;
    setMode(state,'2d');state.tour.hidden=false;state.tour.querySelector('.route-tour-controls').hidden=true;state.tour.querySelector('.route-tour-stop').hidden=true;
    state.tour.querySelector('.route-3d-note').hidden=true;state.tour.querySelector('.route-3d-status').textContent=message;
    state.toolbar.querySelector('[data-map-mode="3d"]').disabled=true;
    state.map?.remove();state.map=null;
  }
  async function setMode(state,mode){
    if(state.closed)return;
    state.mode=mode;pause(state);
    state.toolbar.querySelectorAll('[data-map-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.mapMode===mode)));
    state.container.hidden=mode!=='3d';$('#inspection-map').hidden=mode==='3d';$('#fit-inspection').hidden=mode==='3d';
    state.wrap.classList.toggle('is-3d',mode==='3d');state.tour.hidden=mode!=='3d';
    if(mode==='2d')return;
    if(state.map){state.map.resize();return;}
    if(state.loading)return;state.loading=true;
    state.tour.querySelector('.route-3d-status').textContent='Loading the route and verified building shapes…';
    try{
      const [gl,artifact]=await Promise.all([loadLibrary(),loadFootprints()]);if(state.closed)return;
      if(gl.supported&&!gl.supported())throw new Error('WebGL unavailable');
      const buildings=artifact?.areas?.[state.area.code]||empty();
      state.map=new gl.Map({container:state.container,style:{version:8,sources:{onemap:{type:'raster',tiles:['https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png'],tileSize:256,maxzoom:20,attribution:'<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener">OneMap</a> © Singapore Land Authority · HDB / NEA / data.gov.sg'}},layers:[{id:'background',type:'background',paint:{'background-color':'#eff1e7'}},{id:'onemap',type:'raster',source:'onemap'}]},center:[state.plan.stops[0].longitude,state.plan.stops[0].latitude],zoom:16.8,pitch:53,bearing:-22,maxZoom:20,minZoom:11,antialias:true,attributionControl:{compact:true}});
      state.map.addControl(new gl.NavigationControl({visualizePitch:true}),'bottom-right');state.map.scrollZoom.disable();
      state.map.on('error',event=>{if(event.sourceId==='onemap')state.tour.querySelector('.route-3d-status').textContent='OneMap tiles are unavailable. Verified building shapes, stops and the saved route remain visible.';});
      state.map.getCanvas().addEventListener('webglcontextlost',()=>fallback(state,'3D graphics became unavailable. Continue with the 2D map and numbered checklist.'),{once:true});
      state.map.on('dragstart',()=>pause(state));state.map.on('zoomstart',event=>{if(event.originalEvent)pause(state);});
      state.map.once('load',()=>{
        if(state.closed||!state.map)return;
        const map=state.map,color=['case',['==',['get','cluster_block'],true],'#c24f3b','#95a78c'];
        map.addSource('buildings',{type:'geojson',data:buildings});
        map.addLayer({id:'building-footprints',type:'fill',source:'buildings',paint:{'fill-color':color,'fill-opacity':.65,'fill-outline-color':'#687861'}});
        map.addLayer({id:'building-heights',type:'fill-extrusion',source:'buildings',filter:['>', ['coalesce',['get','height_m'],0],0],paint:{'fill-extrusion-color':color,'fill-extrusion-height':['coalesce',['get','height_m'],0],'fill-extrusion-base':0,'fill-extrusion-opacity':.86}});
        if(state.plan.clusters?.features?.length){map.addSource('clusters',{type:'geojson',data:state.plan.clusters});map.addLayer({id:'cluster-outline',type:'line',source:'clusters',paint:{'line-color':'#c24f3b','line-width':1.5,'line-dasharray':[3,2]}});}
        if(state.plan.route?.geometry){map.addSource('route',{type:'geojson',data:{type:'Feature',properties:{},geometry:state.plan.route.geometry}});map.addLayer({id:'route-halo',type:'line',source:'route',paint:{'line-color':'#fffef7','line-width':7}});map.addLayer({id:'walking-route',type:'line',source:'route',paint:{'line-color':'#224e41','line-width':3,...(!state.track?{'line-dasharray':[2,2]}:{})}});}
        state.plan.stops.forEach((stop,index)=>{const button=document.createElement('button');button.type='button';button.className='route-3d-pin';button.textContent=String(stop.number||index+1);button.setAttribute('aria-label',`Show stop ${index+1}: ${stop.name}`);button.onclick=()=>go(state,index);state.markers.push(new gl.Marker({element:button,anchor:'center'}).setLngLat([stop.longitude,stop.latitude]).addTo(map));});
        state.plan.cluster_blocks?.forEach(block=>{const dot=document.createElement('span');dot.className='route-cluster-dot';dot.title=`Cluster block ${block.block} ${block.street}`;new gl.Marker({element:dot,anchor:'center'}).setLngLat([block.longitude,block.latitude]).addTo(map);});
        state.tour.querySelector('.route-3d-status').textContent=buildings.features.length?`${buildings.features.length} source building shapes · ${buildings.features.filter(f=>Number(f.properties.height_m)>0).length} with matched storeys`:'Building shapes are unavailable for this area. The verified stops and saved route remain visible.';
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
    state.map?.remove();state.toolbar.remove();state.tour.remove();state.container.remove();current=null;
  }
  window.RouteFlythrough={mount,focusStop,dispose};
})();
