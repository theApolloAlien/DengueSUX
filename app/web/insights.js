/* Two-week area outlook, published-forecast track record, community checks, outreach context and alert feeds.
   Extends the existing views through the shell's events; reads only the published gold export and /api/reports. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = v => Number.isFinite(v) ? `${Math.round(v * 100)}%` : '—';
  const num = (v, d = 0) => Number.isFinite(Number(v)) ? Number(v).toLocaleString('en-SG', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—';
  const icon = n => `<i class="ph ph-${n}" aria-hidden="true"></i>`;
  const day = v => { const t = Date.parse(v); return Number.isFinite(t) ? new Date(t).toLocaleDateString('en-SG', { day: 'numeric', month: 'short' }) : '—'; };
  let api = null, community = null;

  const data = () => api?.state?.data || {};
  const outlook = () => data().area_forecast?.areas?.length ? data().area_forecast : null;
  const outlookFor = code => outlook()?.areas.find(a => a.code === code);
  const slug = name => String(name).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-$/, '');

  function bar(p, tone) {
    const width = Math.max(2, Math.round((p || 0) * 100));
    return `<span class="prob-bar ${tone}" role="img" aria-label="${pct(p)} chance"><b style="width:${width}%"></b></span>`;
  }

  function driverSentence(row) {
    const top = (row.drivers || []).slice(0, 2).map(d => `${d.group.toLowerCase()} ${d.direction} it`);
    return top.length ? top.join('; ') : 'No single driver stands out';
  }

  /* ---------- Home: insights row ---------- */
  function outlookCard() {
    const o = outlook();
    if (!o) return `<section class="insight-card"><h2>${icon('binoculars')} Two-week area outlook</h2><p class="insight-empty">The area outlook appears after the next pipeline run.</p></section>`;
    const rows = o.areas.filter(a => a.band !== 'Low' || a.p_any >= 0.25).slice(0, 5);
    const rising = o.areas.filter(a => a.band === 'High' && a.band_now !== 'High');
    const ev = o.evaluation || {}, m = ev.model || {}, p = ev.persistence || {};
    return `<section class="insight-card outlook-card" aria-labelledby="outlook-title">
      <header><h2 id="outlook-title">${icon('binoculars')} In about two weeks</h2><a href="#map/3d">3D map →</a></header>
      <p class="insight-lede">${rising.length ? `<strong>${rising.map(a => esc(a.name)).join(', ')}</strong> may become High.` : 'No area is expected to newly reach High.'} Chance of 10+ people in clusters:</p>
      <ol class="outlook-list">${rows.map(a => `<li><a href="#map/${slug(a.name)}"><span class="outlook-name">${esc(a.name)}<small>${esc(a.band_now)} now → ${esc(a.band)}</small></span>${bar(a.p_high, a.band.toLowerCase())}<b>${pct(a.p_high)}</b></a></li>`).join('')}</ol>
      <p class="insight-foot" title="${esc(o.method)}">Trained on ${num(o.training?.origin_dates)} archived NEA listings since ${esc((o.training?.first_origin || '').slice(0, 4))}. Brier ${num(m.brier_any, 3)} vs ${num(p.brier_any, 3)} for “stays the same”. Chances, not certainties.</p>
    </section>`;
  }

  function ledgerCard() {
    const l = data().ledger;
    const rows = (l?.national || []).slice(-3);
    if (!rows.length) return `<section class="insight-card"><h2>${icon('notebook')} What we said</h2><p class="insight-empty">Published forecasts are recorded here as soon as the first one is issued.</p></section>`;
    const scored = rows.filter(r => r.actual != null);
    return `<section class="insight-card ledger-card" aria-labelledby="ledger-title">
      <header><h2 id="ledger-title">${icon('notebook')} What we said, what happened</h2><a href="#forecast">Forecast →</a></header>
      <table class="ledger-table"><thead><tr><th scope="col">Week</th><th scope="col">We said</th><th scope="col">Reported</th></tr></thead><tbody>
      ${rows.map(r => `<tr><td>${esc(r.target.replace('-W', ' W'))}<small>${day(r.issued_for)}</small></td><td>${num(r.prediction)}<small>${num(r.lower)}–${num(r.upper)}</small></td><td>${r.actual == null ? '<span class="pending">Awaiting report</span>' : `${num(r.actual)} <span class="${r.covered ? 'hit' : 'miss'}">${r.covered ? 'in range' : 'outside'}</span>`}</td></tr>`).join('')}
      </tbody></table>
      <p class="insight-foot">Append-only ledger since ${day(l.first_published)}; predictions are never edited.${scored.length ? '' : ' Outcomes fill in as CDA publishes each week.'}${l.area_scored ? ` Area outlooks scored: ${num(l.area_scored)} (${pct(l.area_band_accuracy)} band accuracy).` : ''}</p>
    </section>`;
  }

  function communityCard() {
    const c = community;
    const week = c?.this_week;
    return `<section class="insight-card community-card" aria-labelledby="community-title">
      <header><h2 id="community-title">${icon('hand-heart')} Checked this week</h2><a href="#plan">Field plans →</a></header>
      ${c ? `<div class="community-stats"><div><strong data-count="${week?.stops_checked || 0}">${num(week?.stops_checked || 0)}</strong><small>stops checked</small></div><div><strong>${num(week?.water_found || 0)}</strong><small>with water found</small></div><div><strong>${num(c.stops_checked)}</strong><small>stops all time</small></div></div>
      <p class="insight-foot">${week?.water_found ? 'Stops with water are re-checked first in tomorrow’s plans.' : 'Every report lands in a Unity Catalog table and shapes the next plan.'} Self-reports, not confirmed breeding sites.</p>`
      : '<p class="insight-empty">Field reports are unavailable right now.</p>'}
    </section>`;
  }

  function mountHome() {
    const grid = $('.chat-home .week-grid');
    if (!grid || $('#home-insights')) return;
    const block = document.createElement('section');
    block.id = 'home-insights';
    block.className = 'home-insights-block';
    block.setAttribute('aria-label', 'Outlook, track record and community checks');
    const row = document.createElement('div');
    row.className = 'home-insights';
    row.innerHTML = outlookCard() + ledgerCard() + communityCard();
    block.append(row);
    grid.after(block);
    const history = data().area_history;
    if (history?.dates?.length > 2) {
      const play = document.createElement('button');
      play.className = 'outline-button timelapse-launch';
      play.innerHTML = `${icon('play-circle')} Replay ${history.dates[0].slice(0, 4)}–${history.dates.at(-1).slice(0, 4)} in 3D`;
      play.onclick = () => window.Timelapse3D?.open();
      const story = document.createElement('button');
      story.className = 'solid-button timelapse-launch';
      story.innerHTML = `${icon('presentation-chart')} Play the 2-minute story`;
      story.onclick = () => window.Story?.play();
      const actions = document.createElement('div');
      actions.className = 'home-launchers';
      actions.append(story, play);
      block.append(actions);  // inside the block, so a two-column chat layout never strands the buttons
    }
  }

  function refreshCommunity() {
    const card = $('#home-insights .community-card');
    if (card) card.outerHTML = communityCard();
  }

  async function loadCommunity() {
    try {
      const response = await fetch('/api/reports', { cache: 'no-store' });
      if (!response.ok) throw new Error(response.status);
      community = await response.json();
    } catch { community = null; }
    refreshCommunity();
  }

  /* ---------- Map: area detail additions ---------- */
  function areaDetail({ area, node }) {
    if (!node || node.querySelector('.area-outlook')) return;
    const o = outlookFor(area.code);
    const pieces = [];
    if (o) {
      pieces.push(`<section class="area-outlook" aria-label="Two-week outlook"><h4>${icon('binoculars')} In about two weeks</h4>
        <div class="outlook-pair"><div><span>Any cluster</span>${bar(o.p_any, 'medium')}<b>${pct(o.p_any)}</b></div><div><span>10+ people</span>${bar(o.p_high, 'high')}<b>${pct(o.p_high)}</b></div></div>
        <p>Most likely <span class="badge ${o.band.toLowerCase()}">${esc(o.band)}</span> · ${esc(driverSentence(o))}.</p></section>`);
    }
    if (Number.isFinite(area.elderly_share)) {
      const small = Number.isFinite(area.small_flat_share) ? ` and ${pct(area.small_flat_share)} live in 1- or 2-room flats` : '';
      const wide = area.elderly_share >= 0.22 || (area.small_flat_share || 0) >= 0.08;
      pieces.push(`<p class="outreach-note">${icon('users-three')} <span><strong>${pct(area.elderly_share)}</strong> of residents are 65 or older${small}.${wide ? ' Plan printed notices and offer help emptying containers.' : ''}<small>SingStat June 2026 · for outreach, not risk</small></span></p>`);
    }
    const reports = community?.by_area?.[area.code];
    if (reports) pieces.push(`<p class="outreach-note">${icon('check-circle')} <span><strong>${num(reports.stops_checked)}</strong> stops checked here${reports.water_found ? `, ${num(reports.water_found)} with water found` : ''}.<small>Last report ${day(reports.last_reported_at)}</small></span></p>`);
    const feed = `/feeds/alerts.xml?area=${encodeURIComponent(area.code)}`;
    const share = `DengueSUX: ${area.name} has ${area.cluster_cases} people in active dengue clusters. Check for stagnant water today. ${location.origin}/#plan/${slug(area.name)}`;
    pieces.push(`<div class="follow-row">${telegramLink(area)}<a class="text-button" href="${feed}" title="Atom feed: follow in any feed reader or chat bot. We store no contact details.">${icon('rss')} Follow alerts</a><a class="text-button" href="https://wa.me/?text=${encodeURIComponent(share)}" target="_blank" rel="noopener">${icon('whatsapp-logo')} Share</a><a class="text-button" href="#poster/${slug(area.name)}">${icon('printer')} Lift poster</a></div>`);
    node.insertAdjacentHTML('beforeend', pieces.join(''));
  }

  /* ---------- Forecast: track record and benchmark ---------- */
  function forecastExtras() {
    const view = $('#forecast-view');
    if (!view || $('#forecast-record')) return;
    const l = data().ledger, b = data().pipeline_status?.benchmark, s = data().model?.prospective?.scoring;
    const blocks = [];
    if (l?.national?.length) {
      blocks.push(`<section class="record-block"><h3>${icon('notebook')} Forecasts as published</h3><table class="ledger-table wide"><thead><tr><th scope="col">Target week</th><th scope="col">Published</th><th scope="col">Forecast</th><th scope="col">80% range</th><th scope="col">Reported</th></tr></thead><tbody>${l.national.map(r => `<tr><td>${esc(r.target)}</td><td>${day(r.published_at)}</td><td>${num(r.prediction)}</td><td>${num(r.lower)}–${num(r.upper)}</td><td>${r.actual == null ? '<span class="pending">Awaiting</span>' : `${num(r.actual)} <span class="${r.covered ? 'hit' : 'miss'}">${r.covered ? 'in range' : 'outside'}</span>`}</td></tr>`).join('')}</tbody></table><p class="insight-foot">Every forecast is written once to an append-only Delta table (Change Data Feed on) and scored when the official count arrives.</p></section>`);
    }
    if (b && Number.isFinite(b.ai_forecast_mae)) {
      const max = Math.max(b.ai_forecast_mae, b.denguesux_mae, b.four_week_average_mae);
      const row = (label, v, tone) => `<div class="bench-row"><span>${label}</span><span class="bench-bar ${tone}"><b style="width:${Math.max(3, v / max * 100)}%"></b></span><strong>${num(v, 1)}</strong></div>`;
      blocks.push(`<section class="record-block"><h3>${icon('scales')} Two weeks ahead, ${num(b.weeks)} weeks since 2025</h3><p class="insight-lede">Average error in people a week. Each forecaster saw only the weeks before its forecast.</p>${row('DengueSUX model', b.denguesux_mae, 'good')}${row('Four-week average', b.four_week_average_mae, 'neutral')}${row('Databricks ai_forecast', b.ai_forecast_mae, 'warn')}<p class="insight-foot">One SQL query with <code>ai_forecast</code> grouped by origin week. 80% range coverage: DengueSUX ${pct(b.denguesux_coverage)}, ai_forecast ${pct(b.ai_forecast_coverage)}.</p></section>`);
    }
    if (s) {
      const dm = s.diebold_mariano?.vs_four_week_average;
      blocks.push(`<section class="record-block"><h3>${icon('target')} Honest scoring since 2023</h3><dl class="score-grid"><div><dt>80% range coverage</dt><dd>${pct(s.adaptive?.coverage)}<small>adaptive (was ${pct(s.fixed?.coverage)} fixed)</small></dd></div><div><dt>Interval score</dt><dd>${num(s.adaptive?.interval_score, 0)}<small>fixed ${num(s.fixed?.interval_score, 0)} · lower is better</small></dd></div><div><dt>vs four-week average</dt><dd>${dm ? `p = ${num(dm.p_value, 2)}` : '—'}<small>${dm && dm.p_value > 0.05 ? 'difference could be chance' : 'Diebold–Mariano test'}</small></dd></div><div><dt>Error, people a week</dt><dd>${num(s.mae?.selected, 0)}<small>four-week average ${num(s.mae?.four_week_average, 0)} · same week last year ${num(s.mae?.seasonal_naive, 0)}</small></dd></div></dl></section>`);
    }
    if (!blocks.length) return;
    const wrap = document.createElement('div');
    wrap.id = 'forecast-record';
    wrap.className = 'forecast-record';
    wrap.innerHTML = blocks.join('');
    const anchor = $('#live-outlook');
    if (anchor) anchor.after(wrap); else view.prepend(wrap);
  }

  /* ---------- Telegram alerts: a deep link per area; the bot stores only the chat id and area ---------- */
  function telegramLink(area, cls = 'text-button') {
    const tg = window.DengueTelegram;
    if (!tg?.username || !area) return '';
    return `<a class="${cls} telegram-link" href="https://t.me/${esc(tg.username)}?start=${encodeURIComponent(area.code)}" target="_blank" rel="noopener" title="Telegram: a message on days ${esc(area.name)} is High, has a new cluster or is forecast High. Only your chat id and the area are stored; /stop deletes them.">${icon('telegram-logo')} Telegram alerts</a>`;
  }
  function loadTelegram() {
    fetch('/api/telegram/status', { signal: AbortSignal.timeout(8000) }).then(r => r.ok ? r.json() : null).then(t => {
      window.DengueTelegram = t?.available ? t : null;
      const row = document.querySelector('.follow-row');
      const area = row && api?.state?.selected;  // detail already open: add the link in place
      if (row && area && !row.querySelector('.telegram-link')) row.insertAdjacentHTML('afterbegin', telegramLink(area));
      document.dispatchEvent(new CustomEvent('denguesux:telegram', { detail: window.DengueTelegram }));
    }).catch(() => { window.DengueTelegram = null; });
  }

  document.addEventListener('denguesux:ready', e => {
    api = e.detail.api;
    window.DengueData = api.state.data;  // read-only handle for the 3D walk's Aedes and outlook layers
    loadTelegram();
    mountHome();
    forecastExtras();
    loadCommunity();
  });
  document.addEventListener('denguesux:route', e => { if (e.detail.view === 'week') requestAnimationFrame(mountHome); });
  document.addEventListener('denguesux:area-detail', e => areaDetail(e.detail));
  window.Insights = { outlook, outlookFor, community: () => community, reload: loadCommunity };
})();
