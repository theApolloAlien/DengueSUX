# Who DengueSUX helps, and how much

## The people and the decisions

| Who | Decision DengueSUX informs | What they use |
|---|---|---|
| NEA officers and town council estate teams | Which areas and blocks to inspect first this week, and which to watch for the next two weeks | Area ranking, two-week area outlook, field plans with routes and checklists, SQL alerts, AI/BI dashboard |
| Residents' Committees and volunteer groups | Where to walk on Saturday, what to look for at each stop, what to tell neighbours | 3D walk preview, printable field sheet, lift-lobby poster, WhatsApp text, per-area alert feed, Telegram alerts (@DengueSUXbot) |
| Residents | Is my block near a cluster, and what can I do today? | Private postal check (runs in the browser), care guidance in four languages, myENV handoff |

## What exists today (13 Oct 2026, real data)

| Measure | Value |
|---|---|
| Planning areas with a walk route or flyover | 55 of 55 |
| Places to check across all walks | 311 stops |
| HDB homes in the blocks along those routes | about 32,400 flats |
| Homes in this week's three cluster-plan routes | 2,821 flats (3,225 in the cluster blocks themselves) |
| Resident notices drafted | 220 (55 areas × English, Chinese, Malay, Tamil), each with 5 fact checks |
| Days of area-level cluster history | 73 listed days since February 2019 |

Homes count HDB flats only (HDB Property Information); private housing is not counted, and flats are not residents at risk.

## Why it could realistically be adopted

- **Runs on what agencies already have.** Open government data, Databricks Free Edition serverless, and a web app that works on a phone. No new sensors, no personal data collected.
- **Honest by design.** Places to check, never "confirmed breeding sites". Every number is dated and sourced. Forecasts show ranges; the ledger shows what we said and what happened.
- **Closes the loop.** Field reports land in a Unity Catalog table, feed the next morning's plan (stops with water found are re-checked first) and show up as coloured beacons in the 3D walk.
- **Reaches people who are hard to reach.** Outreach notes flag areas with many residents aged 65+ or living in 1–2-room flats (SingStat June 2026), where printed posters and door-to-door help matter more than an app.

## A four-week pilot we would propose

1. Pick one town council with an active cluster (this week: Jurong West or Jurong East).
2. Week 1: the estate team uses the daily plan and prints posters for the cluster blocks; volunteers report outcomes at each stop.
3. Weeks 2–4: compare stops checked, water found and cluster growth with the previous month; review the area outlook's chances against what happened (recorded automatically in the ledger).
4. Decide with the team which alerts and formats to keep. Translations are reviewed by native speakers before any notice is posted.
