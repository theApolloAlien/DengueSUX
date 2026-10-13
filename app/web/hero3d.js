/* 3D Singapore: every URA planning area as a prism, raised by people in active NEA clusters. Data, not decoration:
   heights and colours come from the dated snapshot; flat means no active cluster, not no risk. */
(() => {
  'use strict';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const COLOR = {High: '#ff7a5c', Medium: '#f3b847', Low: '#2f6a55', ground: '#173d32', edge: '#4f8a72', cluster: '#ff4b3a'};
  const THEMES = {
    night: {background: '#0b221c', sky: '#0f2d25', horizon: '#1d4a3d', ground: COLOR.ground, edge: '#3f7a63', low: '#245847', label: 'dark'},
    day: {background: '#eef2ea', sky: '#d9e8ee', horizon: '#f3f5ee', ground: '#dfe7da', edge: '#a8bba9', low: '#c6d6c4', label: 'light'},
  };
  let library = null;
  function loadLibrary() {
    if (window.maplibregl) return Promise.resolve(window.maplibregl);
    if (library) return library;
    library = new Promise((resolve, reject) => {
      if (!document.querySelector('link[data-maplibre]')) { const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/vendor/maplibre/maplibre-gl.css'; css.dataset.maplibre = ''; document.head.append(css); }
      const script = document.createElement('script'); script.src = '/vendor/maplibre/maplibre-gl.js'; script.async = true;
      script.onload = () => resolve(window.maplibregl); script.onerror = () => { library = null; script.remove(); reject(new Error('Map library unavailable')); }; document.head.append(script);
    });
    return library;
  }
  function supported() { try { return !!document.createElement('canvas').getContext('webgl2'); } catch { return false; } }
  // Height in metres: active areas rise from 900 m by the square root of people in clusters (a 100-person area reaches 3.5 km).
  const heightFor = people => people > 0 ? Math.round(900 + 2600 * Math.sqrt(Math.min(people, 400) / 100)) : 90;

  function collection(current) {
    const byCode = new Map((current.areas || []).map(a => [a.code, a]));
    const features = (current.boundaries?.features || []).map((f, i) => {
      const a = byCode.get(f.properties.code) || {};
      return {type: 'Feature', id: i, geometry: f.geometry, properties: {code: f.properties.code, name: a.name || f.properties.name, risk: a.risk || 'Low',
        people: a.cluster_cases || 0, clusters: a.cluster_count || 0, height: heightFor(a.cluster_cases || 0)}};
    });
    return {type: 'FeatureCollection', features};
  }
  function clusterBeacons(current, areas) {
    const heights = new Map(areas.features.map(f => [f.properties.code, f.properties.height]));
    return {type: 'FeatureCollection', features: (current.clusters?.features || []).map((f, i) => {
      const top = Math.max(...(f.properties.area_codes || [f.properties.area_code]).map(code => heights.get(code) || 90));
      return {type: 'Feature', id: i, geometry: f.geometry, properties: {name: f.properties.name, people: f.properties.cases, base: top, top: top + 700}};
    })};
  }
  function centroid(geometry) {
    const rings = geometry.type === 'Polygon' ? [geometry.coordinates[0]] : geometry.coordinates.map(p => p[0]);
    let best = rings[0], area = 0;
    for (const ring of rings) { let a = 0; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) a += (ring[j][0] + ring[i][0]) * (ring[j][1] - ring[i][1]); if (Math.abs(a) > area) { area = Math.abs(a); best = ring; } }
    let x = 0, y = 0; best.forEach(p => { x += p[0]; y += p[1]; }); return [x / best.length, y / best.length];
  }

  /** Mount a 3D landscape in host. opts: {theme:'night'|'day', orbit:true, labels:5, interactive:true, onPick(code), legend:true} */
  function mount(host, current, opts = {}) {
    if (!host || !current?.boundaries?.features?.length || !supported()) return null;
    const theme = THEMES[opts.theme || 'night'];
    const state = {closed: false, map: null, frame: 0, hover: null, idleSince: performance.now(), markers: []};
    const box = document.createElement('div'); box.className = `landscape3d is-${opts.theme || 'night'}`; box.setAttribute('role', opts.onPick ? 'region' : 'img');
    box.setAttribute('aria-label', 'Three-dimensional map of Singapore planning areas, raised by people in active NEA dengue clusters');
    host.append(box);
    const tip = document.createElement('div'); tip.className = 'landscape-tip'; tip.hidden = true; host.append(tip);
    if (opts.legend !== false) {
      const legend = document.createElement('div'); legend.className = 'landscape-legend';
      legend.innerHTML = `<span><b style="background:${COLOR.High}"></b>High</span><span><b style="background:${COLOR.Medium}"></b>Medium</span><span><b style="background:${theme.low}"></b>No active cluster</span><span><b class="beacon" style="background:${COLOR.cluster}"></b>Cluster</span><small>Height = people in active clusters · NEA ${esc(new Date(current.as_of).toLocaleDateString('en-SG', {day: 'numeric', month: 'short'}))}</small>`;
      host.append(legend);
    }
    const areas = collection(current), beacons = clusterBeacons(current, areas);
    loadLibrary().then(gl => {
      if (state.closed) return;
      const map = state.map = new gl.Map({container: box, style: {version: 8, sources: {}, layers: [{id: 'background', type: 'background', paint: {'background-color': theme.background}}]},
        center: [103.82, 1.352], zoom: 10, pitch: 58, bearing: -22, maxPitch: 75, minZoom: 9, maxZoom: 14, attributionControl: false, antialias: true,
        interactive: opts.interactive !== false, dragRotate: true, touchPitch: false});
      map.scrollZoom.disable(); map.keyboard.disable();
      const ready = () => {
        if (state.closed || state.built) return; state.built = true;
        try { map.setSky({'sky-color': theme.sky, 'horizon-color': theme.horizon, 'fog-color': theme.background, 'sky-horizon-blend': .8, 'horizon-fog-blend': .5, 'fog-ground-blend': .55, 'atmosphere-blend': 0}); } catch {}
        map.setLight({anchor: 'map', color: '#fff4e2', intensity: .42, position: [1.4, 215, 40]});
        state.areas = areas; state.target = new Map(areas.features.map(f => [f.properties.code, {height: f.properties.height, risk: f.properties.risk}]));
        if (!reduced.matches && opts.rise !== false) areas.features.forEach(f => { f.properties.height = 0; });
        map.addSource('areas', {type: 'geojson', data: areas});
        map.addSource('beacons', {type: 'geojson', data: beacons});
        const risk = ['match', ['get', 'risk'], 'High', COLOR.High, 'Medium', COLOR.Medium, theme.low];
        map.addLayer({id: 'areas-prism', type: 'fill-extrusion', source: 'areas', paint: {
          'fill-extrusion-color': ['case', ['boolean', ['feature-state', 'hover'], false], ['match', ['get', 'risk'], 'High', '#ffa48c', 'Medium', '#ffd37a', '#4f957a'], risk],
          'fill-extrusion-height': ['get', 'height'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': .94, 'fill-extrusion-vertical-gradient': true}});
        map.addLayer({id: 'areas-edge', type: 'line', source: 'areas', paint: {'line-color': theme.edge, 'line-width': .8, 'line-opacity': .7}});
        map.addLayer({id: 'areas-selected', type: 'line', source: 'areas', filter: ['==', ['get', 'code'], ''], paint: {'line-color': opts.theme === 'day' ? '#163f35' : '#fff6dc', 'line-width': 3}});
        map.addLayer({id: 'cluster-beacons', type: 'fill-extrusion', source: 'beacons', paint: {'fill-extrusion-color': COLOR.cluster, 'fill-extrusion-height': ['get', 'top'], 'fill-extrusion-base': ['get', 'base'], 'fill-extrusion-opacity': .9}});
        // Persistent padding keeps the island (and the orbit's pivot) in the open part of the frame. It is measured
        // when the stage has a real size (the view may still be hidden at mount) and again after every resize.
        const bounds = new gl.LngLatBounds([103.6, 1.21], [104.04, 1.47]);
        const frame = () => {
          const w = box.clientWidth, h = box.clientHeight; if (!w || !h) return false;
          const pad = typeof opts.padding === 'function' ? opts.padding(w, h) : opts.padding || {top: 30, bottom: 30, left: 30, right: 30};
          map.setPadding({top: 0, bottom: 0, left: 0, right: 0});
          const cam = map.cameraForBounds(bounds, {padding: pad, bearing: -22});
          map.setPadding(pad); map.jumpTo({center: [103.82, 1.352], zoom: (cam?.zoom ?? 10) - (opts.zoomOut ?? .02), pitch: 58, bearing: state.framed ? map.getBearing() : -22});
          state.framed = true; state.width = w; return true;
        };
        frame();
        let resizeTimer = 0;
        state.observer = new ResizeObserver(() => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (box.clientWidth && box.clientWidth !== state.width) frame(); }, 120); });
        state.observer.observe(box);
        // Labels for the top areas, floating over their prisms.
        const top = areas.features.filter(f => f.properties.people > 0).sort((a, b) => b.properties.people - a.properties.people).slice(0, typeof opts.labels === 'function' ? opts.labels(box.clientWidth || host.clientWidth) : opts.labels ?? 5);
        top.forEach(f => {
          const el = document.createElement(opts.onPick ? 'button' : 'span'); el.className = `landscape-label risk-${f.properties.risk.toLowerCase()}`;
          if (opts.onPick) { el.type = 'button'; el.onclick = e => { e.stopPropagation(); opts.onPick(f.properties.code); }; el.setAttribute('aria-label', `${f.properties.name}: ${f.properties.people} people in active clusters`); }
          el.innerHTML = `<b>${esc(f.properties.name)}</b><span>${f.properties.people}</span>`;
          state.markers.push(new gl.Marker({element: el, anchor: 'bottom', offset: [0, -8]}).setLngLat(centroid(f.geometry)).addTo(map));
        });
        // Larger areas keep their label; a label that would overlap one already shown fades out until the view changes.
        let tidyAt = 0;
        const tidy = () => { const now = performance.now(); if (now - tidyAt < 180) return; tidyAt = now; const shown = [];
          state.markers.forEach(m => { const el = m.getElement(), r = el.getBoundingClientRect(), hit = shown.some(o => r.left < o.right + 4 && r.right > o.left - 4 && r.top < o.bottom + 2 && r.bottom > o.top - 2);
            el.classList.toggle('is-hidden', hit); if (!hit) shown.push(r); }); };
        map.on('render', tidy); tidy();
        if (opts.interactive !== false) {
          map.on('mousemove', 'areas-prism', e => {
            const f = e.features?.[0]; if (!f) return; map.getCanvas().style.cursor = opts.onPick ? 'pointer' : '';
            if (state.hover !== f.id) { if (state.hover !== null) map.setFeatureState({source: 'areas', id: state.hover}, {hover: false}); state.hover = f.id; map.setFeatureState({source: 'areas', id: f.id}, {hover: true}); }
            const p = f.properties; tip.hidden = false; tip.innerHTML = `<b>${esc(p.name)}</b><span>${p.people ? `${p.people} ${p.people === 1 ? 'person' : 'people'} · ${p.clusters} ${p.clusters === 1 ? 'cluster' : 'clusters'}` : 'No active cluster'}</span><em class="risk-${String(p.risk).toLowerCase()}">${esc(p.risk)}</em>`;
            const r = host.getBoundingClientRect(); tip.style.transform = `translate(${Math.min(e.point.x + 14, r.width - 200)}px,${Math.max(e.point.y - 54, 6)}px)`;
          });
          map.on('mouseleave', 'areas-prism', () => { tip.hidden = true; map.getCanvas().style.cursor = ''; if (state.hover !== null) map.setFeatureState({source: 'areas', id: state.hover}, {hover: false}); state.hover = null; });
          if (opts.onPick) map.on('click', 'areas-prism', e => { const f = e.features?.[0]; if (f) opts.onPick(f.properties.code); });
          ['dragstart', 'rotatestart', 'zoomstart'].forEach(name => map.on(name, e => { if (e.originalEvent) state.idleSince = Infinity; }));
          map.on('dragend', () => { state.idleSince = performance.now() + 4000; });
        }
        host.classList.add('is-ready');
        if (!reduced.matches && opts.rise !== false) { beaconsVisible(false); animateTo(state.target, 1400, 'riseOut').then(() => beaconsVisible(true)); } else state.ready = true;
        orbit();
      };
      map.once('load', ready); map.once('style.load', ready);
      const poll = setInterval(() => { if (state.closed || state.built) return clearInterval(poll); if (map.style?._loaded) ready(); }, 200);
    }).catch(() => host.classList.add('is-failed'));
    // A slow, continuous orbit (about 4° a second); it pauses while someone is exploring and for reduced motion.
    function orbit() {
      let last = performance.now();
      const loop = now => {
        if (state.closed) return;
        const dt = Math.min(.1, (now - last) / 1000); last = now;
        // Off-screen (another view is showing) the loop idles instead of re-rendering the map every frame.
        if (opts.orbit !== false && !reduced.matches && !document.hidden && box.offsetParent !== null && now > state.idleSince && state.map && !state.map.isMoving()) state.map.setBearing(state.map.getBearing() + 4 * dt);
        state.frame = requestAnimationFrame(loop);
      };
      state.frame = requestAnimationFrame(loop);
    }
    // Animate every prism towards target heights (and risk colours) — used for the rise-in, the two-week
    // outlook and the time-lapse. Heights interpolate on the GeoJSON so colours switch at the midpoint.
    function animateTo(target, ms = 900, easing = 'inOut') {
      if (!state.map?.getSource('areas')) return Promise.resolve();
      cancelAnimationFrame(state.morph);
      const from = new Map(state.areas.features.map(f => [f.properties.code, f.properties.height]));
      const ease = easing === 'riseOut' ? x => 1 - Math.pow(1 - x, 3) : x => x < .5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;
      const start = performance.now(), duration = reduced.matches ? 0 : ms;
      return new Promise(resolve => {
        const tick = now => {
          if (state.closed) return resolve();
          const k = duration ? Math.min(1, (now - start) / duration) : 1, e = ease(k);
          state.areas.features.forEach(f => { const t = target.get(f.properties.code) || {height: 90, risk: 'Low'}; const h0 = from.get(f.properties.code) ?? 90;
            f.properties.height = Math.round(h0 + (t.height - h0) * e); if (k >= .5 || h0 <= 100) { f.properties.risk = t.risk; if (t.people != null) f.properties.people = t.people; if (t.clusters != null) f.properties.clusters = t.clusters; } });
          state.map.getSource('areas').setData(state.areas);
          if (k < 1) state.morph = requestAnimationFrame(tick); else { state.ready = true; resolve(); }
        };
        state.morph = requestAnimationFrame(tick);
      });
    }
    function caption(text) { const small = host.querySelector('.landscape-legend small'); if (small) small.textContent = text; }
    function beaconsVisible(on) { if (state.map?.getLayer('cluster-beacons')) state.map.setLayoutProperty('cluster-beacons', 'visibility', on ? 'visible' : 'none'); }
    return {
      get map() { return state.map; },
      ready() { return new Promise(resolve => { const check = () => state.closed || state.ready ? resolve() : setTimeout(check, 80); check(); }); },
      /** people: Map(code -> {people, clusters}); heights and colours follow the same rule as the live snapshot. */
      setPeople(people, ms = 700) {
        const target = new Map((state.areas?.features || []).map(f => { const p = people.get(f.properties.code) || {people: 0, clusters: 0};
          return [f.properties.code, {height: heightFor(p.people), risk: p.people >= 10 ? 'High' : p.clusters > 0 ? 'Medium' : 'Low', people: p.people, clusters: p.clusters}]; }));
        beaconsVisible(false); return animateTo(target, ms);
      },
      /** The two-week outlook: height follows the chance of 10+ people in clusters; colour follows the outlook band. */
      showOutlook(outlook, ms = 1100) {
        const by = new Map((outlook?.areas || []).map(a => [a.code, a]));
        const target = new Map((state.areas?.features || []).map(f => { const a = by.get(f.properties.code);
          return [f.properties.code, {height: a ? Math.round(90 + 3600 * a.p_high + 600 * a.p_any) : 90, risk: a?.band || 'Low'}]; }));
        beaconsVisible(false); caption('Height = chance of 10+ people in clusters in about two weeks · trained on NEA listings since 2020'); return animateTo(target, ms);
      },
      showNow(ms = 900) { beaconsVisible(true); caption(`Height = people in active clusters · NEA ${new Date(current.as_of).toLocaleDateString('en-SG', {day: 'numeric', month: 'short'})}`); return animateTo(state.target, ms); },
      caption,
      /** Today's labels describe today; hide them while the heights show another day or the outlook. */
      labels(on) { state.markers.forEach(m => m.getElement().classList.toggle('is-off', !on)); },
      select(code) { if (state.map?.getLayer('areas-selected')) state.map.setFilter('areas-selected', ['==', ['get', 'code'], code || '']); },
      /** Fly into one area: the island sinks and the camera dives towards it; resolves when the dive ends. */
      async dive(code, ms = 1900) {
        const f = state.areas?.features.find(x => x.properties.code === code); if (!f || !state.map) return;
        state.idleSince = Infinity; this.select(code);
        const sink = new Map(state.areas.features.map(x => [x.properties.code, {height: x.properties.code === code ? x.properties.height : 20, risk: x.properties.risk}]));
        const [lng, lat] = centroid(f.geometry);
        state.map.easeTo({center: [lng, lat], zoom: 13.6, pitch: 72, bearing: state.map.getBearing() + 25, duration: reduced.matches ? 0 : ms, easing: x => 1 - Math.pow(1 - x, 3)});
        await animateTo(sink, ms * .7);
        if (!reduced.matches) await new Promise(r => setTimeout(r, ms * .35));
      },
      resize() { state.map?.resize(); },
      dispose() { state.closed = true; state.observer?.disconnect(); cancelAnimationFrame(state.frame); state.markers.forEach(m => m.remove()); state.map?.remove(); box.remove(); tip.remove(); host.querySelector('.landscape-legend')?.remove(); },
    };
  }
  window.Landscape3D = {mount, supported, heightFor};
})();
