/* "How it runs": the Databricks pipeline behind every number, read from the platform status the jobs publish. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (v, d = 0) => Number.isFinite(Number(v)) ? Number(v).toLocaleString('en-SG', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—';
  const pct = v => Number.isFinite(Number(v)) ? `${Math.round(Number(v) * 100)}%` : '—';
  const icon = n => `<i class="ph ph-${n}" aria-hidden="true"></i>`;
  const ago = v => { const t = Date.parse(v); if (!Number.isFinite(t)) return '—'; const h = (Date.now() - t) / 36e5; return h < 1 ? 'under an hour ago' : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} days ago`; };
  const FALLBACK = [
    { stage: 'Bronze', tables: ['bronze_live_clusters', 'bronze_live_weather', 'bronze_moh_weekly'], how: 'Auto Loader appends immutable API envelopes with checksums.' },
    { stage: 'Silver', tables: ['silver_cluster_snapshots', 'silver_live_weather_daily', 'silver_area_cluster_history'], how: 'Lakeflow Declarative Pipeline with expectations.' },
    { stage: 'Gold', tables: ['gold_national_scores', 'gold_area_forecast', 'gold_forecast_ledger'], how: 'Registered models scored in Spark; append-only ledger.' },
    { stage: 'Serve', tables: ['Databricks App', 'Genie space', 'AI/BI dashboard', 'SQL alerts'], how: 'The app reads the gold export every minute.' },
  ];
  const CRON = { '0 15 8 * * ?': 'Daily 08:15', '0 30 10 ? * TUE,FRI': 'Tue & Fri 10:30' };
  let api = null, mounted = false;

  function tableChip(fact) {
    if (!fact || fact.available === false) return '';
    const chips = [fact.change_data_feed ? 'CDF' : '', ...(fact.clustering || []).length ? ['clustered'] : [], ...(fact.constraints || []).map(() => '')].filter(Boolean);
    const constraints = (fact.constraints || []).length;
    if (fact.version == null) return `<span class="table-meta">${num(fact.rows)} rows · ${esc(fact.kind || '')}</span>`;
    return `<span class="table-meta">v${num(fact.version)} · ${num(fact.rows)} rows${constraints ? ` · ${constraints} check${constraints > 1 ? 's' : ''}` : ''}${chips.length ? ' · ' + chips.join(' · ') : ''}</span>`;
  }

  function lineage(status) {
    const facts = Object.fromEntries((status?.tables || []).map(t => [t.table, t]));
    return `<div class="lineage-flow" role="list">${(status?.lineage || FALLBACK).map((stage, i) => `
      <section class="lineage-stage stage-${stage.stage.toLowerCase()}" role="listitem">
        <h3><span>${i + 1}</span>${esc(stage.stage)}</h3>
        <p>${esc(stage.how)}</p>
        <ul>${stage.tables.map(t => `<li><code>${esc(t)}</code>${tableChip(facts[t])}</li>`).join('')}</ul>
      </section>${i < 3 ? `<span class="lineage-arrow" aria-hidden="true">${icon('arrow-right')}</span>` : ''}`).join('')}</div>`;
  }

  function jobs(status) {
    const list = status?.jobs || [];
    if (!list.length) return '';
    return `<section class="platform-card"><h3>${icon('clock-clockwise')} Scheduled jobs (serverless)</h3>${list.map(job => `
      <div class="job-row"><div><strong>${esc(job.name.replace('DengueSUX ', ''))}</strong><small>${esc(CRON[job.schedule] || job.schedule || 'On demand')}</small></div>
      <div class="run-dots" aria-label="Last runs">${(job.runs || []).slice().reverse().map(r => `<span class="run-dot ${String(r.result || '').toLowerCase()}" title="${esc(r.result || 'running')} · ${esc(ago(r.started_at))} · ${num(r.minutes, 1)} min"></span>`).join('')}</div>
      <small>${job.runs?.[0] ? `${esc(String(job.runs[0].result || '').toLowerCase())} ${esc(ago(job.runs[0].started_at))}` : 'no runs yet'}</small></div>`).join('')}</section>`;
  }

  function quality(status) {
    const p = status?.pipeline;
    if (!p?.available) return '';
    const rows = p.expectations || [];
    return `<section class="platform-card"><h3>${icon('shield-check')} Data-quality expectations</h3><p class="platform-note">Lakeflow pipeline <strong>${esc(p.state || '')}</strong> · rows breaking a rule are dropped and counted, or stop the update.</p>
      <table class="mini-table"><thead><tr><th scope="col">Table</th><th scope="col">Rule</th><th scope="col">Passed</th><th scope="col">Failed</th></tr></thead><tbody>
      ${rows.map(e => `<tr><td>${esc(e.dataset)}</td><td>${esc(String(e.name).replace(/_/g, ' '))}</td><td>${num(e.passed)}</td><td class="${e.failed ? 'warn' : ''}">${num(e.failed)}</td></tr>`).join('') || '<tr><td colspan="4">Expectation metrics appear after the first pipeline update.</td></tr>'}</tbody></table></section>`;
  }

  function model(status, local) {
    const m = status?.model;
    const registry = local?.registry;
    const versions = m?.versions || [];
    const scoring = registry?.spark_scoring;
    return `<section class="platform-card"><h3>${icon('git-branch')} Registered forecast model</h3>
      <p class="platform-note"><code>${esc(m?.name || registry?.name || 'national_forecast')}</code> in ${esc(m?.registry || (registry?.registry === 'unity_catalog' ? 'Unity Catalog' : 'the MLflow registry'))}</p>
      <div class="model-versions">${versions.length ? versions.map(v => `<div class="model-version ${esc(v.alias)}"><span>@${esc(v.alias)}</span><strong>v${esc(v.version)}</strong><small>${esc(v.tags?.feature_set === 'no_weather' ? 'without weather' : 'with weather')}${v.tags?.prospective_mae ? ` · error ${esc(v.tags.prospective_mae)}` : ''}</small></div>`).join('')
        : registry?.versions ? Object.entries(registry.versions).map(([alias, v]) => `<div class="model-version ${esc(alias)}"><span>@${esc(alias)}</span><strong>v${esc(v)}</strong></div>`).join('') : '<p class="platform-note">Versions appear after the gold stage registers the model.</p>'}</div>
      ${scoring?.status === 'scored' ? `<p class="platform-note">Scored in Spark from <code>${esc(scoring.uri)}</code> into <code>gold_national_scores</code>, so lineage runs feature table → model → scores.</p>` : ''}
      <p class="platform-note">MLflow run <code>${esc((local?.run_id || '').slice(0, 8))}</code> · selection locked on 2019–2021 folds.</p></section>`;
  }

  function bench(status) {
    const b = status?.benchmark;
    if (!b || !Number.isFinite(Number(b.ai_forecast_mae))) return '';
    return `<section class="platform-card"><h3>${icon('scales')} One-query benchmark with ai_forecast</h3><p class="platform-note">${num(b.weeks)} weeks from ${esc(String(b.first_week).slice(0, 10))}, two weeks ahead, each fitted only on earlier weeks.</p>
      <dl class="bench-dl"><div><dt>DengueSUX</dt><dd>${num(b.denguesux_mae, 1)}</dd></div><div><dt>Four-week average</dt><dd>${num(b.four_week_average_mae, 1)}</dd></div><div><dt>ai_forecast</dt><dd>${num(b.ai_forecast_mae, 1)}</dd></div></dl><p class="platform-note">Mean absolute error, people a week.</p></section>`;
  }

  function links(status) {
    const l = status?.links || {};
    if (!l.dashboard && !l.genie) return '';
    return `<div class="platform-links">${l.dashboard ? `<a class="outline-button" href="${esc(l.dashboard)}" target="_blank" rel="noopener">${icon('chart-bar')} Open the AI/BI dashboard</a>` : ''}${l.genie ? `<a class="outline-button" href="${esc(l.genie)}" target="_blank" rel="noopener">${icon('database')} Open the Genie space</a>` : ''}<small>Workspace sign-in required.</small></div>`;
  }

  function services() {
    const items = [
      ['chat-circle-dots', 'Ask DengueSUX', 'Llama 3.3 70B on the Foundation Model API with nine tools; every answer is traced in MLflow and checked against tool results.'],
      ['database', 'Genie space', 'Natural-language SQL over 11 gold tables, with join rules, examples and 18 benchmark questions.'],
      ['bell-ringing', 'SQL alerts', 'New High areas, predicted hotspots, stale labels and missed snapshots email the operator.'],
      ['chart-bar', 'AI/BI dashboard', 'Operations view for NEA and town councils: outlook, track record and field outcomes.'],
      ['lock-key', 'Unity Catalog', 'Tags, column comments, check constraints and scoped grants for the app’s service principal.'],
      ['rss', 'Alert feeds', 'Per-area Atom feeds anyone can follow without giving contact details.'],
    ];
    return `<section class="platform-card services"><h3>${icon('stack')} What serves the answers</h3><ul>${items.map(([i, t, d]) => `<li>${icon(i)}<div><strong>${t}</strong><p>${d}</p></div></li>`).join('')}</ul></section>`;
  }

  function render() {
    const data = api?.state?.data || {};
    const status = data.pipeline_status?.available ? data.pipeline_status : null;
    const view = $('#platform-view');
    view.innerHTML = `<div class="platform-intro"><p>Every number in DengueSUX comes from this pipeline. ${status ? `Status read from the workspace ${esc(ago(status.generated_at))}.` : 'Live job and table status appears when the app runs on Databricks.'}</p></div>
      ${links(status)}
      ${lineage(status)}
      <div class="platform-grid">${jobs(status)}${quality(status)}${model(status, data.model)}${bench(status)}${services()}</div>`;
  }

  function mount() {
    if (mounted) return;
    const node = document.createElement('section');
    node.id = 'platform-view';
    node.className = 'view-content platform-view';
    node.hidden = true;
    node.setAttribute('aria-label', 'How DengueSUX runs on Databricks');
    $('#main').insertBefore(node, $('footer'));
    mounted = true;
  }

  document.addEventListener('denguesux:ready', e => { api = e.detail.api; mount(); });
  document.addEventListener('denguesux:route', e => { if (e.detail.view === 'platform') { mount(); render(); } });
})();
