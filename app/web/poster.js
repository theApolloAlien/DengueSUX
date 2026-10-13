/* A4 lift-lobby poster for one planning area, in four languages, with a QR code to the live field plan.
   Body text is the area's approved resident notice (allowlisted sentences); nothing is generated freely here. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const slug = name => String(name).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-$/, '');
  const HEAD = {
    en: ['Dengue is in our neighbourhood', 'Ten minutes this week can stop the next case.', 'Scan for the places to check near you'],
    zh: ['我们的社区出现骨痛热症', '这个星期花十分钟，就能阻止下一宗病例。', '扫描查看附近需要检查的地方'],
    ms: ['Denggi ada di kawasan kita', 'Sepuluh minit minggu ini boleh menghalang kes seterusnya.', 'Imbas untuk tempat yang perlu diperiksa'],
    ta: ['நம் சுற்றுவட்டாரத்தில் டெங்கி உள்ளது', 'இந்த வாரம் பத்து நிமிடங்கள் அடுத்த பாதிப்பைத் தடுக்கலாம்.', 'அருகில் சரிபார்க்க வேண்டிய இடங்களுக்கு ஸ்கேன் செய்யுங்கள்'],
  };
  const TELEGRAM = { en: 'Alerts on Telegram', zh: 'Telegram 提醒', ms: 'Amaran di Telegram', ta: 'Telegram எச்சரிக்கைகள்' };
  const ACTIONS = [['flower', 'Empty flowerpot plates'], ['paint-bucket', 'Turn over pails, wipe the rims'], ['house-line', 'Clear roof gutters'], ['drop', 'Change vase water'], ['plant', 'Loosen hardened soil']];
  let api = null, language = 'en';

  function qrSvg(text) {
    if (typeof window.qrcode !== 'function') return '';
    const qr = window.qrcode(0, 'M'); qr.addData(text); qr.make();
    return qr.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
  }

  function render(area) {
    const view = $('#poster-view'); if (!view) return;
    if (!area) { view.innerHTML = '<p class="poster-empty">Choose an area from the map to make a poster.</p>'; return; }
    const notice = api.state.data.notices?.notices?.[area.code]?.[language];
    const head = HEAD[language];
    const url = `${location.origin}/#plan/${slug(area.name)}`;
    const telegram = window.DengueTelegram?.username ? `https://t.me/${window.DengueTelegram.username}?start=${encodeURIComponent(area.code)}` : '';
    const date = new Date(api.state.data.current?.as_of).toLocaleDateString('en-SG', { day: 'numeric', month: 'long', year: 'numeric' });
    const short = new Date(api.state.data.current?.as_of).toLocaleDateString('en-SG', { day: 'numeric', month: 'short' });
    const sms = `${area.cluster_cases} in dengue clusters near ${area.name} (NEA ${short}). Empty pots and pails today. ${url}`;
    view.innerHTML = `<div class="poster-tools no-print"><a class="text-button" href="#map/${slug(area.name)}">← ${esc(area.name)}</a>
        <div class="segmented" role="group" aria-label="Poster language">${[['en', 'English'], ['zh', '中文'], ['ms', 'Melayu'], ['ta', 'தமிழ்']].map(([v, n]) => `<button type="button" data-poster-lang="${v}" class="${v === language ? 'active' : ''}" aria-pressed="${v === language}">${n}</button>`).join('')}</div>
        <button class="solid-button" id="poster-print"><i class="ph ph-printer" aria-hidden="true"></i> Print A4</button></div>
      <article class="poster-sheet" lang="${esc(language)}">
        <header><img src="/brand/logo-mark.svg" width="36" height="36" alt=""><span>${esc(area.name)} · ${esc(date)}</span></header>
        <h1>${esc(head[0])}</h1>
        <p class="poster-sub">${esc(head[1])}</p>
        <div class="poster-figure"><strong>${esc(area.cluster_cases)}</strong><span>${language === 'en' ? `${area.cluster_cases === 1 ? 'person' : 'people'} in active dengue clusters around ${esc(area.name)}` : esc(area.name)}</span></div>
        <ul class="poster-actions">${ACTIONS.map(([i, t]) => `<li><i class="ph ph-${i}" aria-hidden="true"></i><span>${esc(t)}</span></li>`).join('')}</ul>
        ${notice ? `<p class="poster-notice">${esc(notice.text)}</p>` : ''}
        <footer><div class="poster-qr" role="img" aria-label="QR code to the field plan for ${esc(area.name)}">${qrSvg(url)}</div><div><strong>${esc(head[2])}</strong><span>${esc(url.replace(/^https?:\/\//, ''))}</span>${telegram ? `<span class="poster-telegram"><i class="ph ph-telegram-logo" aria-hidden="true"></i> ${esc(TELEGRAM[language])}: ${esc(telegram.replace(/^https?:\/\//, ''))}</span>` : ''}<small>Feeling unwell with fever? See a doctor. Places to check are not confirmed breeding sites. Data: NEA via data.gov.sg. Draft notice: review before posting.</small></div>${telegram ? `<div class="poster-qr poster-qr-telegram" role="img" aria-label="QR code for Telegram alerts about ${esc(area.name)}">${qrSvg(telegram)}</div>` : ''}</footer>
      </article>
      <section class="poster-sms no-print"><h2>Short text for WhatsApp or SMS (${sms.length} characters)</h2><textarea readonly rows="3">${esc(sms)}</textarea><button class="outline-button" id="poster-copy"><i class="ph ph-copy" aria-hidden="true"></i> Copy text</button></section>`;
    view.querySelectorAll('[data-poster-lang]').forEach(b => b.onclick = () => { language = b.dataset.posterLang; render(area); });
    $('#poster-print', view).onclick = () => window.print();
    $('#poster-copy', view).onclick = async e => { try { await navigator.clipboard.writeText(sms); e.currentTarget.textContent = 'Copied'; } catch { $('textarea', view).select(); } };
  }

  function mount() {
    if ($('#poster-view')) return;
    const node = document.createElement('section');
    node.id = 'poster-view'; node.className = 'view-content poster-view'; node.hidden = true; node.setAttribute('aria-label', 'Printable poster');
    $('#main').insertBefore(node, $('footer'));
  }
  document.addEventListener('denguesux:ready', e => { api = e.detail.api; mount(); });
  document.addEventListener('denguesux:route', e => { document.body.classList.toggle('poster-mode', e.detail.view === 'poster'); if (e.detail.view === 'poster') { mount(); render(e.detail.area); } });
  document.addEventListener('denguesux:telegram', () => { if (document.body.classList.contains('poster-mode')) render(api?.state?.selected); });
  window.Poster = {qrSvg};
})();
