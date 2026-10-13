/* Story mode: a captioned, about-two-minute walk through the product for a live demo. Start with ?story=1,
   the Help menu, or the home button. Esc stops; → skips ahead. Every step uses the real views and data. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  let api = null, running = false, skip = null, stepIndex = 0;

  const slug = name => String(name).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-$/, '');
  const top = () => api.state.areas[0];

  function steps() {
    const c = api.state.data.current?.totals || {}, o = api.state.data.area_forecast, l = api.state.data.ledger, h = api.state.data.area_history;
    const live = api.liveForecast()?.headline, b = api.state.data.pipeline_status?.benchmark;
    const t = top();
    return [
      { title: 'This week in Singapore', text: `${c.clusters ?? '—'} active dengue clusters, ${c.cluster_cases ?? '—'} people in them${live ? `, and about ${Math.round(live.prediction)} new cases expected nationally next week` : ''}. All from NEA, MOH and URA open data, refreshed daily on Databricks.`,
        run: async () => { window.Product.go('week'); await wait(5200); } },
      { title: 'Seven years, area by area', text: h?.dates?.length ? `data.gov.sg keeps no cluster history, so we rebuilt it: ${h.dates.length} archived NEA listings since ${h.dates[0].slice(0, 4)}, placed block by block.` : 'Every saved cluster snapshot, replayed by planning area.',
        run: async () => { location.hash = '#map/3d'; await window.Map3DExtras.whenReady(); if (reduced()) { window.Map3DExtras.setMode('history'); await wait(4000); } else await window.Map3DExtras.runTimelapse({speed: 4, maxMs: 26000}); } },
      { title: 'In about two weeks', text: o ? `A two-week outlook for every planning area, trained on ${o.training?.examples?.toLocaleString('en-SG')} area examples. Height is the chance of 10 or more people in clusters — chances, not certainties.` : 'The two-week area outlook.',
        run: async () => { window.Map3DExtras.setMode('outlook'); await wait(6500); window.Map3DExtras.setMode('now'); await wait(1600); } },
      { title: `From the island to a doorstep in ${t?.name || 'one area'}`, text: 'Dive from the national picture into one area, then walk its route on official HDB block shapes, the rest of the neighbourhood in grey, with what to check at each stop.',
        run: async () => { if (t) { await window.Map3DExtras.diveTo(t.code); } await wait(700); document.querySelector('.inspection-map-column')?.scrollIntoView({ behavior: reduced() ? 'instant' : 'smooth', block: 'start' });
          // Let the whole walk play at double speed so the story reaches "Route complete" instead of cutting it off.
          if (reduced()) await wait(5000); else { await wait(1500); window.RouteFlythrough?.setSpeed(2); await window.RouteFlythrough?.whenDone(95000); await wait(1800); } } },
      { title: 'A notice residents will read', text: 'A lift-lobby poster in English, Chinese, Malay and Tamil, with a QR code back to the live plan.',
        run: async () => { if (t) window.Product.go('poster', t.code); await wait(6000); } },
      { title: 'What we said, what happened', text: l?.national?.length ? `Every forecast is written once to an append-only Delta table and scored when CDA publishes. First entry: ${new Date(l.first_published).toLocaleDateString('en-SG', { day: 'numeric', month: 'short' })}.` : 'An append-only ledger of every published forecast.',
        run: async () => { window.Product.go('forecast'); await wait(1200); $('#forecast-record')?.scrollIntoView({ behavior: reduced() ? 'instant' : 'smooth', block: 'center' }); await wait(5800); } },
      { title: 'How it runs', text: `Auto Loader, a Lakeflow pipeline with expectations, Unity Catalog models scored in Spark${b ? `, and a one-query benchmark where the model beat ai_forecast ${Math.round(b.ai_forecast_mae)} to ${Math.round(b.denguesux_mae)}` : ''}. Genie, alerts and this app sit on the same gold tables.`,
        run: async () => { window.Product.go('platform'); await wait(7500); } },
      { title: 'Ask anything', text: 'Ask in four languages. Answers call real tools and Genie, cite dated sources, and are checked against the data before you see them.',
        run: async () => { window.Product.go('week'); await wait(900); const input = $('#ask-input') || $('textarea'); input?.focus(); await wait(4200); } },
    ];
  }

  function overlay() {
    let node = $('#story-overlay');
    if (node) return node;
    node = document.createElement('div');
    node.id = 'story-overlay'; node.className = 'story-overlay'; node.setAttribute('role', 'region'); node.setAttribute('aria-label', 'Story mode');
    node.innerHTML = `<div class="story-card"><div class="story-progress" aria-hidden="true"></div><p class="story-count"></p><h2 class="story-title" aria-live="polite"></h2><p class="story-text"></p>
      <div class="story-actions"><button type="button" class="text-button" id="story-stop">Stop</button><button type="button" class="outline-button" id="story-next">Next →</button></div></div>`;
    document.body.append(node);
    $('#story-stop', node).onclick = stop;
    $('#story-next', node).onclick = () => skip?.();
    return node;
  }

  async function play(from = 0) {
    if (running || !api) return;
    running = true; document.body.classList.add('story-running');
    try { localStorage.setItem('denguesux:toured', 'true'); } catch {}
    document.querySelector('#tour-dialog[open]')?.close();
    const list = steps(), node = overlay(); node.hidden = false;
    $('.story-progress', node).innerHTML = list.map(() => '<span></span>').join('');
    for (stepIndex = from; stepIndex < list.length && running; stepIndex++) {
      const step = list[stepIndex];
      $('.story-count', node).textContent = `${stepIndex + 1} of ${list.length}`;
      $('.story-title', node).textContent = step.title;
      $('.story-text', node).textContent = step.text;
      node.querySelectorAll('.story-progress span').forEach((s, i) => s.className = i < stepIndex ? 'done' : i === stepIndex ? 'now' : '');
      await Promise.race([step.run().catch(() => {}), new Promise(r => { skip = r; })]);
    }
    stop();
  }

  function stop() {
    running = false; skip = null;
    const node = $('#story-overlay'); if (node) node.hidden = true;
    document.body.classList.remove('story-running');
  }

  document.addEventListener('keydown', e => {
    if (!running) return;
    if (e.key === 'Escape') { e.preventDefault(); stop(); }
    if (e.key === 'ArrowRight' && !e.target.closest('input,textarea,select')) { e.preventDefault(); skip?.(); }
  });
  document.addEventListener('denguesux:ready', e => {
    api = e.detail.api;
    const menu = $('.help-menu > div');
    if (menu && !$('#story-open')) { const b = document.createElement('button'); b.id = 'story-open'; b.textContent = 'Play the story (2 min)'; b.onclick = () => { $('.help-menu').open = false; play(); }; menu.prepend(b); }
    const params = new URLSearchParams(location.search);
    if (params.get('story') === '1') setTimeout(() => play(), 900);
    // ?kiosk=1: no chrome, large captions, the story on a loop, and a QR code so a visitor can continue on a phone.
    if (params.get('kiosk') === '1') {
      document.body.classList.add('kiosk');
      const url = location.origin + location.pathname;
      const loop = async () => { if (!document.body.classList.contains('kiosk')) return; await play(); await wait(3500); loop(); };
      setTimeout(loop, 600);
      document.addEventListener('keydown', e => { if (e.key === 'Escape' && document.body.classList.contains('kiosk')) { document.body.classList.remove('kiosk'); stop(); } });
      const badge = document.createElement('div'); badge.className = 'kiosk-badge'; badge.innerHTML = `<strong>DengueSUX</strong><span>Open on your phone</span>${window.Poster?.qrSvg ? window.Poster.qrSvg(url) : ''}<small>${esc(url.replace(/^https?:\/\//, ''))}</small>`;
      document.body.append(badge);
    }
  });
  window.Story = { play, stop, running: () => running };
})();
