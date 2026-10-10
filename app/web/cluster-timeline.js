/* Only saved NEA snapshots are shown; gaps are never animated as observations. */
(() => {
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const day=v=>{const d=new Date(`${v}T12:00:00+08:00`);return Number.isNaN(+d)?String(v):d.toLocaleDateString('en-SG',{day:'numeric',month:'short',year:'numeric'});};
  window.ClusterTimeline={label:day,init(timeline,map,currentLayer){
    const box=document.querySelector('#cluster-timeline');
    const days=timeline.filter(d=>d.date&&Array.isArray(d.clusters)).sort((a,b)=>a.date.localeCompare(b.date));
    if(!box||days.length<2)return;
    const historical=L.layerGroup();let index=days.length-1,timer=null,restorePriority=null;
    box.hidden=false;
    box.innerHTML='<div class="cluster-timeline-controls"><button type="button" class="map-chip" id="cluster-play" aria-label="Play saved cluster snapshots">Play</button><label for="cluster-date">Snapshot <output id="cluster-date-label"></output></label><input id="cluster-date" type="range" min="0" max="'+(days.length-1)+'" value="'+index+'" aria-label="Choose saved cluster snapshot"><button type="button" class="text-button" id="cluster-latest">Latest</button></div><p id="cluster-timeline-note" role="status"></p>';
    const slider=box.querySelector('input'),play=box.querySelector('#cluster-play'),note=box.querySelector('p');
    const stop=()=>{clearInterval(timer);timer=null;play.textContent='Play';play.setAttribute('aria-label','Play saved cluster snapshots');};
    const draw=()=>{
      const day=days[index],latest=index===days.length-1;
      slider.value=index;box.querySelector('output').textContent=window.ClusterTimeline.label(day.date);slider.setAttribute('aria-valuetext',`Saved ${window.ClusterTimeline.label(day.date)}`);
      historical.clearLayers();map.removeLayer(currentLayer);map.removeLayer(historical);
      const show=document.querySelector('#show-clusters').checked;
      document.querySelector('#show-priority').disabled=!latest;
      if(!latest){if(restorePriority===null)restorePriority=document.querySelector('#show-priority').checked;document.querySelector('#show-priority').checked=false;document.querySelector('#show-priority').dispatchEvent(new Event('change'));}
      else if(restorePriority!==null){document.querySelector('#show-priority').checked=restorePriority;restorePriority=null;document.querySelector('#show-priority').dispatchEvent(new Event('change'));}
      if(latest){if(show)currentLayer.addTo(map);}else{
        day.clusters.forEach(c=>{if(!Number.isFinite(c.lat)||!Number.isFinite(c.lon)||!Number.isFinite(c.people))return;
          const size=Math.round(16+5*Math.sqrt(Math.max(0,c.people)));
          L.marker([c.lat,c.lon],{icon:L.divIcon({className:'cluster-pin',html:esc(c.people),iconSize:[size,size],iconAnchor:[size/2,size/2]}),title:c.locality})
            .bindPopup('<strong>'+esc(c.people)+' people</strong><br>'+esc(c.locality)+'<br>Saved '+esc(window.ClusterTimeline.label(day.date))+'<br><small>Cluster counts, not new weekly infections.</small>').addTo(historical);
        });if(show)historical.addTo(map);
      }
      const gap=index?Math.round((Date.parse(day.date)-Date.parse(days[index-1].date))/86400000):null;
      note.textContent=(latest?'Saved map. ':'Historical pins; area cards use latest data. ')+(gap?gap+'-day gap. ':'')+'Missing dates stay missing.';
    };
    slider.addEventListener('input',()=>{stop();index=Number(slider.value);draw();});
    play.addEventListener('click',()=>{if(timer){stop();return;}if(index===days.length-1)index=0;draw();
      if(matchMedia('(prefers-reduced-motion: reduce)').matches){note.textContent+=' Reduced motion: use the date slider to step manually.';return;}
      play.textContent='Pause';play.setAttribute('aria-label','Pause saved cluster snapshots');
      timer=setInterval(()=>{index++;draw();if(index===days.length-1)stop();},1800);
    });
    box.querySelector('#cluster-latest').addEventListener('click',()=>{stop();index=days.length-1;draw();});
    document.querySelector('#show-clusters').addEventListener('change',draw);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
    document.querySelectorAll('[data-view],[data-section]').forEach(b=>b.addEventListener('click',stop));
    draw();
  }};
})();
