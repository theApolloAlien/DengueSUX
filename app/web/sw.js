/* DengueSUX service worker: the app shell and the last data stay available offline for a field walk.
   App files: cache first, refreshed in the background. Data files: network first, cached copy when offline.
   API calls: network only (a saved plan never pretends a report was sent). */
const VERSION = 'denguesux-v1';
const SHELL = ['/', '/index.html', '/app.css', '/app.js', '/product.js', '/fieldwork.js', '/chat-home.js', '/assistant.js', '/showcase.js', '/answer-cards.js',
  '/checklist3d.js', '/hero3d.js', '/flythrough.js', '/weather3d.js', '/map3d-extras.js', '/insights.js', '/platform.js', '/poster.js', '/story.js', '/motion.js',
  '/checkblock.js', '/location-check.js', '/aedes-layer.js', '/activity-feed.js', '/care-actions.js', '/cluster-timeline.js', '/embedded.js', '/i18n.js', '/offline.js',
  '/vendor/leaflet/leaflet.js', '/vendor/leaflet/leaflet.css', '/vendor/icons/style.css', '/vendor/qrcode/qrcode.min.js', '/brand/logo-mark.svg', '/brand/favicon.svg', '/brand/site.webmanifest'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(VERSION).then(cache => Promise.allSettled(SHELL.map(url => cache.add(url)))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/')) return;  // live only
  if (url.pathname.startsWith('/data/')) {
    event.respondWith(fetch(request).then(response => { const copy = response.clone(); caches.open(VERSION).then(cache => cache.put(request, copy)); return response; })
      .catch(() => caches.match(request).then(hit => hit || new Response('{"offline":true}', {status: 503, headers: {'content-type': 'application/json'}}))));
    return;
  }
  event.respondWith(caches.match(request).then(hit => {
    const refresh = fetch(request).then(response => { if (response.ok) caches.open(VERSION).then(cache => cache.put(request, response.clone())); return response; }).catch(() => hit);
    return hit || refresh;
  }));
});
