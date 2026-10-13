/* Interface language (English, 中文, Bahasa Melayu, தமிழ்). Elements carry data-i18n="key"; modules can call I18N.t(key).
   Translations were drafted by the team and marked for native-speaker review; data values and place names stay as published. */
(() => {
  'use strict';
  const S = {
    'nav.week': ['This week', '本周', 'Minggu ini', 'இந்த வாரம்'],
    'nav.map': ['Map', '地图', 'Peta', 'வரைபடம்'],
    'nav.plan': ['Field plan', '实地计划', 'Pelan lapangan', 'கள திட்டம்'],
    'nav.forecast': ['Forecast', '预测', 'Ramalan', 'முன்னறிவிப்பு'],
    'nav.platform': ['How it runs', '运作方式', 'Cara ia berjalan', 'இது எப்படி இயங்குகிறது'],
    'nav.find': ['Find anything', '搜索', 'Cari apa-apa', 'எதையும் தேடுங்கள்'],
    'nav.help': ['Help', '帮助', 'Bantuan', 'உதவி'],
    'nav.collapse': ['Collapse', '收起', 'Kecilkan', 'சுருக்கு'],
    'nav.export': ['Export data', '导出数据', 'Eksport data', 'தரவை ஏற்றுமதி'],
    'nav.ask': ['Ask DengueSUX', '询问 DengueSUX', 'Tanya DengueSUX', 'DengueSUX-இடம் கேளுங்கள்'],
    'nav.note': ['Singapore · Open data', '新加坡 · 开放数据', 'Singapura · Data terbuka', 'சிங்கப்பூர் · திறந்த தரவு'],
    'hero.explore': ['Explore the 3D map', '浏览 3D 地图', 'Terokai peta 3D', '3D வரைபடத்தைப் பாருங்கள்'],
    'hero.clusters': ['active clusters', '活跃感染群', 'kluster aktif', 'செயலில் உள்ள கொத்துகள்'],
    'hero.people': ['people in clusters', '感染群中的人数', 'orang dalam kluster', 'கொத்துகளில் உள்ளவர்கள்'],
    'hero.areas': ['areas affected', '受影响地区', 'kawasan terjejas', 'பாதிக்கப்பட்ட பகுதிகள்'],
    'hero.morning': ['Good morning.', '早上好。', 'Selamat pagi.', 'காலை வணக்கம்.'],
    'hero.afternoon': ['Good afternoon.', '下午好。', 'Selamat petang.', 'மதிய வணக்கம்.'],
    'hero.evening': ['Good evening.', '晚上好。', 'Selamat malam.', 'மாலை வணக்கம்.'],
    'home.national': ['Expected nationally', '全国预计', 'Dijangka di seluruh negara', 'தேசிய அளவில் எதிர்பார்க்கப்படுவது'],
    'home.first': ['Where to check first', '优先检查地点', 'Di mana perlu periksa dahulu', 'முதலில் எங்கு சரிபார்க்க வேண்டும்'],
    'home.activity': ['Recent activity', '最新动态', 'Aktiviti terkini', 'சமீபத்திய நடவடிக்கை'],
    'home.outlook': ['In about two weeks', '约两周后', 'Dalam kira-kira dua minggu', 'சுமார் இரண்டு வாரங்களில்'],
    'home.ledger': ['What we said, what happened', '我们的预测与实际', 'Apa yang kami kata, apa yang berlaku', 'நாங்கள் சொன்னது, நடந்தது'],
    'home.checked': ['Checked this week', '本周已检查', 'Diperiksa minggu ini', 'இந்த வாரம் சரிபார்க்கப்பட்டது'],
    'home.forecast': ['See forecast', '查看预测', 'Lihat ramalan', 'முன்னறிவிப்பைப் பார்க்க'],
    'home.allAreas': ['All {0} areas →', '全部 {0} 个地区 →', 'Semua {0} kawasan →', 'அனைத்து {0} பகுதிகள் →'],
    'plan.stops': ['{0} stops to check', '{0} 个检查点', '{0} hentian untuk diperiksa', '{0} சரிபார்க்க வேண்டிய இடங்கள்'],
    'plan.places': ['{0} places to check', '{0} 个检查地点', '{0} tempat untuk diperiksa', '{0} சரிபார்க்க வேண்டிய இடங்கள்'],
    'plan.notice': ['Resident notice', '居民通告', 'Notis penduduk', 'குடியிருப்பாளர் அறிவிப்பு'],
    'plan.copy': ['Copy link', '复制链接', 'Salin pautan', 'இணைப்பை நகலெடு'],
    'plan.print': ['Print sheet', '打印表格', 'Cetak helaian', 'தாளை அச்சிடு'],
    'plan.2d': ['2D map', '2D 地图', 'Peta 2D', '2D வரைபடம்'],
    'plan.3d': ['3D walk preview', '3D 步行预览', 'Pratonton jalan 3D', '3D நடைப் பார்வை'],
    'plan.full': ['Full screen', '全屏', 'Skrin penuh', 'முழுத் திரை'],
    'plan.walk': ['Walk the route', '沿路线步行', 'Jalan ikut laluan', 'பாதையில் நடக்க'],
    'plan.whole': ['Whole route', '整条路线', 'Seluruh laluan', 'முழு பாதை'],
    'plan.done': ['Done', '完成', 'Selesai', 'முடிந்தது'],
    'plan.report': ['Report', '报告', 'Lapor', 'அறிக்கை'],
    'plan.why': ['Why', '原因', 'Mengapa', 'ஏன்'],
    'plan.map': ['Map', '地图', 'Peta', 'வரைபடம்'],
    'plan.checklist': ['Checklist', '检查清单', 'Senarai semak', 'சரிபார்ப்புப் பட்டியல்'],
    'plan.atEachStop': ['At each stop', '每个检查点', 'Di setiap hentian', 'ஒவ்வொரு இடத்திலும்'],
    'plan.field': ['Field mode', '实地模式', 'Mod lapangan', 'கள முறை'],
    'plan.claim': ['Claim this walk', '认领此路线', 'Tuntut laluan ini', 'இந்த நடையை ஏற்கவும்'],
    'plan.release': ['Release', '取消认领', 'Lepaskan', 'விடுவி'],
    'plan.claimedBy': ['Claimed by {0} this week', '本周由 {0} 认领', 'Dituntut oleh {0} minggu ini', 'இந்த வாரம் {0} ஏற்றுள்ளார்'],
    'plan.myWalks': ['My walks', '我的路线', 'Laluan saya', 'எனது நடைகள்'],
    'plan.csv': ['Export outcomes (CSV)', '导出结果 (CSV)', 'Eksport hasil (CSV)', 'முடிவுகளை ஏற்றுமதி (CSV)'],
    'plan.toNext': ['{0} m to stop {1}', '距检查点 {1} 还有 {0} 米', '{0} m ke hentian {1}', 'நிறுத்தம் {1}-க்கு {0} மீ'],
    'plan.gps': ['Show my distance to the next stop', '显示我到下一个检查点的距离', 'Tunjuk jarak saya ke hentian seterusnya', 'அடுத்த நிறுத்தத்திற்கான தூரத்தைக் காட்டு'],
    'common.honest': ['Places to check, not confirmed breeding sites', '待检查地点，非确认的滋生地', 'Tempat untuk diperiksa, bukan tapak pembiakan yang disahkan', 'சரிபார்க்க வேண்டிய இடங்கள், உறுதிப்படுத்தப்பட்ட இனப்பெருக்க இடங்கள் அல்ல'],
    'common.dark': ['Dark mode', '深色模式', 'Mod gelap', 'இருண்ட முறை'],
    'common.light': ['Light mode', '浅色模式', 'Mod cerah', 'வெளிர் முறை'],
    'common.share': ['Share', '分享', 'Kongsi', 'பகிர்'],
    'common.listen': ['Listen', '朗读', 'Dengar', 'கேட்க'],
    'common.stopListening': ['Stop', '停止', 'Henti', 'நிறுத்து'],
    'common.speak': ['Speak your question', '语音提问', 'Sebut soalan anda', 'உங்கள் கேள்வியைப் பேசுங்கள்'],
    'common.reviewNote': ['Interface translations are drafts for native-speaker review.', '界面翻译为草稿，待母语者审阅。', 'Terjemahan antara muka adalah draf untuk semakan penutur asli.', 'இடைமுகப் பெயர்ப்புகள் தாய்மொழியாளர் ஆய்வுக்கான வரைவுகள்.'],
  };
  const ORDER = ['en', 'zh', 'ms', 'ta'];
  let lang = 'en';
  try { lang = ORDER.includes(localStorage.getItem('denguesux:lang')) ? localStorage.getItem('denguesux:lang') : 'en'; } catch {}
  function t(key, ...args) {
    const row = S[key]; if (!row) return key;
    let text = row[ORDER.indexOf(lang)] || row[0];
    args.forEach((a, i) => { text = text.replace(`{${i}}`, String(a)); });
    return text;
  }
  function apply(next) {
    if (next && ORDER.includes(next)) { lang = next; try { localStorage.setItem('denguesux:lang', lang); } catch {} }
    document.documentElement.lang = lang === 'en' ? 'en' : lang === 'zh' ? 'zh-Hans' : lang === 'ms' ? 'ms' : 'ta';
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const [key, ...args] = el.dataset.i18n.split('|');
      const text = t(key, ...args);
      const target = el.dataset.i18nAttr;
      if (target) el.setAttribute(target, text);
      else { const icon = el.querySelector('i.ph'); el.textContent = text; if (icon) el.prepend(icon, ' '); }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    document.dispatchEvent(new CustomEvent('denguesux:lang', {detail: {lang}}));
  }
  window.I18N = {t, apply, get lang() { return lang; }, languages: ORDER, speech: {en: 'en-SG', zh: 'zh-CN', ms: 'ms-MY', ta: 'ta-IN'}};
  document.addEventListener('DOMContentLoaded', () => apply());
})();
