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
      <button type="button" class="solid-button dive-button" id="dive-button" hidden>${icon('arrow-down-right')} <span>Dive in</span></button>`;
    host.append(bar);
    const player = document.createElement('div');
    player.className = 'timelapse-player';
    player.hidden = true;
    player.innerHTML = `<div class="timelapse-date" aria-live="polite"><strong></strong><span></span></div>
      <div class="timelapse-row"><button type="button" class="icon-button" id="timelapse-play" aria-label="Pause">${icon('pause')}</button>
      <input type="range" id="timelapse-scrub" min="0" max="${Math.max(0, (h?.dates?.length || 1) - 1)}" value="0" aria-label="Listed day"></div>
      <div class="timelapse-years" aria-hidden="true"></div>
      <p class="timelapse-note">Each step is a day NEA's cluster list was saved (Internet Archive captures, then daily snapshots). Days in between were not captured and are not filled in.</p>`;
    host.append(player);
    bar.querySelectorAll('[data-mode3d]').forEach(b => b.onclick = () => setMode(b.dataset.mode3d));
    $('#dive-button', bar).onclick = dive;
    $('#timelapse-play', player).onclick = () => timer ? stop() : play();
    $('#timelapse-scrub', player).oninput = e => { stop(); show(Number(e.target.value), 250); };
    if (h?.dates?.length) {
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
    if (next === 'history') { index = 0; show(0, 600).then(() => play()); }
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
    $('.timelapse-date strong', player).textContent = day(date);
    $('.timelapse-date span', player).textContent = `${areas} ${areas === 1 ? 'area' : 'areas'} with clusters · ${total.toLocaleString('en-SG')} people (shared clusters counted per area) · ${h.sources?.[date] || ''}`;
    $('#timelapse-scrub', player).value = String(index);
    land.caption(`Height = people in active clusters on ${day(date)}`);
    return land.setPeople(peopleOn(date), ms);
  }

  function play() {
    if (reduced()) return;
    const button = $('#timelapse-play', host); button.innerHTML = icon('pause'); button.setAttribute('aria-label', 'Pause');
    const stepMs = 760;
    const tick = () => {
      const h = history(); if (mode !== 'history') return stop();
      if (index >= h.dates.length - 1) return stop();
      show(index + 1, stepMs * .8);
      timer = setTimeout(tick, stepMs);
    };
    clearTimeout(timer); timer = setTimeout(tick, stepMs);
  }

  function stop() {
    clearTimeout(timer); timer = 0;
    const button = host && $('#timelapse-play', host);
    if (button) { button.innerHTML = icon('play'); button.setAttribute('aria-label', 'Play'); }
  }

  function syncDive() {
    const button = host && $('#dive-button', host); if (!button) return;
    const area = api.state.areas.find(a => a.code === selected);
    const hasWalk = area && (data().inspection?.areas?.[area.code]?.stops?.length || true);
    button.hidden = !area || !hasWalk || mode === 'history';
    if (area) $('span', button).textContent = `Dive into ${area.name}`;
  }

  async function dive() {
    const area = api.state.areas.find(a => a.code === selected); if (!area) return;
    stop();
    host.classList.add('is-diving');
    await land.dive(area.code);
    window.RouteFlythrough.autoplay = true;  // the walk starts on arrival
    window.Product.go('plan', area.code);
    setTimeout(() => host.classList.remove('is-diving'), 600);
  }

  document.addEventListener('denguesux:ready', e => { api = e.detail.api; });
  document.addEventListener('denguesux:landscape', async e => {
    land = e.detail.landscape; host = e.detail.host; if (!land) return;
    controls(); await land.ready();
    if (selected) land.select(selected);
    syncDive();
    if (pendingTimelapse) { pendingTimelapse = false; setMode('history'); }
    if (pendingDive) { const code = pendingDive; pendingDive = null; selected = code; land.select(code); syncDive(); }
  });
  document.addEventListener('denguesux:area-detail', e => { selected = e.detail.area.code; land?.select(selected); syncDive(); });
  document.addEventListener('denguesux:route', e => { if (e.detail.view !== 'map') stop(); });
  window.Map3DExtras = {
    whenReady: () => new Promise(resolve => { const check = () => land ? land.ready().then(resolve) : setTimeout(check, 120); check(); }),
    setMode: next => land && setMode(next),
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
