# Two-week planning-area outlook

**Question it answers:** which planning areas are likely to have an active dengue cluster, or 10 or more people in clusters, about two weeks from now?

## Why this needed new data

The A2 brief asks for a forward-looking Low/Medium/High per planning area. data.gov.sg publishes only today's NEA cluster GeoJSON, so there was no area-level history to learn from. NEA's own listing page prints every active cluster with its locality, cases since the cluster started, cases in the last two weeks and, since 2019, the cases at each block or street. The Internet Archive saved that page on 68 distinct days between February 2019 and September 2026.

- `scripts/collect_nea_cluster_archive.py` saves every capture byte for byte with a SHA-256 receipt (`data/raw/dengue/nea_cluster_archive/`).
- `denguesux/cluster_archive.py` parses both page layouts (the 2019–2022 rowspan table and the 2023+ nested details table).
- Each location is placed with official data only, in this order: exact HDB block and street on an HDB footprint (53% of listed cases); an HDB block on an unverified street code through its HDB town (0.4%); a street whose HDB blocks mostly sit in one planning area (8%); an exact road-name match on OneMap public search (37%). 1.4% of listed cases stay unlocated and are counted, never guessed.
- A cluster counts in every planning area that holds one of its locations, matching the live map's rule for shared clusters.
- The 73 listed days (archive plus daily data.gov.sg snapshots since 24 Sep 2026) form `silver_area_cluster_history`. Days that were not captured are missing, not zero.

## Model

Two L2 logistic regressions (scikit-learn) on standardised features known on each listing date:

| Group | Features |
|---|---|
| People in clusters here now | log people in clusters, log cluster count, clusters with 10+ people |
| This area's track record | share of earlier listings with a cluster in this area (earlier listings only) |
| National trend | latest published national weekly count (log) and its two-week change |
| Recent rain | national rainfall over the previous 28 days |
| Time of year | sine and cosine of day of year |

Targets come from the listing 10–21 days later, closest to 14. Band = High when 10+ people is at least 50% likely, otherwise Medium when any cluster is, otherwise Low, so the band never contradicts the chances shown.

## Validation (leave one origin year out)

1,100 area examples from 20 listing pairs, June 2020 to September 2026.

| Measure | Model | Persistence (band stays the same) | Area track record only |
|---|---|---|---|
| Brier score, any cluster | **0.110** | 0.136 | 0.161 |
| Brier score, 10+ people | **0.065** | 0.075 | 0.139 |
| AUC, any cluster | **0.92** | 0.85 | 0.85 |
| AUC, 10+ people | **0.96** | 0.89 | 0.84 |
| Band accuracy | 79.4% | **81.5%** | 70.1% |
| Areas that newly reached High, flagged High | **12 of 44** | 0 of 44 | — |

The honest reading: the band alone is about as good as assuming nothing changes, because most areas stay in the same band for two weeks. The model's value is in calibrated chances and in ranking areas that are about to become hotspots, which persistence cannot do.

## Limitations

- Archived captures are irregular; only pairs 10–21 days apart are used, and listings within one capture are not independent.
- Archived clusters are placed by their block or street breakdown; the live map uses polygon overlap. People in clusters count cases since a cluster started, not weekly incidence.
- This is a check-first outlook, not a case forecast. Places to check are not confirmed breeding sites.
- Every daily outlook is recorded in the append-only ledger and scored about two weeks later, so a real track record accumulates from 13 Oct 2026.
