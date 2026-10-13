/* 3D "what to look for" illustrations for each checklist item. Illustrations of the task, not views of the place. */
(() => {
  'use strict';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = n => `<i class="ph ph-${n}" aria-hidden="true"></i>`;
  // Loop: the problem (2 s), the fix (1.6 s), then the cleared state (1.4 s).
  const LOOP = 5, FIX_AT = 2, DONE_AT = 3.6;
  const KEYS = [[/gutter/i, 'gutter'], [/planter|tray|flower ?pot|saucer/i, 'tray'], [/pail|corridor/i, 'pail'], [/tree.?hole/i, 'treehole'],
    [/pond/i, 'pond'], [/\bbins?\b/i, 'bin'], [/container/i, 'containers'], [/drain/i, 'drain']];
  const COPY = {
    gutter: {title: 'Roof gutters', problem: 'Leaves block the gutter and rainwater pools behind them.', fix: 'Cleared, it drains. Report blocked roof gutters to the town council. Never climb to check.'},
    tray: {title: 'Planter trays', problem: 'Water collects in the tray under the pot.', fix: 'Empty the tray and wipe it dry, or remove it.'},
    pail: {title: 'Corridor pails', problem: 'An upright pail fills with rain or rinse water.', fix: 'Turn pails over and wipe their rims. Keep them under shelter.'},
    drain: {title: 'Drains', problem: 'Leaves and litter trap water in the drain.', fix: 'With the blockage gone, water flows on. Report blocked drains to the operator.'},
    containers: {title: 'Unused containers', problem: 'Spare tubs and boxes hold water.', fix: 'Empty them and store them upside down or under cover.'},
    bin: {title: 'Bin areas', problem: 'Water pools around the bin and on its lid.', fix: 'Mop up the puddle and keep the lid shut.'},
    pond: {title: 'Pond edges', problem: 'A still pocket forms between rocks, cut off from the moving water.', fix: 'Note where it is and tell the park manager.'},
    treehole: {title: 'Tree holes', problem: 'Rainwater sits in a hole in the trunk.', fix: 'Report it to the park manager so it can be filled.'},
  };
  const PALETTE = {plinth: '#e8e2d3', plinthTop: '#f3efe4', concrete: '#d9d4c5', wall: '#f4efe2', forest: '#163f35', sage: '#8fb39a', leaf: '#5f8f52',
    terracotta: '#c0643f', soil: '#5b4632', water: '#4f9fc4', amber: '#e3ad3c', red: '#c2523c', dark: '#2a2c26', bark: '#7a5a3c', sand: '#d8c49a', blue: '#3f7fb5'};
  let THREE = null, loading = null, thumbRenderer = null, liveRenderer = null;
  // One offscreen renderer serves every live illustration; each host shows a 2D copy, so a walk with eight stops
  // never opens eight WebGL contexts (browsers drop the oldest, which used to knock the 3D map back to 2D).
  function sharedLive() { if (!liveRenderer) { const c = document.createElement('canvas'); liveRenderer = makeRenderer(c); liveRenderer.setPixelRatio(1); liveRenderer.setSize(720, 450, false); } return liveRenderer; }
  const thumbs = new Map();

  function keyFor(text) { const found = KEYS.find(([pattern]) => pattern.test(String(text || ''))); return found ? found[1] : null; }
  function supported() { try { const c = document.createElement('canvas'); return !!(window.WebGL2RenderingContext && c.getContext('webgl2')); } catch { return false; } }
  function load() {
    if (THREE) return Promise.resolve(THREE);
    // The portable export embeds the module gzip-compressed (no server to fetch it from).
    const embedded = document.getElementById('three-module-gz');
    const source = embedded ? window.DengueEmbedded.blob('three-module-gz', 'text/javascript').then(blob => URL.createObjectURL(blob)) : Promise.resolve('/vendor/three/three.module.min.js');
    if (!loading) loading = source.then(url => import(url)).then(module => (THREE = module)).catch(error => { loading = null; throw error; });
    return loading;
  }
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ease = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  const fixAmount = t => t < FIX_AT ? 0 : t >= DONE_AT ? 1 : ease((t - FIX_AT) / (DONE_AT - FIX_AT));
  const phaseOf = t => t < FIX_AT ? 'problem' : t < DONE_AT ? 'fix' : 'done';

  // ---------- scene kit ----------
  function kit() {
    const T = THREE;
    const mat = (color, extra = {}) => new T.MeshStandardMaterial({color, roughness: .82, metalness: 0, ...extra});
    const mesh = (geometry, material, x = 0, y = 0, z = 0) => { const m = new T.Mesh(geometry, material); m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; return m; };
    const box = (w, h, d, material, x, y, z) => mesh(new T.BoxGeometry(w, h, d), material, x, y, z);
    const cyl = (rt, rb, h, material, x, y, z, seg = 32, open = false) => mesh(new T.CylinderGeometry(rt, rb, h, seg, 1, open), material, x, y, z);
    const water = (w, d, x, y, z) => {
      const geometry = new T.PlaneGeometry(w, d, 18, 18); geometry.rotateX(-Math.PI / 2);
      const m = new T.Mesh(geometry, mat(PALETTE.water, {transparent: true, opacity: .84, roughness: .06, metalness: .1, emissive: '#0e3d52', emissiveIntensity: .18}));
      m.position.set(x, y, z); m.receiveShadow = true; m.userData.base = geometry.attributes.position.array.slice(); m.userData.water = true; return m;
    };
    const disc = (r, material, x, y, z, seg = 40) => { const g = new T.CircleGeometry(r, seg); g.rotateX(-Math.PI / 2); return mesh(g, material, x, y, z); };
    const waterDisc = (r, x, y, z) => { const g = new T.CircleGeometry(r, 40); g.rotateX(-Math.PI / 2); const m = new T.Mesh(g, mat(PALETTE.water, {transparent: true, opacity: .86, roughness: .05, metalness: .1, emissive: '#0e3d52', emissiveIntensity: .18})); m.position.set(x, y, z); m.receiveShadow = true; m.userData.discWater = true; return m; };
    const larvae = (group, count, cx, y, cz, spread) => {
      const list = [], material = mat('#2b2a22', {roughness: .6});
      for (let i = 0; i < count; i++) {
        const l = new T.Mesh(new T.CapsuleGeometry(.007, .038, 3, 6), material);
        l.position.set(cx + (Math.sin(i * 2.7) * spread), y - .012, cz + (Math.cos(i * 1.9) * spread * .7));
        l.rotation.z = Math.PI / 2; l.userData.seed = i * 1.37; l.userData.y = l.position.y; group.add(l); list.push(l);
      }
      return list;
    };
    const leaves = (group, count, x0, x1, y, z, spread = .06) => {
      const list = [], colors = ['#8a6b3a', '#a4803f', '#6f7a3a', '#94572f'];
      for (let i = 0; i < count; i++) {
        const g = new T.SphereGeometry(.06, 10, 6); g.scale(1, .18, .55);
        const leaf = mesh(g, mat(colors[i % colors.length], {roughness: .9}), x0 + (x1 - x0) * (i / Math.max(1, count - 1)) + Math.sin(i * 3.1) * .03, y + (i % 3) * .012, z + Math.cos(i * 2.3) * spread);
        leaf.rotation.set(Math.sin(i) * .4, i * 1.3, Math.cos(i * 1.7) * .3); leaf.userData.home = leaf.position.clone(); group.add(leaf); list.push(leaf);
      }
      return list;
    };
    const mosquito = () => {
      const g = new T.Group(), body = mat('#1f211c', {roughness: .5});
      const thorax = new T.Mesh(new T.CapsuleGeometry(.011, .02, 3, 8), body); thorax.rotation.z = Math.PI / 2; g.add(thorax);
      const abdomen = new T.Mesh(new T.CapsuleGeometry(.008, .05, 3, 8), mat('#2d2f29', {roughness: .5})); abdomen.rotation.z = Math.PI / 2 - .25; abdomen.position.set(-.04, -.006, 0); g.add(abdomen);
      for (let i = 0; i < 4; i++) { const band = new T.Mesh(new T.TorusGeometry(.0085, .0018, 4, 10), mat('#f2f2ea')); band.rotation.y = Math.PI / 2; band.position.set(-.025 - i * .012, -.003 - i * .0015, 0); g.add(band); }
      const wingMaterial = new T.MeshStandardMaterial({color: '#ffffff', transparent: true, opacity: .45, side: T.DoubleSide, roughness: .2});
      const wings = [1, -1].map(side => { const w = new T.Mesh(new T.PlaneGeometry(.055, .016), wingMaterial); w.position.set(-.01, .008, .025 * side); w.rotation.x = Math.PI / 2; g.add(w); return w; });
      const legMaterial = mat('#1f211c');
      for (let i = 0; i < 6; i++) { const leg = new T.Mesh(new T.CylinderGeometry(.0012, .0012, .075, 4), legMaterial); const side = i % 2 ? 1 : -1; leg.position.set(.01 - Math.floor(i / 2) * .012, -.03, .018 * side); leg.rotation.x = .55 * side; g.add(leg); }
      g.userData.wings = wings; g.scale.setScalar(1.6); return g;
    };
    const plinth = group => {
      const base = cyl(2.35, 2.45, .26, mat(PALETTE.plinth, {roughness: .95}), 0, -.13, 0, 64); base.castShadow = false; group.add(base);
      const top = disc(2.33, mat(PALETTE.plinthTop, {roughness: .95}), 0, .001, 0, 64); top.castShadow = false; group.add(top);
    };
    return {T, mat, mesh, box, cyl, water, disc, waterDisc, larvae, leaves, mosquito, plinth};
  }

  // ---------- the eight illustrations ----------
  const SCENES = {
    gutter(k) {
      const {T, mat, box, cyl, water, leaves, larvae, plinth} = k, g = new T.Group(); plinth(g);
      const wall = mat(PALETTE.wall), concrete = mat(PALETTE.concrete), dark = mat('#55615a', {roughness: .5});
      g.add(box(3.4, 1.55, 1.3, wall, 0, .78, -.35));
      for (let i = 0; i < 4; i++) g.add(box(.55, .38, .02, dark, -1.2 + i * .8, .72, .31));
      g.add(box(3.4, .06, .16, concrete, 0, .38, .38));
      g.add(box(3.6, .2, 1.55, concrete, 0, 1.65, -.3));
      const gutterMat = mat('#bfc4bb', {roughness: .55, metalness: .2});
      g.add(box(3.4, .035, .34, gutterMat, 0, 1.56, .64)); g.add(box(3.4, .26, .035, gutterMat, 0, 1.68, .82));
      g.add(cyl(.065, .065, 1.62, mat('#a9b0a6', {roughness: .5, metalness: .2}), 1.5, .8, .6));
      const pool = water(2.3, .3, -.45, 1.63, .64);
      g.add(pool);
      const debris = leaves(g, 11, .7, 1.25, 1.64, .64, .07);
      const larvaList = larvae(g, 8, -.6, 1.63, .64, .55);
      const drops = []; for (let i = 0; i < 6; i++) { const d = new T.Mesh(new T.SphereGeometry(.03, 10, 8), mat(PALETTE.water, {transparent: true, opacity: .8, roughness: .1})); d.position.set(1.5, -1, .6); g.add(d); drops.push(d); }
      return {group: g, camera: [1.9, 3.9, 3.6], target: [.2, 1.25, .2], waters: [pool], larvae: larvaList, mosquitoAt: [-.3, 1.98, .62],
        fix(f, t) {
          debris.forEach((leaf, i) => { const lift = clamp(f * 1.6 - i * .06); leaf.position.set(leaf.userData.home.x + lift * .5, leaf.userData.home.y + lift * .9, leaf.userData.home.z + lift * .4); leaf.scale.setScalar(1 - lift * .9); leaf.visible = lift < .98; });
          const drain = clamp((f - .25) / .75); pool.scale.x = 1 - drain * .97; pool.position.x = -.45 + drain * 1.85 * .5; pool.visible = drain < .99;
          larvaList.forEach(l => { l.visible = drain < .5; });
          drops.forEach((d, i) => { const p = ((t * 1.3 + i / drops.length) % 1); const on = f > .3 && f < 1; d.visible = on; d.position.set(1.5, .02 - p * .4, .64); });
        }};
    },
    tray(k) {
      const {T, mat, box, cyl, mesh, waterDisc, larvae, plinth} = k, g = new T.Group(); plinth(g);
      g.add(box(3.2, .08, 2, mat('#cfc6b2', {roughness: .9}), 0, .04, -.1));
      g.add(box(3.2, 1.9, .14, mat(PALETTE.wall), 0, 1.03, -1.05));
      const grille = mat('#3f5a4f', {roughness: .5, metalness: .3});
      for (let i = 0; i < 7; i++) g.add(box(.025, .8, .025, grille, -1.25 + i * .12, 1.2, -.96));
      g.add(box(.78, .025, .03, grille, -.89, 1.6, -.96)); g.add(box(.78, .025, .03, grille, -.89, .8, -.96));
      const pot = new T.Group();
      const profile = [[0, 0], [.2, 0], [.22, .02], [.29, .46], [.32, .48], [.32, .53], [.27, .53], [0, .5]].map(([x, y]) => new T.Vector2(x, y));
      pot.add(mesh(new T.LatheGeometry(profile, 40), mat(PALETTE.terracotta, {roughness: .9})));
      const soil = new T.Mesh(new T.CircleGeometry(.27, 32), mat(PALETTE.soil)); soil.rotation.x = -Math.PI / 2; soil.position.y = .5; pot.add(soil);
      const leafMat = [mat(PALETTE.leaf), mat('#7aa765'), mat('#4e7d48')];
      for (let i = 0; i < 9; i++) { const geometry = new T.SphereGeometry(.13, 12, 8); geometry.scale(.35, 1.4, .18); const leaf = mesh(geometry, leafMat[i % 3], Math.sin(i * 2.1) * .1, .72 + (i % 3) * .05, Math.cos(i * 2.1) * .1); leaf.rotation.set(Math.cos(i * 2.1) * .5, i * .7, -Math.sin(i * 2.1) * .5); pot.add(leaf); }
      pot.position.set(.1, .12, .25); g.add(pot);
      const saucer = new T.Group();
      saucer.add(cyl(.42, .38, .07, mat('#b65a39', {roughness: .85}), 0, .035, 0, 48));
      const inner = cyl(.37, .35, .05, mat('#8f452c'), 0, .05, 0, 48); inner.castShadow = false; saucer.add(inner);
      const pool = waterDisc(.36, 0, .071, 0); saucer.add(pool);
      const larvaList = larvae(saucer, 6, .2, .071, .05, .1);
      saucer.position.set(.1, .08, .25); g.add(saucer);
      const drops = []; for (let i = 0; i < 7; i++) { const d = new T.Mesh(new T.SphereGeometry(.025, 10, 8), mat(PALETTE.water, {transparent: true, opacity: .8, roughness: .1})); g.add(d); drops.push(d); }
      return {group: g, camera: [2.5, 2.4, 3.5], target: [.05, .4, 0], waters: [], discs: [pool], larvae: larvaList, mosquitoAt: [.45, .55, .45],
        fix(f, t) {
          const lift = clamp(f / .3) * (1 - clamp((f - .75) / .25));
          pot.position.set(.1 - lift * .75, .12 + lift * .55, .25 - lift * .1);
          const tilt = Math.sin(clamp((f - .25) / .5) * Math.PI) * 1.05; saucer.rotation.z = -tilt; saucer.position.x = .1 + tilt * .1;
          const empty = clamp((f - .3) / .35); pool.scale.setScalar(Math.max(.001, 1 - empty)); pool.visible = empty < .99; larvaList.forEach(l => { l.visible = empty < .6; });
          drops.forEach((d, i) => { const p = ((t * 1.6 + i / drops.length) % 1); d.visible = f > .32 && f < .7; d.position.set(.55 + p * .12, .35 - p * .3, .2 + Math.sin(i) * .08); });
        }};
    },
    pail(k) {
      const {T, mat, box, cyl, mesh, waterDisc, larvae, plinth} = k, g = new T.Group(); plinth(g);
      g.add(box(3.4, .1, 2.1, mat('#cdc5b1', {roughness: .9}), 0, .05, 0));
      g.add(box(3.4, 2, .14, mat(PALETTE.wall), 0, 1.08, -1.0));
      g.add(box(.82, 1.62, .06, mat(PALETTE.forest, {roughness: .6}), -.75, .91, -.92));
      const gate = mat('#2c3b35', {roughness: .4, metalness: .4});
      for (let i = 0; i < 8; i++) g.add(box(.02, 1.56, .02, gate, -1.1 + i * .1, .9, -.86));
      g.add(box(3.4, .6, .1, mat('#e9e3d4'), 0, .38, 1.0)); g.add(box(3.4, .05, .16, mat('#bfb8a4'), 0, .7, 1.0));
      const pail = new T.Group();
      const shell = cyl(.27, .21, .44, mat(PALETTE.blue, {roughness: .5, side: T.DoubleSide}), 0, .22, 0, 40, true); pail.add(shell);
      pail.add(cyl(.21, .21, .02, mat('#356a97', {roughness: .5}), 0, .01, 0, 40));
      const rim = mesh(new T.TorusGeometry(.27, .014, 8, 40), mat('#2f5f8a', {roughness: .5})); rim.rotation.x = Math.PI / 2; rim.position.y = .44; pail.add(rim);
      const handle = mesh(new T.TorusGeometry(.26, .008, 6, 32, Math.PI), mat('#9aa39c', {metalness: .5, roughness: .4})); handle.position.y = .44; handle.rotation.y = Math.PI / 2; pail.add(handle);
      const pool = waterDisc(.245, 0, .36, 0); pail.add(pool);
      const larvaList = larvae(pail, 6, 0, .36, 0, .12);
      pail.position.set(.55, .1, .1); g.add(pail);
      const tub = cyl(.18, .15, .2, mat(PALETTE.amber, {roughness: .5}), 1.25, .2, -.35, 32); g.add(tub);
      return {group: g, camera: [2.9, 2.5, 3.4], target: [.2, .4, 0], waters: [], discs: [pool], larvae: larvaList, mosquitoAt: [.6, .8, .2],
        fix(f) {
          const flip = clamp((f - .1) / .6), lift = Math.sin(flip * Math.PI) * .32;
          pail.rotation.x = flip * Math.PI; pail.position.y = .1 + lift + (flip > .5 ? .44 * ((flip - .5) * 2) : 0);
          pool.visible = flip < .2; larvaList.forEach(l => { l.visible = flip < .2; });
        }};
    },
    drain(k) {
      const {T, mat, box, water, leaves, larvae, plinth} = k, g = new T.Group(); plinth(g);
      const concrete = mat(PALETTE.concrete), deep = mat('#b7b09d');
      g.add(box(3.6, .3, .9, concrete, 0, .15, -.75)); g.add(box(3.6, .3, .9, concrete, 0, .15, .75));
      g.add(box(3.6, .06, .6, deep, 0, .03, 0));
      g.add(box(3.6, .24, .04, deep, 0, .18, -.3)); g.add(box(3.6, .24, .04, deep, 0, .18, .3));
      const grate = mat('#4b5450', {metalness: .5, roughness: .4});
      for (let i = 0; i < 9; i++) g.add(box(.035, .03, .62, grate, .9 + i * .1, .3, 0));
      const pool = water(2.4, .56, -.55, .1, 0); g.add(pool);
      const debris = leaves(g, 12, .05, .7, .11, 0, .18);
      const can = new k.T.Mesh(new T.CylinderGeometry(.06, .06, .2, 16), mat(PALETTE.red, {metalness: .3, roughness: .4})); can.rotation.z = Math.PI / 2; can.position.set(.35, .13, .08); can.castShadow = true; g.add(can);
      const larvaList = larvae(g, 8, -.9, .1, 0, .45);
      return {group: g, camera: [2.8, 3.0, 3.3], target: [-.05, .05, 0], waters: [pool], larvae: larvaList, mosquitoAt: [-.6, .45, 0],
        fix(f) {
          const lift = clamp(f / .5);
          debris.forEach((leaf, i) => { const l = clamp(lift * 1.4 - i * .03); leaf.position.y = leaf.userData.home.y + l * .8; leaf.position.z = leaf.userData.home.z + l * .9; leaf.scale.setScalar(1 - l * .9); leaf.visible = l < .98; });
          can.position.y = .13 + lift * .8; can.position.z = .08 + lift * .9; can.visible = lift < .98;
          const flow = clamp((f - .35) / .65); pool.scale.x = 1 - flow * .97; pool.position.x = -.55 + flow * 1.7; pool.visible = flow < .99;
          larvaList.forEach(l => { l.visible = flow < .4; });
        }};
    },
    containers(k) {
      const {T, mat, box, cyl, waterDisc, larvae, plinth} = k, g = new T.Group(); plinth(g);
      g.add(box(3.6, .06, 2.2, mat('#d8d2c4', {roughness: .9}), 0, .03, 0));
      g.add(box(1.7, .9, .7, mat('#e9e2d0'), -.85, .5, -.7)); g.add(box(1.8, .06, .8, mat('#8f6b4a', {roughness: .6}), -.85, .97, -.7));
      g.add(box(1.7, .5, .04, mat(PALETTE.forest), -.85, 1.55, -1.03));
      const stool = cyl(.17, .17, .05, mat(PALETTE.red, {roughness: .5}), 1.05, .5, -.6, 24); g.add(stool); g.add(cyl(.03, .03, .45, mat('#777'), 1.05, .25, -.6, 8));
      const crate = box(.55, .3, .4, mat(PALETTE.blue, {roughness: .6}), -.2, .21, .5); g.add(crate);
      const foam = box(.45, .22, .32, mat('#f6f6f0', {roughness: .95}), .35, .17, .62); g.add(foam);
      const tub = new T.Group();
      tub.add(cyl(.3, .24, .32, mat(PALETTE.amber, {roughness: .5, side: T.DoubleSide}), 0, .16, 0, 40, true)); tub.add(cyl(.24, .24, .02, mat('#c99430'), 0, .01, 0, 40));
      const pool = waterDisc(.28, 0, .27, 0); tub.add(pool); const larvaList = larvae(tub, 5, 0, .27, 0, .14);
      tub.position.set(.85, .06, .3); g.add(tub);
      return {group: g, camera: [3.0, 2.6, 3.6], target: [.1, .35, 0], waters: [], discs: [pool], larvae: larvaList, mosquitoAt: [.85, .62, .3],
        fix(f) {
          const flip = clamp((f - .1) / .6), lift = Math.sin(flip * Math.PI) * .35;
          tub.rotation.z = flip * Math.PI; tub.position.set(.85 + flip * .1, .06 + lift + (flip > .5 ? .32 * ((flip - .5) * 2) : 0), .3);
          pool.visible = flip < .2; larvaList.forEach(l => { l.visible = flip < .2; });
        }};
    },
    bin(k) {
      const {T, mat, box, cyl, mesh, waterDisc, larvae, plinth} = k, g = new T.Group(); plinth(g);
      g.add(box(3.4, .06, 2.2, mat('#d4cdbd', {roughness: .9}), 0, .03, 0));
      const bin = new T.Group(); const green = mat('#2f6f58', {roughness: .55});
      bin.add(box(.8, 1.05, .8, green, 0, .62, 0));
      [-1, 1].forEach(side => { const wheel = cyl(.1, .1, .06, mat('#1d1f1c'), side * .32, .1, -.38, 20); wheel.rotation.x = Math.PI / 2; wheel.rotation.z = Math.PI / 2; bin.add(wheel); });
      const lid = new T.Group(); const lidMesh = box(.86, .07, .86, mat('#25594a', {roughness: .5}), 0, 0, .43); lid.add(lidMesh);
      const lidPool = waterDisc(.18, .1, .04, .5); lidPool.scale.set(1.4, 1, 1); lid.add(lidPool);
      lid.position.set(0, 1.15, -.43); lid.rotation.x = -.5; bin.add(lid);
      bin.position.set(-.3, 0, -.2); g.add(bin);
      const puddle = waterDisc(.5, .65, .07, .55); puddle.scale.set(1.5, 1, .9); g.add(puddle);
      const larvaList = larvae(g, 6, .65, .07, .55, .3);
      const mop = new T.Group(); mop.add(cyl(.02, .02, 1.3, mat('#b98b54'), 0, .65, 0, 8)); mop.add(box(.4, .08, .12, mat('#e8e0c8'), 0, .04, 0)); mop.position.set(1.6, 0, .9); mop.rotation.z = .3; g.add(mop);
      return {group: g, camera: [3.0, 2.8, 3.6], target: [.1, .4, .1], waters: [], discs: [puddle, lidPool], larvae: larvaList, mosquitoAt: [.6, .5, .5],
        fix(f) {
          const sweep = clamp(f / .7); mop.position.set(1.6 - sweep * 1.0, 0, .9 - Math.sin(sweep * Math.PI * 3) * .15); mop.visible = f < .98;
          puddle.scale.set(Math.max(.001, 1.5 * (1 - sweep)), 1, Math.max(.001, .9 * (1 - sweep))); puddle.visible = sweep < .99; larvaList.forEach(l => { l.visible = sweep < .4; });
          const shut = clamp((f - .5) / .4); lid.rotation.x = -.5 * (1 - shut); lidPool.visible = shut < .3;
        }};
    },
    pond(k) {
      const {T, mat, mesh, cyl, waterDisc, larvae, plinth} = k, g = new T.Group(); plinth(g);
      const grass = new T.Mesh(new T.CircleGeometry(2.3, 64), mat('#9cbf86', {roughness: .95})); grass.rotation.x = -Math.PI / 2; grass.position.y = .01; grass.receiveShadow = true; g.add(grass);
      const pond = waterDisc(1.15, -.45, .04, -.2); pond.scale.set(1.25, 1, .9); g.add(pond);
      const rockMat = [mat('#9a9486', {roughness: 1}), mat('#b2ab9b', {roughness: 1}), mat('#857f73', {roughness: 1})];
      const rocks = [[.75, .4], [.95, .1], [1.05, .55], [.85, .85], [.55, .7], [1.25, .3], [.45, .45]];
      rocks.forEach(([x, z], i) => { const r = mesh(new T.DodecahedronGeometry(.16 + (i % 3) * .05, 0), rockMat[i % 3], x, .1, z); r.rotation.set(i, i * 2, i * .5); r.scale.y = .7; g.add(r); });
      const pocket = waterDisc(.17, .82, .05, .5); g.add(pocket);
      const larvaList = larvae(g, 5, .82, .05, .5, .07);
      for (let i = 0; i < 14; i++) { const reed = cyl(.012, .016, .55 + (i % 4) * .1, mat(i % 2 ? '#5f8f52' : '#6f9a5b'), -1.5 + Math.sin(i * 1.7) * .25, .3, -.9 + Math.cos(i * 2.3) * .35, 6); reed.rotation.z = Math.sin(i) * .15; g.add(reed); }
      for (let i = 0; i < 4; i++) { const pad = new T.Mesh(new T.CircleGeometry(.12, 20, .3, Math.PI * 1.8), mat('#5c8f4e')); pad.rotation.x = -Math.PI / 2; pad.position.set(-.9 + i * .35, .05, -.35 + Math.sin(i * 2) * .3); g.add(pad); }
      const flag = new T.Group(); flag.add(cyl(.012, .012, .75, mat('#f3efe4'), 0, .37, 0, 8)); const cloth = new T.Mesh(new T.PlaneGeometry(.28, .17), mat(PALETTE.amber, {side: T.DoubleSide})); cloth.position.set(.14, .65, 0); flag.add(cloth); flag.position.set(.82, 0, .5); g.add(flag);
      return {group: g, camera: [2.3, 3.1, 3.7], target: [.1, .05, .1], waters: [], discs: [pond, pocket], larvae: larvaList, mosquitoAt: [.85, .35, .5],
        fix(f) { const rise = clamp(f / .6); flag.scale.set(1, Math.max(.001, rise), 1); flag.visible = rise > .01; cloth.rotation.y = Math.sin(f * 9) * .2; }};
    },
    treehole(k) {
      const {T, mat, mesh, cyl, waterDisc, larvae, plinth} = k, g = new T.Group(); plinth(g);
      const grass = new T.Mesh(new T.CircleGeometry(2.3, 64), mat('#a4c48d', {roughness: .95})); grass.rotation.x = -Math.PI / 2; grass.position.y = .01; grass.receiveShadow = true; g.add(grass);
      const bark = mat(PALETTE.bark, {roughness: .95});
      g.add(cyl(.42, .62, 2.6, bark, 0, 1.3, 0, 28));
      [[.9, 1.6, .4], [-.8, 1.9, -.2], [.2, 2.4, -.6]].forEach(([x, y, z]) => { const branch = cyl(.1, .16, 1.1, bark, x * .5, y, z * .5, 12); branch.rotation.z = -x * .9; branch.rotation.x = z * .9; g.add(branch); });
      const canopyMat = [mat('#4e7d48'), mat('#5f8f52'), mat('#6f9e5c')];
      [[0, 3.0, 0, .95], [.8, 2.6, .3, .7], [-.8, 2.7, -.2, .75], [.2, 2.7, -.8, .7], [-.3, 2.5, .7, .6]].forEach(([x, y, z, r], i) => g.add(mesh(new T.IcosahedronGeometry(r, 1), canopyMat[i % 3], x, y, z)));
      const hole = new T.Group();
      const rimGeometry = new T.TorusGeometry(.24, .06, 10, 28); rimGeometry.scale(1, .6, 1);
      const holeRim = new T.Mesh(rimGeometry, mat('#5e4430', {roughness: 1})); holeRim.rotation.x = Math.PI / 2; hole.add(holeRim);
      const cavity = new T.Mesh(new T.CircleGeometry(.23, 28), mat('#2b2016')); cavity.rotation.x = -Math.PI / 2; cavity.scale.set(1, .6, 1); cavity.position.y = -.02; hole.add(cavity);
      const pool = waterDisc(.21, 0, .005, 0); pool.scale.set(1, 1, .6); hole.add(pool);
      const larvaList = larvae(hole, 5, 0, .005, 0, .08);
      // Opening faces the camera, tilted up so the trapped water shows.
      const facing = Math.atan2(2.3, 2.9); hole.rotation.order = 'YXZ'; hole.rotation.set(Math.PI / 2 - .75, facing, 0);
      hole.position.set(Math.sin(facing) * .5, 1.05, Math.cos(facing) * .5); g.add(hole);
      const tag = new T.Mesh(new T.PlaneGeometry(.26, .16), mat(PALETTE.amber, {side: T.DoubleSide})); tag.position.set(Math.sin(facing) * .62 + .25, 1.42, Math.cos(facing) * .62 - .1); tag.rotation.y = facing; g.add(tag);
      return {group: g, camera: [2.85, 2.5, 3.6], target: [.25, 1.25, .3], waters: [], discs: [pool], larvae: larvaList, mosquitoAt: [.55, 1.25, .45],
        fix(f) { const s = clamp(f / .6); tag.scale.setScalar(Math.max(.001, s)); tag.visible = s > .01; }};
    },
  };

  // ---------- renderer ----------
  function makeRenderer(canvas) {
    const T = THREE, renderer = new T.WebGLRenderer({canvas, antialias: true, alpha: true, preserveDrawingBuffer: false, powerPreference: 'low-power'});
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1)); renderer.outputColorSpace = T.SRGBColorSpace;
    renderer.toneMapping = T.NeutralToneMapping ?? T.ACESFilmicToneMapping; renderer.toneMappingExposure = 1; renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;
    return renderer;
  }
  function stage(key) {
    const T = THREE, k = kit(), made = SCENES[key](k), scene = new T.Scene();
    scene.add(new T.HemisphereLight('#fff8ec', '#9fb59a', .95));
    const sun = new T.DirectionalLight('#fff3dc', 2.7); sun.position.set(3.5, 6, 3); sun.castShadow = true; sun.shadow.mapSize.set(1024, 1024);
    Object.assign(sun.shadow.camera, {left: -3, right: 3, top: 3, bottom: -3, near: 1, far: 15}); sun.shadow.bias = -.0008; sun.shadow.radius = 4; scene.add(sun);
    const fill = new T.DirectionalLight('#dbe8ff', .45); fill.position.set(-4, 3, -2); scene.add(fill);
    scene.add(made.group);
    const camera = new T.PerspectiveCamera(34, 1.6, .05, 60);
    const base = new T.Vector3(...made.camera), target = new T.Vector3(...made.target);
    let bug = null; if (made.mosquitoAt) { bug = k.mosquito(); scene.add(bug); }
    const offset = base.clone().sub(target), radius = Math.hypot(offset.x, offset.z), height = offset.y, start = Math.atan2(offset.x, offset.z);
    function frame(t, fixed, orbit) {
      const angle = start + orbit, f = fixed;
      camera.position.set(target.x + Math.sin(angle) * radius, target.y + height, target.z + Math.cos(angle) * radius); camera.lookAt(target);
      made.waters?.forEach(w => { const a = w.geometry.attributes.position, b = w.userData.base; for (let i = 0; i < a.count; i++) { const x = b[i * 3], z = b[i * 3 + 2]; a.array[i * 3 + 1] = b[i * 3 + 1] + Math.sin(x * 14 + t * 3.1) * .004 + Math.cos(z * 18 + t * 2.3) * .003; } a.needsUpdate = true; w.geometry.computeVertexNormals(); });
      made.discs?.forEach((d, i) => { d.material.emissiveIntensity = .16 + Math.sin(t * 2.4 + i) * .05; });
      made.larvae?.forEach(l => { const s = l.userData.seed; l.rotation.y = Math.sin(t * 9 + s * 3) * .9; l.rotation.x = Math.sin(t * 7 + s) * .4; l.position.y = l.userData.y + Math.sin(t * 2 + s) * .004; });
      made.fix(f, t);
      if (bug) {
        const [x, y, z] = made.mosquitoAt, leave = clamp(f * 1.5);
        bug.position.set(x + Math.sin(t * 1.3) * .22 + leave * 1.2, y + Math.sin(t * 2.1) * .05 + leave * 1.4, z + Math.cos(t * 1.1) * .16);
        bug.rotation.y = -t * 1.3 + Math.PI / 2; bug.visible = leave < .95;
        bug.userData.wings.forEach((w, i) => { w.rotation.y = Math.sin(t * 70 + i * Math.PI) * .7; });
      }
    }
    function dispose() { scene.traverse(o => { o.geometry?.dispose(); if (o.material) [].concat(o.material).forEach(m => m.dispose()); }); }
    return {scene, camera, frame, dispose};
  }

  // A live, looping illustration in an element. Returns {setKey, dispose}.
  function live(host, key, {onPhase} = {}) {
    let renderer = null, current = null, raf = 0, t0 = performance.now(), closed = false, orbit = 0, drag = null, phase = null, fixedStill = 0;
    const canvas = document.createElement('canvas'); canvas.className = 'look3d-canvas'; canvas.setAttribute('aria-hidden', 'true'); host.prepend(canvas);
    const ctx2d = canvas.getContext('2d'), dpr = Math.min(2, window.devicePixelRatio || 1);
    const resize = () => { if (!renderer) return; const w = host.clientWidth || 320, h = Math.round(w / 1.6); canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); canvas.style.width = w + 'px'; canvas.style.height = h + 'px'; if (current) { current.camera.aspect = 1.6; current.camera.updateProjectionMatrix(); if (reduced.matches) { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); } } };
    const observer = new ResizeObserver(resize); observer.observe(host);
    canvas.addEventListener('pointerdown', e => { drag = {x: e.clientX, orbit}; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener('pointermove', e => { if (drag) orbit = drag.orbit + (e.clientX - drag.x) / 160; });
    canvas.addEventListener('pointerup', () => { drag = null; });
    function draw(now) {
      if (closed || !current) return;
      const elapsed = (now - t0) / 1000, t = reduced.matches ? 1 : elapsed % LOOP;
      const fixed = reduced.matches ? fixedStill : fixAmount(t), next = reduced.matches ? (fixedStill ? 'done' : 'problem') : phaseOf(t);
      if (next !== phase) { phase = next; onPhase?.(phase, current.key); }
      current.frame(reduced.matches ? 1 : elapsed, fixed, orbit + (reduced.matches || drag ? 0 : Math.sin(elapsed * .35) * .22));
      renderer.render(current.scene, current.camera);
      ctx2d.clearRect(0, 0, canvas.width, canvas.height); ctx2d.drawImage(renderer.domElement, 0, 0, canvas.width, canvas.height);
      if (!reduced.matches) raf = requestAnimationFrame(draw);
    }
    const api = {
      async setKey(next) {
        await load(); if (closed) return;
        if (!renderer) { renderer = sharedLive(); resize(); }
        cancelAnimationFrame(raf); current?.dispose(); current = {...stage(next), key: next}; t0 = performance.now(); phase = null; fixedStill = 0; resize();
        raf = requestAnimationFrame(draw);
      },
      showFix(on) { fixedStill = on ? 1 : 0; phase = null; cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); },
      replay() { t0 = performance.now(); phase = null; cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); },
      dispose() { closed = true; cancelAnimationFrame(raf); observer.disconnect(); current?.dispose(); canvas.remove(); },
    };
    api.setKey(key).catch(() => { api.failed = true; host.classList.add('look3d-failed'); });
    return api;
  }

  // Still thumbnails (the problem state) rendered once per illustration by one shared renderer.
  async function thumbnail(key) {
    if (thumbs.has(key)) return thumbs.get(key);
    const job = (async () => {
      await load();
      if (!thumbRenderer) { const canvas = document.createElement('canvas'); thumbRenderer = makeRenderer(canvas); thumbRenderer.setPixelRatio(2); thumbRenderer.setSize(160, 100, false); }
      const s = stage(key); s.camera.aspect = 1.6; s.camera.updateProjectionMatrix(); s.frame(1.1, 0, 0);
      thumbRenderer.render(s.scene, s.camera); const url = thumbRenderer.domElement.toDataURL('image/png'); s.dispose(); return url;
    })().catch(error => { thumbs.delete(key); throw error; });
    thumbs.set(key, job); return job;
  }

  // ---------- dialog ----------
  let dialog = null, dialogLive = null;
  function ensureDialog() {
    if (dialog) return dialog;
    document.body.insertAdjacentHTML('beforeend', `<dialog id="look-dialog" class="look-dialog" aria-labelledby="look-title"><div class="dialog-top"><h2 id="look-title">What to look for</h2><button class="icon-button" data-look-close aria-label="Close">${icon('x')}</button></div><div class="look-tabs" role="tablist" aria-label="Checklist items"></div><div class="look-stage"><div class="look-caption" aria-live="polite"></div></div><div class="look-actions"><button class="outline-button" data-look-fix hidden>${icon('check')} Show the fix</button><button class="text-button" data-look-replay>${icon('arrow-counter-clockwise')} Replay</button><span class="look-hint">Drag to turn</span></div><p class="look-note">An illustration of the task, not a view of this place. Places to check, not confirmed breeding sites.</p></dialog>`);
    dialog = document.getElementById('look-dialog');
    dialog.querySelector('[data-look-close]').onclick = () => dialog.close();
    dialog.addEventListener('close', () => { dialogLive?.dispose(); dialogLive = null; });
    dialog.querySelector('[data-look-replay]').onclick = () => { dialogLive?.showFix(false); dialogLive?.replay(); };
    dialog.querySelector('[data-look-fix]').onclick = event => { const on = event.currentTarget.getAttribute('aria-pressed') !== 'true'; event.currentTarget.setAttribute('aria-pressed', String(on)); event.currentTarget.innerHTML = on ? `${icon('arrow-counter-clockwise')} Show the problem` : `${icon('check')} Show the fix`; dialogLive?.showFix(on); };
    return dialog;
  }
  function caption(box, key, phase) {
    const c = COPY[key]; if (!c || !box) return;
    box.innerHTML = `<span class="look-step ${phase === 'problem' ? 'is-now' : ''}">${icon('drop')} ${esc(c.problem)}</span><span class="look-step ${phase !== 'problem' ? 'is-now' : ''}">${icon(phase === 'done' ? 'check-circle' : 'hand')} ${esc(c.fix)}</span>`;
  }
  function open(items, index = 0) {
    const list = items.map(text => ({text, key: keyFor(text)})).filter(item => item.key);
    if (!list.length || !supported()) return false;
    const d = ensureDialog(), tabs = d.querySelector('.look-tabs'), stageBox = d.querySelector('.look-stage'), cap = d.querySelector('.look-caption');
    let active = Math.min(Math.max(0, list.findIndex(item => item.text === items[index])), list.length - 1);
    const fixButton = d.querySelector('[data-look-fix]'); fixButton.hidden = !reduced.matches; fixButton.setAttribute('aria-pressed', 'false'); fixButton.innerHTML = `${icon('check')} Show the fix`;
    const select = i => { active = i; tabs.querySelectorAll('[role=tab]').forEach((b, j) => { b.setAttribute('aria-selected', String(j === i)); b.tabIndex = j === i ? 0 : -1; }); d.querySelector('#look-title').textContent = COPY[list[i].key].title; caption(cap, list[i].key, 'problem'); dialogLive?.setKey(list[i].key); fixButton.setAttribute('aria-pressed', 'false'); fixButton.innerHTML = `${icon('check')} Show the fix`; };
    tabs.innerHTML = list.map((item, i) => `<button role="tab" aria-selected="${i === active}" tabindex="${i === active ? 0 : -1}">${esc(item.text)}</button>`).join('');
    tabs.querySelectorAll('[role=tab]').forEach((b, i) => { b.onclick = () => select(i); b.onkeydown = e => { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); const n = (i + (e.key === 'ArrowRight' ? 1 : -1) + list.length) % list.length; select(n); tabs.querySelectorAll('[role=tab]')[n].focus(); } }; });
    dialogLive?.dispose();
    dialogLive = live(stageBox, list[active].key, {onPhase: (phase, key) => caption(cap, key, phase)});
    d.querySelector('#look-title').textContent = COPY[list[active].key].title; caption(cap, list[active].key, 'problem');
    if (!d.open) d.showModal();
    return true;
  }

  // ---------- list decoration ----------
  // Each checklist line gets a 3D thumbnail button; tapping it opens the animated illustration.
  function decorate(root) {
    if (!root || !supported()) return;
    const groups = [...root.querySelectorAll('.shared-checklist ul, .stop-checklist')];
    groups.forEach(group => {
      const rows = group.matches('ul') ? [...group.querySelectorAll('li')] : [...group.querySelectorAll('label')];
      const texts = rows.map(row => (row.querySelector('span') || row).textContent.trim());
      rows.forEach((row, i) => {
        const key = keyFor(texts[i]); if (!key || row.querySelector('.look-thumb')) return;
        const button = document.createElement('button'); button.type = 'button'; button.className = 'look-thumb'; button.dataset.lookKey = key;
        button.setAttribute('aria-label', `See what to look for: ${texts[i]}`); button.innerHTML = `<span class="look-thumb-art" aria-hidden="true">${icon('cube')}</span>`;
        button.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); open(texts, i); });
        row.prepend(button);
      });
    });
    const pending = [...root.querySelectorAll('.look-thumb:not([data-ready])')]; if (!pending.length) return;
    const paint = button => { button.dataset.ready = '1'; thumbnail(button.dataset.lookKey).then(url => { button.querySelector('.look-thumb-art').innerHTML = `<img src="${url}" alt="" width="64" height="40">`; }).catch(() => {}); };
    const io = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { io.unobserve(entry.target); paint(entry.target); } }), {rootMargin: '200px'});
    pending.forEach(button => io.observe(button));
  }

  window.Checklist3D = {keyFor, supported, decorate, open, live, thumbnail, copy: key => COPY[key] || null, LOOP, three: load};
})();
