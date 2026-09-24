# UI / UX experience pass — 24 September 2026

final result: passed

Scope: improve the existing app, preserving the forest-green identity as explicitly requested. This is an experience refinement, not a pixel-for-pixel recreation or a complete accessibility certification.

## Current evidence

- Existing visual grounding: `output/design/review/denguesux-polish-desktop.png` (earlier pass captured this session, 1280 × 720, DPR 1). It is not an untouched pre-edit baseline.
- Final matched view: `output/design/experience/12-map-1280.png` (1280 × 720, DPR 1), same initial area and data. Combined comparison: `output/design/experience/comparison.png` (two 1280 × 720 views with a label strip). Both images and the combined comparison were inspected.
- Full desktop: `01-map-desktop.png`, `02-plan-desktop.png`, `03-notice.png`, `04-forecast-desktop.png`, `05-assistant.png`, `08-loading.png`, `09-error.png`, `10-standalone.png` under `output/design/experience/`, 1440 × 1000, DPR 1.
- Mobile: `06-map-mobile.png`, `07-forecast-mobile.png`, `11-mobile-map-controls.png`, `13-webkit-mobile.png`, 390 × 844, DPR 1. Mobile Chrome and WebKit rendering inspected. Document overflow checked at 900, 390 and 325 CSS pixels.
- Focused states (notice dialog, loading state, mobile map controls and assistant) were inspected at native dimensions; individual views provide readable details beyond the reduced combined comparison.

## Flow results

1. Entry and loading — passed. Branded indeterminate loader appears during a delayed request. Real completion removes it without an artificial delay; busy semantics clear on success and failure. Timeout and retry guidance supplied.
2. Area discovery — passed. Visible view navigation; larger names and controls; empty search has a working reset. Selection updates detail and map. Mobile drawer focuses search and returns focus on close.
3. Inspection — passed. Checklist progress updates and restores from existing dated session storage. Focus moves to the plan heading; return restores the plan action.
4. Resident notice — passed. Loading feedback, readable draft and 5/5 checks; copy is enabled for the checked English draft. No notice was sent.
5. Forecast — passed. Historical 2022 context stays explicit. Slider keyboard End selects the final week; replay advances and pauses.
6. Assistant — passed. Answers render with sources. Header placement avoids obscuring map, chart and inspection actions. Mobile panel uses dialog semantics, traps focus and makes the background inert; closing restores access.
7. Portable HTML — passed. Regenerated with all experience styles and scripts; renders the same source-backed data.

## Findings and iteration

- P2 fixed: initial floating assistant covered content on short screens. First reduced its phone footprint, then moved the entry into the header after the matched 1280 comparison showed a remaining collision. Final matched capture confirms primary action is unobstructed.
- P2 fixed: phone map zoom and assistant collided. Zoom moved left; final native-size mobile capture confirms control separation.
- P2 fixed: small list metadata/controls and icon-only desktop navigation reduced discoverability. Increased control text and target sizes, surfaced labeled view tabs and added a short task introduction. Intentional increase in vertical space accepted for clearer navigation; short viewports scroll normally.
- P2 fixed: empty searches lacked an actionable recovery. Reset restores all 55 areas and returns focus to search.
- P2 fixed: load failures exposed pipeline instructions. User-facing copy now offers retry guidance; errors still log technical details to console.

## Required design surfaces

- Typography: existing local DM Sans retained; no extra font downloads. Stronger headings, 12–14px working text, larger touch inputs. Supplementary chart/map labels remain compact.
- Layout: existing list/map/detail arrangement retained; wider list, generous controls, consistent restrained elevation. Mobile stacks map/detail; no measured horizontal overflow.
- Tokens: forest/ivory identity and restrained amber/terracotta priorities retained. Low/Medium/High also appear in text. Secondary copy darkened; no full contrast-certification claim.
- Assets: existing Phosphor aperture, icon font, DM Sans and actual map geometry reused. No new generated brand imagery, fabricated maps, or external asset service needed.
- Content: real artifact counts and source dates preserved. No saved snapshot is called live. Inspection completion describes checklist actions only. National model remains a 2022 backtest.
- Motion: bounded brand pulse, loading indicator, brief view/detail/panel entrances, and hover feedback. Reduced-motion disables animation and transitions.

## Validation and limits

83 Python tests passed (existing dependency deprecation warnings). JavaScript syntax checks passed. 24 browser assertions passed with no uncaught JavaScript errors; details in `output/design/experience/checks.json`. Additional mobile focus, control separation and WebKit rendering checks passed. Expected simulated HTTP failure was exercised; no zero-network-error claim is made. Live external route tile availability can vary. Full screen-reader audit and every translated notice were outside this UI pass.

Implementation complete; no actionable P0/P1/P2 findings remain within the verified scope. Durable notes: `output/design/experience-notes.md`.

