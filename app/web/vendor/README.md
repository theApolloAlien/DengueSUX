# Local frontend dependencies

The dashboard does not need a public CDN at runtime.

- Leaflet 1.9.4: https://leafletjs.com/ — BSD-2-Clause, included in leaflet/LICENSE.
- Phosphor Icons web 2.1.2: https://phosphoricons.com/ — MIT, included in icons/LICENSE.
- DM Sans font: https://fonts.google.com/specimen/DM+Sans — SIL Open Font License, included in fonts/OFL.txt.
- MapLibre GL JS 5.6.1: https://maplibre.org/maplibre-gl-js/ — BSD-3-Clause and bundled dependency notices, included in maplibre/LICENSE.txt. JavaScript and CSS copied from the official `maplibre-gl@5.6.1` npm tarball after SHA-512 integrity verification; receipt and file SHA-256 hashes are in maplibre/receipt.json. Loaded locally on demand for the optional 3D inspection view.
- three.js r169 (`three@0.169.0`): https://threejs.org/ — MIT, included in three/LICENSE. `three.module.min.js` copied from the official npm tarball after SHA-512 integrity verification; receipt in three/receipt.json. Loaded on demand (dynamic import) for the 3D checklist illustrations.

The area overview uses genuine URA planning-area GeoJSON. Inspection maps use public OneMap raster tiles and retain source shapes/markers if tiles fail. No map key or OneMap token is sent to the browser. The 3D view uses genuine HDB Existing Building shapes for the route and nearby HDB blocks; heights are estimates from published storeys × 2.8 m + 1.3 m roof (NUS Urban Analytics Lab convention), and unknown heights stay flat.
