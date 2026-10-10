# DengueSUX product overhaul

The autonomous build request supersedes the brief's Phase 0 approval pause. No deployment or push is part of this work. Model and data artifacts remain untouched.

## Baseline findings

1. Duplicate rail and tab navigation consumes vertical space.
2. The map starts below 600 px on desktop.
3. Four equal metrics compete; the national forecast has little emphasis.
4. The opening kicker and subtitle repeat the product purpose.
5. Snapshot totals and local cluster figures need clearer separation.
6. The 55-area search is hidden on mobile.
7. Planning requires discovering a selected-area action.
8. Field reports repeat a question and three actions eight times.
9. Retrospective forecasting competes with the current national outlook.
10. The loader describes a staged process even though loading is one request.

## Proposed structure

- This week: headline based on High areas; national outlook and its range; five ranked areas; change feed; resident lookup.
- Map: search/list or sortable table; geographic context and selected-area actions.
- Field plan: area picker; existing saved route and checklist; notice, print and share link.
- Forecast: national outlook first; retrospective/replay behind a disclosure.

## Wireframes

This week: [labelled sidebar] [breadcrumb / freshness / Ask] → [answer headline] → [large national outlook | top five area rows] → [snapshot change / resident check].
Map: [same shell] → [55 areas / view switch] → [search list | map | selected area]. Table swaps the list/map region.
Field plan: [same shell / selected area] → [picker / share / notice / print] → [route | checklist].
Forecast: [same shell] → [current expected people / range / last report] → [expand retrospective → chart / replay / evidence].

Baseline word counts and timing are in before-metrics.json. Fast 4G dashboard transfer: 914,342 bytes, approximately 5.1 seconds. Measurements are local synthetic runs, not field performance. The original mobile CLS was 0.132.