---

Earlier verification history (not evidence for the current experience pass):

# DengueSUX review verification — 24 September 2026

This record supersedes earlier design checks and model results below.

The current revision uses the original locked equal-year 2019–2021 selector and MLflow run `ef02042b46d74bde9e46c60962f71e1c`. A separate older task briefly overwrote model/spatial artifacts during QA; it paused, and the verified implementation and saved predictions were restored. Final source/export hashes are in `output/revision_manifest.json`.

## Evidence and model

- 42 tests pass. Tests cover temporal leakage, selected-model explanations, missing weather, null construction metadata, geometric intersections, area ordering and snapshot/label contracts.
- Independent persisted Delta verification passes: 574 national weeks, 304 feature origins, 52 evaluation weeks, 17,215 area weeks. Persisted predictions/priorities match the application JSON.
- Exported MLflow predictor reload reproduces all 52 saved predictions exactly (`output/model_roundtrip.json`).
- Gradient boosting selected across 39 rolling validation folds spanning 2019–2021. 2022 error 83.2 people/week versus 172.4 baseline; first High issued 11 versus 10 weeks before peak. The reused evaluation year and reporting-date assumption are documented.
- Every positive-area cluster intersection is included: shared 74-person cluster spans Jurong West and Jurong East. National 11 clusters/101 people; 12 area associations/175 people (intentionally overlapping).
- Top 5: Jurong East, Jurong West, Bishan, Bukit Merah, Hougang. Missing weather is unavailable and contributes zero; no construction component is scored.

## Browser checks

Verified in the authorized Codex in-app browser, live app and regenerated standalone `/prototype.html`.

- Desktop 1440×1000, intermediate 900×900 and mobile 390×844 show no horizontal document overflow.
- At 900px the banner is 786px wide and 41px tall. At 390px it is 350px wide and 56px tall; words remain normally wrapped.
- Both navigation buttons work; lower forecast sections remain visible with opacity 1, without scroll-reveal dependencies.
- Map initially fits all Singapore. Resizing while Forecast lab is open and switching back correctly restores map bounds.
- Circles scale from about 23px for 2 people to 59px for 74 people; amber/red areas retain legible labels.
- Briefing identifies the shared Jurong cluster. Where/Why/What to do select the top area and move to the correct content; What to do transfers focus to its card.
- Top 5 opens the five ranked areas; search/filter and selected area remain interactive.
- Jurong West displays 35.0mm rain, 27.0°C temperature and 88.5% humidity with 3/3 metrics available; station names/distances/readings are available in the expandable weather section.
- NEA B-L-O-C-K checkboxes work on mobile. Guidance is linked to NEA and says to check at least weekly.
- Replay advances through weeks, pauses, and stops on manual slider selection. Keyboard End selects 25 December. Peak/first-High chart annotations and grouped explanations render.
- How to read this opens/closes; About uses the selected model. Main screens omit public index points and repeated research caveats.
- Standalone displays the same ~83/~172 error, 11-week warning and corrected area data. No console errors or warnings observed.

## Screenshots

- `output/design/review/map-desktop.png`
- `output/design/review/forecast-desktop.png`

## Limits

Databricks Free Edition execution remains untested. This is a historical national replay and dated current cluster map, with assumed local priorities; it does not establish current national forecasts or measured local prediction accuracy. Deck/gallery synchronization is outside this product revision.

---

# DengueSUX design and interaction verification

**Final result: passed**

Original design, verified in the Codex in-app browser on 24 September 2026. The user explicitly asked for our own visual direction and rejected the existing slide deck as a visual reference. There is therefore no source-mock fidelity claim. The design target was the agreed warm ivory/forest, map-first workspace, restrained risk colours, responsive layout, real geography and clear separation of current priorities from historical forecasting. The unavailable Image Gen selection step was explicitly bypassed by the user's direction.

## Evidence

- Desktop: `output/design/desktop-top-final.png`, `output/design/desktop-bottom-final.png`; 1440 × 1000 CSS viewport and screenshot pixels, device pixel ratio 1. The two actual viewport captures cover the whole page. `desktop-final.png` is an overview stitch; fixed navigation repeats in the stitched margin, so the individual viewport captures are the authoritative evidence.
- Desktop forecast: `output/design/forecast-desktop.png`, 1440 × 1000, 1:1. Actual case curve, candidate and baseline were inspected, along with selected-week values and explanations.
- Mobile before: `output/design/mobile.png`; after: `output/design/mobile-final.png`, both 390 × 844 CSS/pixels, DPR 1, initial area view.
- Mobile map/detail: `output/design/mobile-map-final.png`, same 390 × 844 viewport, scrolled 422 CSS pixels.
- Same-input before/after comparison: `output/design/mobile-comparison.png`, two aligned 390 × 844 captures with labels. Opened and visually inspected together.
- Focused map/detail evidence is the mobile map capture and desktop bottom viewport. These make labels, legend, source attribution, area cards and controls readable.

