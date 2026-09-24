Frontend implementation complete; ready for root browser verification at http://127.0.0.1:8787.

- Static HTML/CSS/JS in app/web. Local Leaflet + Phosphor icons + DM Sans fonts; licenses included. No remote tiles, CDNs or map keys at runtime.
- Fully adapted exact current.json contract: list areas, real boundaries GeoJSON, nearest-station weather, reasons, centroid lat/lon, cases cluster properties.
- Fully adapted exact model.json contract: candidate MAE/accuracy, baseline MAE, chronological counts, target/origin week, SHAP value contributions.
- Prominent validation-pick banner keeps recommendation Four-week average even though candidate wins test. Candidate comparison and per-point explanations shown separately.
- Full SHAP importance chart ready for feature_importance export. No synthetic fallback values.
- Area map/list selection, search, priority filters, map reset, layer switches, weather details, forecast chart hover/click + range slider, methodology modal, JSON download, view tabs and mobile area overlay work.
- window.DENGUESUX_DATA supported for bundled HTML. Normal mode fetches /data/dashboard.json.
- node --check passed. Browser QA deliberately left to root to avoid competing browser session.

Potential exporter note: CSS url(/vendor/fonts/...); styles may need base64 rewrite; Phosphor CSS includes optional fallback files absent locally, but WOFF2 exists and is loaded by all modern browsers.
