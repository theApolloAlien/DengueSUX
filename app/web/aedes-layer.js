/* A separate NEA overlay. It never changes the area ranking. */
(() => {
 window.AedesLayer={init(data,api){
  if(!data.aedes?.available||!api.state.map||!window.L)return;
  const label=document.createElement('label');label.className='aedes-toggle';label.innerHTML=`<input type="checkbox"> <span>High mosquito areas <small>NEA · ${window.ChatHome.date(data.aedes.source_date)}${data.aedes.skipped_invalid?.length?' · partial coverage':''}</small></span>`;
  document.querySelector('.map-tools').prepend(label);
  const layer=L.geoJSON(data.aedes,{style:{color:'#76558a',weight:2,fillOpacity:.035},onEachFeature:(f,l)=>l.bindPopup('NEA high mosquito population · '+window.ChatHome.date(f.properties.source_date))});
  label.querySelector('input').onchange=e=>e.target.checked?layer.addTo(api.state.map):api.state.map.removeLayer(layer);
 }};
})();
