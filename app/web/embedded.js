/* Portable export only: inflate gzip+base64 payloads embedded in <script type="text/plain"> elements. */
(() => {
  'use strict';
  const cache = new Map();
  function blob(id, type = 'application/octet-stream') {
    if (!cache.has(id)) cache.set(id, (async () => {
      const node = document.getElementById(id);
      if (!node || !('DecompressionStream' in window)) throw new Error('Embedded data unavailable');
      const bytes = Uint8Array.from(atob(node.textContent.trim()), c => c.charCodeAt(0));
      const text = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
      return new Blob([text], {type});
    })());
    return cache.get(id);
  }
  window.DengueEmbedded = {blob, json: id => blob(id, 'application/json').then(b => b.text()).then(JSON.parse)};
})();
