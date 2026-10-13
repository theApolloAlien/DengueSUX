/* Controls over the Map page's 3D island: now vs the two-week outlook, a time-lapse of every listed day since
   2019, and a dive from the island into one area's 3D walk. Uses Landscape3D's public methods only. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const icon = n => `<i class="ph ph-${n}" aria-hidden="true"></i>`;
  const day = v => new Date(v + 'T00:00:00+08:00').toLocaleDateString('en-SG', { day: 'numeric', month: 'short', year: 'numeric' });
  let api = null, land = null, host = null, selected = null, mode = 'now', timer = 0, index = 0, pendingTimelapse = false, pendingDive = null;

  const data = () => api?.state?.data || {};
  const history = () => data().area_history;
  const slug = name => String(name).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-$/, '');

  function controls() {
    const outlook = data().area_forecast?.areas?.length;
    const h = history();
    const bar = document.createElement('div');
    bar.className = 'map3d-controls';
    bar.innerHTML = `<div class="segmented" role="group" aria-label="What the heights show">
        <button type="button" data-mode3d="now" aria-pressed="true" class="active">Now</button>
        <button type="button" data-mode3d="outlook" aria-pressed="false" ${outlook ? '' : 'disabled'}>In two weeks</button>
        <button type="button" data-mode3d="history" aria-pressed="false" ${h?.dates?.length > 2 ? '' : 'disabled'}>${icon('clock-counter-clockwise')} Since ${esc((h?.dates?.[0] || '').slice(0, 4))}</button>
      </div>
      <button type="button" class="outline-button compare-button" id="compare-button" aria-pressed="false" title="Two synced views side by side">${icon('columns')} <span>Compare</span></button>
      <button type="button" class="solid-button dive-button" id="dive-button" hidden>${icon('arrow-down-right')} <span>Dive in</span></button>`;
    host.append(bar);
    const player = document.createElement('div');
    player.className = 'timelapse-player';
    player.hidden = true;
    player.innerHTML = `<div class="timelapse-date" aria-live="polite"><strong></strong><span></span></div>
      <div class="timelapse-row"><button type="button" class="icon-button" id="timelapse-play" aria-label="Pause">${icon('pause')}</button>
      <input type="range" id="timelapse-scrub" min="0" max="${Math.max(0, (h?.dates?.length || 1) - 1)}" value="0" aria-label="Listed day"><button type="button" class="timelapse-speed" id="timelapse-speed" aria-label="Time-lapse speed: normal">1×</button></div>
      <canvas class="timelapse-spark" width="640" height="44" aria-hidden="true"></canvas>
      <div class="timelapse-years" aria-hidden="true"></div>
      <p class="timelapse-note">Each step is a day NEA's cluster list was saved (Internet Archive captures, then daily snapshots). Days in between were not captured and are not filled in.</p>`;
    host.append(player);
    bar.querySelectorAll('[data-mode3d]').forEach(b => b.onclick = () => setMode(b.dataset.mode3d));
    $('#dive-button', bar).onclick = dive;
    $('#compare-button', bar).onclick = () => compare.open ? closeCompare() : openCompare();
    $('#timelapse-play', player).onclick = () => timer ? stop() : play();
    $('#timelapse-scrub', player).oninput = e => { stop(); show(Number(e.target.value), 250); };
    $('#timelapse-speed', player).onclick = () => setSpeed(speed === 1 ? 4 : 1);
    if (h?.dates?.length) {
      // The day with the most people in clusters (the 2020 outbreak) gets a longer pause and a caption.
      const totals = h.dates.map(d => (h.areas?.[d] || []).reduce((n, r) => n + r[1], 0));
      peakIndex = totals.indexOf(Math.max(...totals)); peakTotal = totals[peakIndex];
      drawSpark(totals);
      const years = {}; h.dates.forEach((d, i) => { const y = d.slice(0, 4); if (!(y in years)) years[y] = i; });
      let last = -1;
      $('.timelapse-years', player).innerHTML = Object.entries(years).map(([y, i]) => { const at = i / Math.max(1, h.dates.length - 1) * 100; if (last >= 0 && at - last < 7) return ''; last = at; return `<span style="left:${at}%">${y}</span>`; }).join('');
    }
  }

  function setMode(next) {
    mode = next; stop();
    host.querySelectorAll('[data-mode3d]').forEach(b => { b.setAttribute('aria-pressed', String(b.dataset.mode3d === next)); b.classList.toggle('active', b.dataset.mode3d === next); });
    land.labels(next === 'now');
    $('.timelapse-player', host).hidden = next !== 'history';
    host.classList.toggle('is-history', next === 'history');
    if (next === 'now') land.showNow();
    if (next === 'outlook') land.showOutlook(data().area_forecast);
    if (next === 'history') { index = 0; lastRun = show(0, 600).then(() => play()); }
  }

  function peopleOn(date) {
    const rows = history().areas?.[date] || [];
    return new Map(rows.map(([code, people, clusters]) => [code, { people, clusters }]));
  }

  function show(i, ms = 520) {
    const h = history(); if (!h?.dates?.length) return Promise.resolve();
    index = Math.max(0, Math.min(h.dates.length - 1, i));
    const date = h.dates[index], rows = h.areas?.[date] || [];
    const total = rows.reduce((n, r) => n + r[1], 0), areas = rows.filter(r => r[2] > 0).length;
    const player = $('.timelapse-player', host);
    const peak = index === peakIndex && total === peakTotal;
    $('.timelapse-date strong', player).textContent = day(date) + (peak ? ' · the peak' : '');
    $('.timelapse-date span', player).textContent = `${areas} ${areas === 1 ? 'area' : 'areas'} with clusters · ${total.toLocaleString('en-SG')} people (shared clusters counted per area) · ${h.sources?.[date] || ''}`;
    player.classList.toggle('is-peak', peak); sparkCursor(index);
    $('#timelapse-scrub', player).value = String(index);
    land.caption(`Height = people in active clusters on ${day(date)}`);
    return land.setPeople(peopleOn(date), ms);
  }

  let speed = 1, finished = [], peakIndex = -1, peakTotal = 0, lastRun = Promise.resolve(), walkIndex = null, walkIndexData = null;
  // Real time between listed days sets the pace: a one-day gap is quick, a long archive gap lingers; the peak holds.
  function stepFor(i) {
    const h = history(), gap = i > 0 ? (Date.parse(h.dates[i]) - Date.parse(h.dates[i - 1])) / 864e5 : 1;
    const ms = Math.min(1100, Math.max(230, 200 + gap * 4));
    return (i === peakIndex ? ms + 1800 : ms) / speed;
  }
  function setSpeed(next) {
    speed = next; const b = host && $('#timelapse-speed', host);
    if (b) { b.textContent = `${speed}×`; b.setAttribute('aria-label', `Time-lapse speed: ${speed === 1 ? 'normal' : speed + ' times'}`); }
  }
  function drawSpark(totals) {
    const canvas = host && $('.timelapse-spark', host); if (!canvas || !totals.length) return;
    const c = canvas.getContext('2d'), w = canvas.width, h = canvas.height, max = Math.max(...totals, 1);
    c.clearRect(0, 0, w, h); c.beginPath();
    totals.forEach((v, i) => { const x = i / Math.max(1, totals.length - 1) * (w - 2) + 1, y = h - 3 - v / max * (h - 8); i ? c.lineTo(x, y) : c.moveTo(x, y); });
    c.strokeStyle = '#2f6a55'; c.lineWidth = 1.5; c.stroke();
    c.lineTo(w - 1, h); c.lineTo(1, h); c.closePath(); c.fillStyle = 'rgba(47,106,85,.12)'; c.fill();
    canvas.dataset.max = String(max); canvas.dataset.totals = JSON.stringify(totals);
  }
  function sparkCursor(i) {
    const canvas = host && $('.timelapse-spark', host); if (!canvas?.dataset.totals) return;
    const totals = JSON.parse(canvas.dataset.totals); drawSpark(totals);
    const c = canvas.getContext('2d'), w = canvas.width, h = canvas.height, max = Number(canvas.dataset.max) || 1;
    const x = i / Math.max(1, totals.length - 1) * (w - 2) + 1, y = h - 3 - totals[i] / max * (h - 8);
    c.beginPath(); c.moveTo(x, 0); c.lineTo(x, h); c.strokeStyle = 'rgba(22,63,53,.35)'; c.lineWidth = 1; c.stroke();
    c.beginPath(); c.arc(x, y, 3.5, 0, Math.PI * 2); c.fillStyle = i === peakIndex ? '#c2523c' : '#163f35'; c.fill();
  }
  function play() {
    if (reduced()) return Promise.resolve();
    const button = $('#timelapse-play', host); button.innerHTML = icon('pause'); button.setAttribute('aria-label', 'Pause');
    return new Promise(resolve => {
      finished.push(resolve);
      const tick = () => {
        const h = history(); if (mode !== 'history') return stop();
        if (index >= h.dates.length - 1) return stop();
        const ms = stepFor(index + 1);
        show(index + 1, Math.min(ms * .8, 700));
        timer = setTimeout(tick, ms);
      };
      clearTimeout(timer); timer = setTimeout(tick, stepFor(index + 1));
    });
  }

  function stop() {
    clearTimeout(timer); timer = 0;
    const button = host && $('#timelapse-play', host);
    if (button) { button.innerHTML = icon('play'); button.setAttribute('aria-label', 'Play'); }
    finished.splice(0).forEach(r => r());
  }
  function loadWalkIndex() {
    if (walkIndex) return walkIndex;
    walkIndex = (window.DENGUESUX_DATA ? Promise.resolve(null) : fetch('/data/walks/index.json', {cache: 'no-cache', signal: AbortSignal.timeout(8000)}).then(r => r.ok ? r.json() : null).catch(() => null))
      .then(d => { walkIndexData = d; syncDive(); return d; });
    return walkIndex;
  }

  // Split screen: the island beside itself with a different day or the outlook, cameras locked together.
  const compare = {open: false, land: null, host: null, sync: null, what: 'outlook'};
  function compareTargets() {
    const h = history(), out = [];
    if (data().area_forecast?.areas?.length) out.push(['outlook', 'In two weeks (outlook)']);
    if (h?.dates?.length) {
      const totals = h.dates.map(d => (h.areas?.[d] || []).reduce((n, r) => n + r[1], 0)), i = totals.indexOf(Math.max(...totals));
      out.push(['peak:' + h.dates[i], `The peak, ${day(h.dates[i])}`]);
      const y = h.dates.find(d => d > new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10)); if (y) out.push(['day:' + y, `A year ago, ${day(y)}`]);
    }
    return out;
  }
  async function openCompare() {
    if (compare.open || !land?.map) return;
    const panel = host.parentElement, targets = compareTargets(); if (!panel || !targets.length) return;
    compare.open = true; stop(); setMode('now'); panel.classList.add('is-compare'); $('#compare-button', host).setAttribute('aria-pressed', 'true');
    const h2 = document.createElement('div'); h2.className = 'map-3d-host map-3d-compare'; panel.append(h2); compare.host = h2;
    const bar = document.createElement('div'); bar.className = 'compare-bar';
    bar.innerHTML = `<label class="sr-only" for="compare-what">Right view</label><select id="compare-what">${targets.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('')}</select><span class="compare-left">Left: today</span>`;
    h2.append(bar);
    compare.land = window.Landscape3D.mount(h2, data().current, {theme: 'night', orbit: false, gestures: false, intro: false, rise: false, labels: 0, interactive: false, padding: {top: 50, bottom: 50, left: 20, right: 20}});
    if (!compare.land) return closeCompare();
    await compare.land.ready(); land.resize(); compare.land.resize();
    const apply = async () => { const v = $('#compare-what', bar).value; compare.what = v;
      if (v === 'outlook') await compare.land.showOutlook(data().area_forecast);
      else { const date = v.split(':')[1]; compare.land.labels(false); await compare.land.setPeople(peopleOn(date), 700); compare.land.caption(`Height = people in active clusters on ${day(date)}`); } };
    $('#compare-what', bar).onchange = apply; await apply();
    const m1 = land.map, m2 = compare.land.map;
    compare.sync = () => { if (!m2 || !compare.open) return; m2.jumpTo({center: m1.getCenter(), zoom: m1.getZoom(), bearing: m1.getBearing(), pitch: m1.getPitch()}); };
    m1.on('move', compare.sync); compare.sync();
  }
  function closeCompare() {
    if (!compare.open) return; compare.open = false;
    try { land?.map?.off('move', compare.sync); } catch {}
    compare.land?.dispose(); compare.host?.remove(); compare.land = null; compare.host = null;
    host.parentElement?.classList.remove('is-compare'); $('#compare-button', host)?.setAttribute('aria-pressed', 'false'); land?.resize();
  }
  document.addEventListener('denguesux:route', e => { if (e.detail.view !== 'map') closeCompare(); });
  function syncDive() {
    const button = host && $('#dive-button', host); if (!button) return;
    const area = api.state.areas.find(a => a.code === selected), entry = walkIndexData?.areas?.[area?.code];
    // An area with no official place, HDB block or context building has no 3D scene to dive into (Tuas, the islands).
    const hasScene = !entry || entry.stops > 0 || ((entry.buildings || 0) + (entry.city_buildings || 0)) > 0 || !!data().inspection?.areas?.[area?.code]?.stops?.length;
    button.hidden = !area || !hasScene || mode === 'history';
    if (area) $('span', button).textContent = `Dive into ${area.name}`;
  }

  async function dive() {
    const area = api.state.areas.find(a => a.code === selected); if (!area) return;
    stop();
    host.classList.add('is-diving');
    window.Fieldwork?.loadWalk?.(area.code);  // prefetch the walk while the island sinks
    await land.dive(area.code);
    // Hand the island's final camera to the walk so it continues the same move instead of cutting to an overview.
    const m = land.map; window.RouteFlythrough.arrival = m ? {center: m.getCenter(), zoom: m.getZoom(), pitch: m.getPitch(), bearing: m.getBearing()} : null;
    window.RouteFlythrough.autoplay = true;  // the walk starts on arrival
    window.Product.go('plan', area.code);
    setTimeout(() => host.classList.remove('is-diving'), 600);
  }

  document.addEventListener('denguesux:ready', e => { api = e.detail.api; });
  document.addEventListener('denguesux:landscape', async e => {
    land = e.detail.landscape; host = e.detail.host; if (!land) return;
    controls(); loadWalkIndex(); await land.ready();
    if (selected) land.select(selected);
    syncDive();
    if (pendingTimelapse) { pendingTimelapse = false; setMode('history'); }
    applyPending();
    if (pendingDive) { const code = pendingDive; pendingDive = null; selected = code; land.select(code); syncDive(); }
  });
  document.addEventListener('denguesux:area-detail', e => { selected = e.detail.area.code; land?.select(selected); syncDive(); });
  document.addEventListener('denguesux:route', e => {
    if (e.detail.view !== 'map') return stop();
    // Deep links into a 3D state: #map/3d/history/2020-08-21 (a listed day) and #map/3d/outlook (the two-week outlook).
    const [, sub, what, value] = e.detail.parts || [];
    if (sub === '3d' && (what === 'history' || what === 'outlook')) { pendingState = {what, value}; applyPending(); }
  });
  let pendingState = null;
  async function applyPending() {
    if (!land || !pendingState || !host) return; const {what, value} = pendingState; pendingState = null; await land.ready();
    if (what === 'outlook') return setMode('outlook');
    const h = history(), i = value ? h?.dates?.indexOf(value) : -1;
    if (i >= 0) { mode = 'history'; stop(); host.querySelectorAll('[data-mode3d]').forEach(b => { b.setAttribute('aria-pressed', String(b.dataset.mode3d === 'history')); b.classList.toggle('active', b.dataset.mode3d === 'history'); }); land.labels(false); $('.timelapse-player', host).hidden = false; host.classList.add('is-history'); show(i, 600); }
    else setMode('history');
  }
  window.Map3DExtras = {
    whenReady: () => new Promise(resolve => { const check = () => land ? land.ready().then(resolve) : setTimeout(check, 120); check(); }),
    setMode: next => land && setMode(next),
    /** Play the whole time-lapse (first listed day to today) at a given speed; resolves at the end or after maxMs. */
    async runTimelapse({speed: s = 4, maxMs = 40000} = {}) {
      if (!land) return; await land.ready(); setSpeed(s); setMode('history');
      await Promise.race([lastRun, new Promise(r => setTimeout(r, maxMs))]); stop();
    },
    hasScene: code => { const e = walkIndexData?.areas?.[code]; return !e || e.stops > 0 || ((e.buildings || 0) + (e.city_buildings || 0)) > 0; },
    async diveTo(code) { if (!land) return; selected = code; land.select(code); await dive(); },
    playing: () => !!timer,
  };
  window.Timelapse3D = {
    open() {
      if (land) { window.Product.go('map'); window.Product.setMapView('3d'); setMode('history'); return; }
      pendingTimelapse = true; location.hash = '#map/3d';
    },
  };
})();
