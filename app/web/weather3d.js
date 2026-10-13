/* Rain inside the 3D walk: the day's millimetres at the area's nearest NEA station, drawn as falling streaks with a
   three.js custom layer. An illustration of an observation (density follows the reading), never a forecast. */
(() => {
  'use strict';
  const layers = new WeakMap();  // map -> {layer, set}
  function build(map, THREE, gl, {center, mm}) {
    const origin = gl.MercatorCoordinate.fromLngLat(center, 0), unit = origin.meterInMercatorCoordinateUnits();
    const count = Math.round(Math.min(4800, Math.max(500, 500 + mm * 320))), box = 460, top = 150, drop = 2.6;
    const positions = new Float32Array(count * 6), speed = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const x = (Math.random() - .5) * box, y = Math.random() * top, z = (Math.random() - .5) * box;
      positions.set([x, y, z, x + .3, y - drop, z], i * 6); speed[i] = 30 + Math.random() * 22;
    }
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({color: 0x8fb8d6, transparent: true, opacity: .62});
    const scene = new THREE.Scene(); scene.add(new THREE.LineSegments(geometry, material));
    const camera = new THREE.Camera();
    // Scene metres (x east, y up, z south) into Mercator at the origin: the standard three.js-on-MapLibre transform.
    const model = new THREE.Matrix4().makeTranslation(origin.x, origin.y, origin.z).scale(new THREE.Vector3(unit, -unit, unit)).multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2));
    let renderer = null, last = performance.now(), on = true;
    const layer = {
      id: 'rain-3d', type: 'custom', renderingMode: '3d',
      onAdd(m, context) { renderer = new THREE.WebGLRenderer({canvas: m.getCanvas(), context, antialias: true}); renderer.autoClear = false; },
      render(context, matrix) {
        if (!on || !renderer) return;
        const now = performance.now(), dt = Math.min(.1, (now - last) / 1000); last = now;
        const p = geometry.attributes.position.array;
        for (let i = 0; i < count; i++) { let y = p[i * 6 + 1] - speed[i] * dt; if (y < 0) y = top; p[i * 6 + 1] = y; p[i * 6 + 4] = y - drop; }
        geometry.attributes.position.needsUpdate = true;
        camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix).multiply(model);
        renderer.resetState(); renderer.render(scene, camera);
        map.triggerRepaint();
      },
      onRemove() { geometry.dispose(); material.dispose(); renderer = null; },
    };
    return {layer, set(v) { on = v; if (v) { last = performance.now(); map.triggerRepaint(); } }};
  }
  async function set(map, {on, mm, center}) {
    if (!map || !center) return;
    let entry = layers.get(map);
    if (!entry) {
      if (!on || !window.Checklist3D?.three || !window.maplibregl) return;
      const THREE = await window.Checklist3D.three();
      if (!map.getStyle() || layers.get(map)) return;
      entry = build(map, THREE, window.maplibregl, {center, mm: Number(mm) || 0});
      map.addLayer(entry.layer); layers.set(map, entry);
      map.once('remove', () => layers.delete(map));
    }
    entry.set(!!on);
  }
  window.Weather3D = {set, active: map => !!layers.get(map)};
})();
