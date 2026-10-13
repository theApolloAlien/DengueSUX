/* Registers the service worker (installable app, offline plan) and reports its state for the field mode banner. */
(() => {
  'use strict';
  // Public links (resident site, app, Telegram) for posters and share cards.
  if (!window.DENGUESUX_DATA && location.protocol !== 'file:') fetch('/api/links').then(r => r.ok ? r.json() : null).then(j => { if (j) { window.DengueLinks = j; document.dispatchEvent(new CustomEvent('denguesux:links')); } }).catch(() => {});
  if (!('serviceWorker' in navigator) || window.DENGUESUX_DATA || location.protocol === 'file:') return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').then(reg => { window.DengueOffline = {ready: true, registration: reg}; document.dispatchEvent(new CustomEvent('denguesux:offline-ready')); }).catch(() => {});
  });
})();
