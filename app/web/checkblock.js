/* Check my block: distance from a home to the nearest active cluster, worked out in the browser.
   Location from "Use my location" never leaves the page; postal codes go to the server's OneMap lookup only when it is configured. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = n => `<i class="ph ph-${n}" aria-hidden="true"></i>`;
  const num = n => Number.isFinite(n) ? Math.round(n).toLocaleString('en-SG') : '—';
  const LANGS = [['en','English'],['zh','中文'],['ms','Bahasa Melayu'],['ta','தமிழ்']];
  const TEXT = {
    en: {inside: 'is inside an active dengue cluster', near: d => `is about ${d} from an active dengue cluster`, far: d => `has no active cluster within 1 km. The nearest is about ${d} away`, steps: 'Five things to do this week'},
    zh: {inside: '位于活跃骨痛热症病例群范围内', near: d => `距离活跃骨痛热症病例群约 ${d}`, far: d => `1公里内没有活跃病例群，最近的约 ${d}`, steps: '本周可以做的五件事'},
    ms: {inside: 'berada dalam kelompok denggi aktif', near: d => `kira-kira ${d} dari kelompok denggi aktif`, far: d => `tiada kelompok aktif dalam 1 km. Yang terdekat kira-kira ${d}`, steps: 'Lima perkara untuk dilakukan minggu ini'},
    ta: {inside: 'செயலில் உள்ள டெங்கி தொகுப்பிற்குள் உள்ளது', near: d => `செயலில் உள்ள டெங்கி தொகுப்பிலிருந்து சுமார் ${d} தொலைவில் உள்ளது`, far: d => `1 கி.மீ.க்குள் செயலில் உள்ள தொகுப்பு இல்லை. அருகிலுள்ளது சுமார் ${d}`, steps: 'இந்த வாரம் செய்ய வேண்டிய ஐந்து விஷயங்கள்'}
  };
  let data = {}, hooks = {}, lang = 'en', last = null;

  // Equirectangular metres around Singapore: accurate to well under 1% at these distances.
  const toXY = (lat, lon, lat0) => [lon * 111320 * Math.cos(lat0 * Math.PI / 180), lat * 110540];
  function segmentDistance(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / (dx*dx + dy*dy || 1)));
    return Math.hypot(p[0] - a[0] - t*dx, p[1] - a[1] - t*dy);
  }
  function inside(pt, ring) {
    let hit = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi) hit = !hit;
    }
    return hit;
  }
  function distanceToCluster(lat, lon, geometry) {
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
    const p = toXY(lat, lon, lat);
    let best = Infinity;
    for (const polygon of polygons) {
      const rings = polygon.map(ring => ring.map(([x, y]) => toXY(y, x, lat)));
      if (inside(p, rings[0]) && !rings.slice(1).some(r => inside(p, r))) return 0;
      for (const ring of rings) for (let i = 1; i < ring.length; i++) best = Math.min(best, segmentDistance(p, ring[i-1], ring[i]));
    }
    return best;
  }
  const distanceText = m => m < 1000 ? `${Math.max(10, Math.round(m / 10) * 10)} m` : `${(m / 1000).toFixed(1)} km`;
  const steps = () => {
    const areas = data.notices?.areas || data.notices?.notices || {};
    for (const byLang of Object.values(areas)) for (const n of Object.values(byLang || {})) if (n?.source_facts?.prevention_steps) return n.source_facts.prevention_steps;
    return null;
  };

  function check(lat, lon, label) {
    const clusters = (data.current?.clusters?.features || []).map(f => ({p: f.properties, d: distanceToCluster(lat, lon, f.geometry)})).sort((a, b) => a.d - b.d);
    last = {lat, lon, label, nearest: clusters[0] || null};
    render();
  }
  function render() {
    const box = $('#check-result');
    if (!last) { box.hidden = true; return; }
    const n = last.nearest, t = TEXT[lang], where = esc(last.label || 'Your location');
    const status = !n ? 'far' : n.d === 0 ? 'inside' : n.d <= 1000 ? 'near' : 'far';
    const sentence = !n ? 'No active clusters in this snapshot.' : status === 'inside' ? `${where} ${t.inside}` : status === 'near' ? `${where} ${t.near(distanceText(n.d))}` : `${where} ${t.far(distanceText(n.d))}`;
    const list = steps()?.[lang] || [];
    const share = `${n ? `${n.p.name.split(' / ')[0]}: ${n.p.cases} people in an active dengue cluster (NEA, ${data.current?.as_of?.slice(0,10) || ''}). ` : ''}${list.join(' ')} https://www.nea.gov.sg/dengue-zika/stop-dengue-now`;
    box.hidden = false;
    box.className = `check-result is-${status}`;
    box.innerHTML = `<div class="check-head">${icon(status === 'far' ? 'shield-check' : 'warning-circle')}<div><p class="check-sentence" lang="${lang}">${sentence}.</p>
      ${n ? `<p class="check-detail">${esc(n.p.name.split(' / ').slice(0, 2).join(' / '))} · <strong>${num(n.p.cases)} people</strong> · ${esc((n.p.area_names || []).join(' · '))}</p>` : ''}</div></div>
      <div class="notice-tabs" role="group" aria-label="Language">${LANGS.map(([id, name]) => `<button data-check-lang="${id}" aria-pressed="${id === lang}" class="${id === lang ? 'active' : ''}" lang="${id}">${name}</button>`).join('')}</div>
      ${list.length ? `<h4 lang="${lang}">${t.steps}</h4><ol class="check-steps" lang="${lang}">${list.map(s => `<li>${esc(s)}</li>`).join('')}</ol>` : ''}
      <div class="check-actions"><a class="outline-button" href="https://wa.me/?text=${encodeURIComponent(share)}" target="_blank" rel="noopener">${icon('whatsapp-logo')} Share with neighbours</a>
      ${n && n.d <= 1000 ? `<button class="text-button" data-check-area="${esc(n.p.area_code)}">${icon('map-trifold')} See this area</button>` : ''}</div>
      <p class="check-note">Distance to the dated NEA cluster footprint, not a measure of personal risk. The shared message contains no location.</p>`;
    box.querySelectorAll('[data-check-lang]').forEach(b => b.addEventListener('click', () => { lang = b.dataset.checkLang; render(); }));
    box.querySelector('[data-check-area]')?.addEventListener('click', e => hooks.selectArea?.(e.currentTarget.dataset.checkArea));
  }
  function status(message) { const box = $('#check-result'); box.hidden = false; box.className = 'check-result'; box.innerHTML = `<p class="check-detail" role="status">${esc(message)}</p>`; }

  async function init(payload, callbacks) {
    data = payload; hooks = callbacks;
    const example = (Object.values(data.inspection?.areas || {}).flatMap(a => a.cluster_blocks || []))[0];
    $('#check-locate').addEventListener('click', () => {
      if (!navigator.geolocation) return status('Location is not available in this browser.');
      status('Finding your location…');
      navigator.geolocation.getCurrentPosition(p => check(p.coords.latitude, p.coords.longitude, 'Your location'),
        () => status('Location permission was not given. Try the example or the area list instead.'), {enableHighAccuracy: false, timeout: 10000, maximumAge: 600000});
    });
    const exampleButton = $('#check-example');
    if (example) exampleButton.addEventListener('click', () => check(example.latitude, example.longitude, `Blk ${example.block} ${example.street.replace(/\b\w+/g, w => w[0] + w.slice(1).toLowerCase())}`));
    else exampleButton.hidden = true;
    try {
      const ok = !window.DENGUESUX_DATA && (await (await fetch('/api/locate/status', {signal: AbortSignal.timeout(6000)})).json()).postal;
      $('#check-postal-form').hidden = !ok;
    } catch { $('#check-postal-form').hidden = true; }
    $('#check-postal-form').addEventListener('submit', async e => {
      e.preventDefault();
      const postal = $('#check-postal').value.trim();
      if (!/^\d{6}$/.test(postal)) return status('Enter a 6-digit postal code.');
      status('Looking up the postal code…');
      try {
        const r = await fetch(`/api/locate?postal=${encodeURIComponent(postal)}`);
        if (!r.ok) return status((await r.json()).detail || 'That postal code could not be located.');
        const found = await r.json(); check(found.latitude, found.longitude, found.address);
      } catch { status('The postal lookup is unavailable. Try “Use my location”.'); }
    });
  }
  window.CheckBlock = {init};
})();