The browser's `fullPage` capture rendered at inconsistent density in this environment; those initial captures were not used to judge the design. Native viewport screenshots were used instead. A transient browser zoom change was also discarded; final mobile evidence came from a fresh in-app tab at the measured 390 × 844 / DPR 1 settings. Temporary viewport overrides were reset after QA.

## Findings and fixes

1. **P2, fixed — mobile overview cropped geography.** The initial minimum map zoom prevented the complete island boundary from fitting. Lowered the minimum zoom, used consistent map padding, and refit when the viewport changes. The after capture and scrolled map show the full geometry. Label density is reduced at the widest overview.
2. **P2, fixed — mobile area drawer lacked an explicit close control.** A search with no results left users without an obvious return to the map. Added a labelled Close area list button and Escape handling. Verified an empty search and closing the drawer, then searching/selecting Tampines; selection closes the drawer and updates the detail.
3. **P2, fixed — model/UI contract initially differed.** Mapped actual metric names, risk bands, origin/issue dates and SHAP values; now the actual 52-week series is shown. The validation-selected baseline remains prominently labelled even though the candidate wins the held-out test. There are no placeholder metrics.
4. **P2, fixed — portable bundle had incomplete vendor assets.** Included Leaflet's referenced image assets and a local WOFF2 icon font. The final 2.6 MB HTML loads with embedded data, styles, fonts and scripts and no linked stylesheet/script dependencies.

No actionable P0/P1/P2 issues remain in the verified scope.

## Required visual surfaces

- **Typography:** Local DM Sans, consistent weights and hierarchy, readable mobile wrapping, no fallback-font flashes in final captures. Small map labels are supplementary; the searchable area list provides full names and priority text.
- **Spacing/layout:** Consistent ivory workspace, aligned four-column desktop metrics and two-column mobile metrics; desktop area browser/map/detail become a map plus detail flow on phones. No horizontal overflow at the measured 1440, 741, 390 or narrow 325 CSS widths. Long area details scroll within the desktop panel.
- **Colours:** Forest text/navigation, restrained green/amber/terracotta priority colours; priority is also written as Low/Medium/High so it is not conveyed by colour alone. Keyboard focus styles and reduced-motion support are present.
- **Assets:** Actual URA GeoJSON renders through Leaflet; no fabricated map illustration. Phosphor icons and DM Sans are vendored with notices. No remote tiles, generated photos, missing-image placeholders or deck imagery.
- **Copy/content:** Current local scores are labelled heuristic. Cluster counts are explicitly not weekly incidence. Weather date, snapshot retrieval date and cluster feature dates are separate. National metrics are clearly a 2022 backtest. Model-selection tradeoff, assumed report availability and lack of local accuracy are disclosed. No synthetic observations or outcomes.

## Interactions verified

- Area search narrows to Tampines; selecting it changes the detail and map selection.
- High filter returns the two actual high-priority areas; All restores 55. Empty search state has useful recovery text.
- All Singapore resets the map; cluster and priority layer toggles work. The 74-case marker opens the real locality and update-date popup and selects Jurong West.
- Desktop/mobile view tabs switch between current area signals and historical Forecast lab.
- Timeline keyboard Home changes the selected target to 2 January 2022; chart click changes it to 26 June and updates actual/predicted/baseline values and SHAP drivers.
- Source notes dialog opens/closes and shows retrieval 24 September, weather 23 September and feature updates 14–18 September 2026, plus national band thresholds.
- Export data triggers a real JSON download and confirmation toast.
- Standalone bundle loaded independently of the API payload endpoint, displayed 55 areas and 52 predictions, and supported mobile search/selection and forecast navigation.
- Browser console checked after the core flows and standalone load: no application errors or warnings captured.

## Implementation checks

- Eight Python tests passed, covering the epidemiological calendar, temporal purge, imputation, spatial assignment/conservation, daily snapshot idempotence and API/static serving.
- Full local PySpark/Delta bronze → silver → gold execution succeeded. Independent persisted-output audit passed: 574 national weeks, 17,215 area-weeks, 304 feature origins, 52 test predictions; recomputed metrics and SHAP additivity agree.
- Pure-Python snapshot downloader successfully retrieved the genuine 11-feature, 20,386-byte source. Saved daily snapshot reuse passed checksum validation.
- JavaScript syntax and Python compilation passed; HTML bundle regenerated after the final visual fixes.

## Remaining scope limits

Databricks Free Edition execution has not been performed in a live workspace; the README documents serverless configuration and that limitation. This was a browser functional/design check, not a complete screen-reader audit or epidemiological validation. Local priorities have no historical outcomes against which to validate accuracy. Publication and deployment were not part of this phase.
