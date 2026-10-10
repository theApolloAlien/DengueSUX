# DengueSUX SaaS overhaul — 10 October 2026

The local product overhaul is implemented on `design/saas-overhaul`. It uses vanilla JavaScript and CSS with no new runtime dependency or build step. No forecast, model recipe, pipeline, source observation or data artifact was changed. No push or deployment was performed.

## What changed

- Four job-based sections: This week, Map, Field plan and Forecast. Desktop has a labelled, collapsible sidebar; phones have bottom navigation. The top bar has a breadcrumb, dated cluster freshness, Help and Ask.
- This week leads with the saved national forecast and range, then the five highest-ranked areas, actual snapshot changes and resident lookup. Map has list and sortable-table alternatives.
- Section, area and plan hashes work with back/forward. The command palette has fuzzy area search, recent actions, section jumps, planning, postal lookup, copy link and Ask prefilling. Keyboard chords and shortcuts are documented in Help.
- Field plans retain the source-backed route, 3D walk, dated checklist, reports and notices in all four languages. Report controls open on demand. The print sheet uses exact saved OneMap geometry and all numbered stops, fitting one A4 page for Jurong West and Bukit Batok. Copy link has a manual fallback when browser clipboard access fails.
- Forecast leads with the current outlook; retrospective checks and the 2022 replay remain available in a disclosure. Missing/expired forecasts remain unavailable.
- Semantic tokens, component states and the hidden `#styleguide` route establish a reusable system. DM Sans and Phosphor remain locally vendored.
- Skeleton structure paints without data; loading animation/copy starts after 300 ms, slow-load copy after four seconds, and the existing timeout leads to Retry. Artificial assistant and notice delays were removed. Offline and saved-map labels remain explicit.
- View transitions, count-up on initial load, row entrances, map fly-to, route stroke draw, chart reveal, checklist ring and toasts use native APIs with reduced-motion fallbacks. No data is invented to animate a number.
- Three skippable coach marks show once on the home route. Shared deep links retain their destination. Help replays the tour and `?tour=1` forces it. Storage failure is non-fatal.
- A generated brand concept sheet, hand-built SVG logo/wordmark with light/dark variants, favicon set, manifest, eight editorial illustrations, a real-app hero and a 1200×630 social card. The export embeds static and dynamically rendered brand images.

## Visible copy

Measured with `document.body.innerText.trim().split(/\s+/).length`, desktop 1440, dialogs and secondary disclosures closed. These count all rendered page text, including content below the fold. First-run tour is dismissed. The old area screen is the baseline for both new home and map because those jobs previously shared one screen.

| Section | Before | After | Reduction |
|---|---:|---:|---:|
| This week / old area entry | 352 | 146 | 58.5% |
| Map / old area entry | 352 | 210 | 40.3% |
| Field plan, Jurong West | 444 | 251 | 43.5% |
| Forecast | 390 | 99 | 74.6% |

Cut: duplicate navigation, the opening kicker/subtitle, competing stat tiles, repeated per-stop report questions, repeated building metadata, visible model machinery and redundant explanatory text. Source details remain in disclosures and How to read this. No coverage was deleted.

## Honesty statements

- “Places to check, not confirmed breeding sites”: once in the visible app footer; a self-contained version remains in printed plans and resident notices.
- “Past error, not a guarantee”: alongside the 80% range on This week and Forecast (one per visible section).
- Saved snapshot: header chip and its exact-date/source dialog. Saved maps and unavailable forecasts are explicitly labelled. The chip never pulses as live.
- Shared clusters overlap: visible on Map. Population rates remain context, not personal risk. Historical model selection, limitations and missing weather disclosure remain available.

## Verification evidence

- **165 Python tests passed**, 38 pre-existing dependency warnings. `final-tests.txt`. JavaScript syntax checks passed.
- **61 journey checks**, no uncaught JavaScript errors: `verification.json`. **21 edge checks**, no console or page errors: `edge-checks.json`. **5 phone focus/privacy checks**: `mobile-edge-checks.json`. **19 existing platform/3D checks passed** after updating navigation selectors: `platform/platform_states.json`. No field report or personal location was submitted.
- Screenshots: `before-*`, `after-*` at 1440, 1024 and 390, plus 1280. Loading/error captures for all four routes, offline, notices, assistant, 3D, table and portable export. Baseline screenshots were recaptured from the pre-overhaul commit with animations disabled to avoid capturing an entrance mid-fade.
- Real flow recordings: six named files in `videos/`, judge/coordinator/resident × normal/reduced motion. Coordinator recordings independently assert the copied clipboard contains the checked notice. Resident recordings use a public example, not a personal address.
- Print: `field-sheet.pdf` and `field-sheet-bukit-batok.pdf`, both one A4 page. All numbered stops are in the print geometry. A print-specific Leaflet crop was found and replaced with a vector projection of the saved route.
- Portable export: `output/denguesux.html`, verified under `file://` with network blocked, including embedded logo, map, and empty-state image.
- Databricks package: built locally at `/tmp/denguesux-saas-package`, 86 files, about 18.9 MB. New CSS/JS/brand files included. The hosted postal capability is tested false and hides postal lookup.
- Core task clicks, after dismissing tour: planning the highest-priority area 1 (previously 1 for the already selected top area); plan + resident notice + copy 3 (previously 3); checking the public block example 1 (previously 1); national forecast 1 (previously 1). The benefit is visibility and direct links, not a fabricated reduction in click counts.

