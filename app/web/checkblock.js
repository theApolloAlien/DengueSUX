/* Shared browser-only geometry. Polygon holes and MultiPolygons are respected. */
(() => {
  // Equirectangular metres around Singapore: accurate to well under 1% at these distances.
  const toXY = (lat, lon, lat0) => [lon * 111320 * Math.cos(lat0 * Math.PI / 180), lat * 110540];
  function segmentDistance(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / (dx*dx + dy*dy || 1)));
    return Math.hypot(p[0] - a[0] - t*dx, p[1] - a[1] - t*dy);
  }
  function inside(pt, ring) {
    let hit = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi) hit = !hit;
    }
    return hit;
  }
  function distanceToCluster(lat, lon, geometry) {
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
    const p = toXY(lat, lon, lat);
    let best = Infinity;
    for (const polygon of polygons) {
      const rings = polygon.map(ring => ring.map(([x, y]) => toXY(y, x, lat)));
      if (inside(p, rings[0]) && !rings.slice(1).some(r => inside(p, r))) return 0;
      for (const ring of rings) for (let i = 1; i < ring.length; i++) best = Math.min(best, segmentDistance(p, ring[i-1], ring[i]));
    }
    return best;
  }
  window.CheckBlock = {distanceToCluster, inside, segmentDistance};
})();
