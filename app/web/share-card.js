/* Share card: one planning area as a 1200×630 image (name, this week's numbers, outlook, QR to the resident page),
   handed to the phone's share sheet when available, otherwise downloaded. Nothing personal; every number dated. */
(() => {
  'use strict';
  const esc = v => String(v ?? '');
  function roundRect(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }
  function wrap(c, text, x, y, max, lh) { const words = text.split(' '); let line = ''; for (const w of words) { const test = line ? line + ' ' + w : w; if (c.measureText(test).width > max && line) { c.fillText(line, x, y); line = w; y += lh; } else line = test; } if (line) c.fillText(line, x, y); return y + lh; }
  async function qrImage(url) {
    if (!window.Poster?.qrSvg) return null;
    const svg = window.Poster.qrSvg(url).replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ');
    const img = new Image(); img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; });
    return img;
  }
  async function render(area, data) {
    const canvas = document.createElement('canvas'); canvas.width = 1200; canvas.height = 630; const c = canvas.getContext('2d');
    const date = new Date(data.current.as_of).toLocaleDateString('en-SG', {day: 'numeric', month: 'short', year: 'numeric'});
    const o = (data.area_forecast?.areas || []).find(a => a.code === area.code);
    const slug = area.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-$/, '');
    const link = window.DengueLinks?.resident_url ? `${window.DengueLinks.resident_url}/areas/${slug}.html` : `${location.origin}/#plan/${slug}`;
    c.fillStyle = '#163f35'; c.fillRect(0, 0, 1200, 630);
    c.fillStyle = '#0f2d25'; roundRect(c, 820, 60, 320, 510, 24); c.fill();
    c.fillStyle = '#9fd4bd'; c.font = '600 26px "DM Sans", sans-serif'; c.fillText('DengueSUX · ' + date, 70, 90);
    c.fillStyle = '#ffffff'; c.font = '700 76px "DM Sans", sans-serif'; wrap(c, area.name, 70, 180, 700, 80);
    const risk = area.risk || 'Low', colour = risk === 'High' ? '#ff7a5c' : risk === 'Medium' ? '#f3b847' : '#8fd1b4';
    c.fillStyle = colour; roundRect(c, 70, 215, 60 + c.measureText(risk).width * .45, 44, 22); c.fill();
    c.fillStyle = '#163f35'; c.font = '700 26px "DM Sans", sans-serif'; c.fillText(risk + ' priority', 86, 246);
    c.fillStyle = '#ffffff'; c.font = '700 120px "DM Sans", sans-serif'; c.fillText(String(area.cluster_cases ?? 0), 70, 400);
    c.fillStyle = '#dfe8de'; c.font = '400 30px "DM Sans", sans-serif';
    let y = wrap(c, `${area.cluster_cases === 1 ? 'person' : 'people'} in ${area.cluster_count ?? 0} active dengue ${area.cluster_count === 1 ? 'cluster' : 'clusters'} (NEA)`, 70, 445, 700, 38);
    if (o) y = wrap(c, `About two weeks ahead: ${Math.round(o.p_high * 100)}% chance of 10 or more people in clusters. Chances, not certainties.`, 70, y + 10, 700, 38);
    c.fillStyle = '#9fb0a4'; c.font = '400 24px "DM Sans", sans-serif'; c.fillText('Places to check, not confirmed breeding sites · open data from NEA, MOH and URA', 70, 585);
    try { const img = await qrImage(link); if (img) { c.fillStyle = '#fff'; roundRect(c, 860, 100, 240, 240, 12); c.fill(); c.drawImage(img, 872, 112, 216, 216); } } catch {}
    c.fillStyle = '#ffffff'; c.font = '700 28px "DM Sans", sans-serif'; c.fillText('Scan for what to do', 860, 390);
    c.fillStyle = '#bcd2c6'; c.font = '400 22px "DM Sans", sans-serif'; wrap(c, link.replace(/^https?:\/\//, ''), 860, 430, 260, 28);
    c.fillStyle = '#9fd4bd'; c.font = '600 22px "DM Sans", sans-serif'; c.fillText('Telegram: @DengueSUXbot', 860, 540);
    return canvas;
  }
  async function share(code) {
    const data = window.ChatHome?.data || window.DengueData; const area = data?.current?.areas?.find(a => a.code === code); if (!area) return;
    const canvas = await render(area, data);
    const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
    const file = new File([blob], `denguesux-${area.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.png`, {type: 'image/png'});
    const text = `${area.name}: ${area.cluster_cases} ${area.cluster_cases === 1 ? 'person' : 'people'} in active dengue clusters. Check for stagnant water this week.`;
    if (navigator.canShare?.({files: [file]})) { try { await navigator.share({files: [file], title: `DengueSUX · ${area.name}`, text}); return; } catch (e) { if (e?.name === 'AbortError') return; } }
    const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = file.name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 4000);
    window.ChatHome?.hooks?.toast?.('Share card saved as an image.');
  }
  document.addEventListener('click', e => { const b = e.target.closest('[data-share-area]'); if (!b) return; e.preventDefault(); share(b.dataset.shareArea); });
  window.ShareCard = {share, render};
})();