## Performance

Cold synthetic Chromium run, 1.6 Mbps downstream / 0.75 Mbps upstream / 150 ms latency, 4× CPU slowdown. Single-run figures are not field Core Web Vitals. INP proxy is the largest Event Timing duration from the tested resident interaction, not real-user INP. `final-performance.json`.

| Viewport | Metric | Before | After |
|---|---|---:|---:|
| 1440 | First contentful paint | 636 ms | 820 ms |
| 1440 | Largest contentful paint | 636 ms | 8,096 ms |
| 1440 | App data ready | 7,161 ms | 7,693 ms |
| 1440 | CLS | 0.0231 | 0.0039 |
| 1440 | Interaction proxy | 64 ms | 40 ms |
| 390 | First contentful paint | 620 ms | 1,000 ms |
| 390 | Largest contentful paint | 620 ms | 8,080 ms |
| 390 | App data ready | 7,157 ms | 7,663 ms |
| 390 | CLS | 0.1369 | 0.0029 |
| 390 | Interaction proxy | 56 ms | 56 ms |

The redesign improves layout stability substantially but does **not** improve FCP or LCP. The new illustrated hero makes the late-arriving foreground and background the largest content, whereas the old LCP was opening shell/loader text. Data readiness is about half a second later after the image expansion; the 914 KB compressed dashboard remains the dominant slow-network cost. Splitting the large geometry artifact would be a separate data-delivery change. New unminified JavaScript is 30,448 bytes net (about 30 KB); no new library was added.

## Deviations and deliberately omitted work

- The user explicitly requested autonomous building, so Phase 0's suggested approval pause was not applied. The audit, mock and proposal are retained for review.
- Built-in raster image generation was unavailable. The user explicitly authorized the codex-easy.ai fallback, then requested more brand assets and a complete visual refinement. The unmodified local runner generated nine images (one three-concept logo sheet plus eight illustrations) with `gpt-image-2`, high quality, concurrency 2. The key was provided only through the child-process environment and was never printed or written. Raw sources, exact prompts, actual dimensions and SHA-256 hashes are recorded under `output/imagegen/denguesux/`. The middle D/home concept was simplified and rebuilt as SVG. The social card and cover add type locally; generated sources contain no text, data, maps or people.
- Plans, notices and footprints already arrive inside `dashboard.json`; no redundant hover-prefetch request was added. 3D runtime assets still load only on demand. There is no invented plan-generation progress for a saved route.
- Progressive data reveal is limited by the existing single dashboard response. The shell paints first; map layers have visual entrances once actual data exists. Separate network-arrival stages are not claimed.
- The chart uses a clipped reveal with the range band and marker staged afterward. The native checkbox uses its own check drawing, with row feedback and a real progress ring; no custom fake checkbox replaces it. Sidebar indicator and map selection move, but there is no shared-element selected-row transition or finger-tracking drawer gesture.
- The style guide demonstrates tokens and components, representative states, and working layers; it does not enumerate every component/state cross-product. Full screen-reader certification, every browser engine and hardware 60 fps certification are not claimed.
- External OneMap tiles can fail; saved route geometry and stops remain available. Existing data/forecast freshness limits remain unchanged.
- Optional overview, full app dark mode and presenter mode were deliberately not added because Parts A–F have documented departures. Light/dark logo variants are brand assets, not an app dark-mode claim. The new cover and hero are deck-ready; pre-existing modified PDF/PPTX files were preserved.
- No pricing, sign-in, testimonials, fake notifications, generated maps, fabricated counts or model changes were introduced.

## Local review

Open `http://127.0.0.1:8787/#week`, `#map`, `#plan/jurong-west`, `#forecast`, or `#styleguide`. Use `?tour=1#week` for the tour. Review the report and screenshots before deciding on any publication.

## Expanded brand pass

On the user’s follow-up request, the site now uses a low-contrast courtyard illustration behind the weekly outlook, a field-kit illustration in the area picker, a calendar illustration beside the forecast sources, a corridor illustration in Our story, and generated empty/error/no-cluster spots. The mobile header retains the brand mark. Spacing, buttons, rows, dialogues and type were refined across the existing sections. Map and chart data layers remain untouched.

`brand-verification.json`: 20 route/viewport combinations (1440, 1280, 1024, 390), with no document overflow, no broken brand images and no JavaScript exceptions. `branded-*.png` contains the final captures. The six recordings were refreshed after the brand pass. New artwork never substitutes for an observed map or a forecast.

Deliverables: `app/web/brand/brand-sheet.png`, `cover.png`, `og-card.png`, light/dark SVG and PNG wordmarks, optimized WebP illustrations, and `output/design/saas/denguesux-brand-kit.zip`. Usage guidance: `app/web/brand/BRAND.md`. Final prompts: `output/imagegen/denguesux/prompts.jsonl`.
