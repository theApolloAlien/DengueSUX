# DengueSUX: turn "This week" into a conversational home

You are continuing the DengueSUX design overhaul on branch `design/saas-overhaul` (repo: `/Users/apollo/1m/dengueRadar`). **All rules in `docs/CODEX_SAAS_OVERHAUL_PROMPT.md` still apply:**
- vanilla JS, no build step
- real data only, with no fake progress, no fake SaaS furniture and the honesty statements kept
- the motion tokens and reduced-motion rules
- tests must pass
- one local commit per phase; no push and no Databricks redeploy

Demo Day is **27 Oct 2026**.

**Before you start:** run `git status`. If the previous overhaul left uncommitted work, run the tests. If they pass, commit it as `design: finish brand assets and copy pass`. If they fail, stop and report.

## The goal

Today "This week" is a static dashboard: a headline, a big national card, a "Where to check first" list, a what-changed strip and a postal check row with a lot of empty space. Make it feel like **Claude's home screen, but for dengue**. It should open on a greeting and a big composer that answers in rich cards. **Keep the existing cards**; they become the supporting context around the conversation.

The two moments that must feel magical:
1. **"Is my place OK?" in one step.** Typing a postal code (or tapping "Use my location") into the composer instantly returns a **map bubble card** with a clear status.
2. **The page feels alive.** A live activity feed shows real things happening: new clusters, growth, the weekly MOH report, NEA updates, and relevant news.

## Layout

**Landing state** (no conversation yet):

```
 Good afternoon.                                              ● Clusters · updated 08:15
 Dengue is low in Singapore this week. 3 areas need checking.

 ┌──────────────────────────────────────────────────────────────┐
 │  Ask about dengue, or enter a postal code…                   │
 │                                                              │
 │  (◎ Use my location)  (EN ▾)                           (↑)   │
 └──────────────────────────────────────────────────────────────┘
  [Is 560123 near a cluster?] [Where should we check this weekend?]
  [Will cases rise next week?] [写一份中文居民通知] [I have a fever, what now?]

 ┌ 68 expected nationally ─┐ ┌ Where to check first ───────┐ ┌ Live activity ─────────┐
 │ 50–93 · 80% range       │ │ 01 Jurong West   97 · High  │ │ ● 08:15 New cluster…   │
 │ sparkline               │ │ 02 Jurong East   91 · High  │ │   Fri  MOH: 71 cases…  │
 └─────────────────────────┘ │ …                           │ │   29 Sep NEA mosquito… │
                             └─────────────────────────────┘ └────────────────────────┘
 Places to check, not confirmed breeding sites.
```

- The greeting follows the time of day. The status line underneath is **generated from real data** (outlook level plus the number of High areas), never canned.
- **Shrink the national card.** It currently takes half the width; make it one of three equal-weight cards with a sparkline. The composer is now the hero.
- The separate "Is my home near a cluster?" row is removed, because the composer replaces it. Keep "Try an example" as one of the suggestion chips.

**Conversation state:** once the user sends something, use a View Transition to move the composer to the bottom (docked, as in Claude). The thread fills the main column. On desktop, the three cards collapse into a right-hand rail of compact cards. On mobile, they become a horizontal strip above the thread. Add a "New chat" button to return to the landing state.

**One conversation, one engine.** The header's "Ask DengueSUX" side panel and this composer must share the same thread and the same backend. On other tabs, the header button opens the side panel with the current conversation. Don't leave two different chat UIs in the app.

## Rich answer cards

The assistant already calls tools (`denguesux/assistant.py`: `top_areas`, `get_area`, `cluster_growth`, `inspection_plan`, `forecast_week`, `live_outlook`, `forecast_evaluation`, `data_status`, `query_database`). Make the API return **structured card payloads** alongside the text, built from the tool results, and render them as components rather than prose:

| Card | Shown when | Contents |
|---|---|---|
| **Location check** (map bubble) | Postal code, "use my location", or "is X near a cluster" | See below |
| **Area** | `get_area` | Name, level badge, people in clusters, cluster count, 14-day trend, buttons for "Open field plan" and "Show on map" |
| **Top areas** | `top_areas` | Compact ranked list (same component as "Where to check first") |
| **Forecast** | `live_outlook` / `forecast_week` | Number, range, sparkline, and "Past error, not a guarantee." |
| **Field plan preview** | `inspection_plan` | Stop count, walk distance, mini route thumbnail, "Open field plan" |
| **Resident notice** | Notice requests | Language switch, the draft, "Draft: review before sending", Copy |
| **Feeling unwell** | Symptom or fever questions | See below |
| **Sources** | Every answer | Numbered, dated footnotes [1][2]; the Genie SQL stays in a disclosure |

Every number in a card comes from the tool result, never from model prose.

### The location check card (the hero feature)

**Privacy design (required):**
- Detect a 6-digit postal code **in the browser** before anything is sent.
- Resolve it by calling OneMap's public search **directly from the browser**: `https://www.onemap.gov.sg/api/common/elastic/search?searchVal=<postal>&returnGeom=Y&getAddrDetails=N&pageNum=1`. I verified that it returns `Access-Control-Allow-Origin: *` and needs no token.
- Doing this from the browser also fixes the Databricks-hosted app, where OneMap refuses server-side requests from the cloud network. Keep `/api/locate` only as a fallback.
- Compute distances in the browser, reusing the logic in `checkblock.js`.
- **The postal code and coordinates are never sent to the DengueSUX server or the AI model.** If the user asks a follow-up, send only the derived facts (planning area, distance band and nearest cluster ID).
- Say this in one line under the card: "Looked up by OneMap from your browser. Not sent to DengueSUX."

**Card contents:**
- A small Leaflet map bubble (~280×180, rounded, non-interactive until clicked) with:
  - a home pin
  - the nearest cluster polygons
  - a faint ring at the "nearby" radius
  - any high-mosquito-population area outline (see Part 2)
- The status pill and headline (wording below), the distance to the nearest cluster, and its size.
- Three actions: **What to do** (Mozzie Wipeout, plus "Spray, Apply, Wear" protection), **Report breeding** (opens NEA's myENV / OneService; see Part 3), and **Remember this place**.
- Animation: the card scales in, the map flies to the pin, the rings draw, and the pill fades in last. Under reduced motion, everything appears instantly.

**Status wording.** This aligns with NEA's own Dengue Community Alert System colours, which residents already recognise. **Never say "safe"**: NEA explicitly says areas not highlighted can still have mosquitoes. Pick the first rule that matches:

| Status | Rule | Pill | Headline |
|---|---|---|---|
| Red | Inside, or within 150 m of, a cluster with **10+ people** | Act now | "You're in a dengue cluster area" |
| Amber | Inside, or within 150 m of, a cluster with **fewer than 10 people**, OR any cluster within 1 km | Be vigilant | "Dengue cluster 320 m away" |
| Purple | No cluster within 1 km, but inside an NEA high-mosquito-population area | Mosquitoes high | "Mosquito numbers are high here" |
| Green | None of the above | No cluster nearby | "No active cluster within 1 km" + "Not an all-clear. Keep up the weekly Mozzie Wipeout." |

Every card shows the snapshot date ("as of 10 Oct, 08:15"). Put the thresholds in one constants object, and explain them in "How to read this" (NEA links cases within 150 m into one cluster; 1 km matches the existing Check my block). Use colour plus text plus an icon shape, never colour alone.

**Remember this place:** store it in localStorage (wrapped in try/catch), on this device only. On the next visit, the greeting line becomes "Your saved place: still no cluster within 1 km." Include "Forget" and "Forget all" options.

### Chat behaviour

- **Streaming:**
  - Add `/api/chat/stream` (SSE). The Databricks serving endpoint is OpenAI-compatible, so stream the final answer for real.
  - Show the actual tool steps as they happen ("Looking up Bishan…", "Checking clusters…"), but only steps that really ran.
  - Fall back to the non-streaming endpoint, and then to the existing saved-data answers, with the existing "Local, no AI" labelling.
  - **Never type out a finished answer to fake streaming.**
- **Language:** answer in the language the user writes in (EN / 中文 / BM / தமிழ்). The language menu in the composer switches the suggestion chips and the card labels.
- **Guardrails** (system prompt plus tests):
  - Never diagnose.
  - Symptom questions trigger the Feeling unwell card.
  - Don't predict dengue at block level, and keep the "places to check, not confirmed breeding sites" framing.
  - If the data can't answer, say so and point to NEA.
- **Composer:** Enter sends, Shift+Enter adds a new line, ↑ edits the last message, Esc stops a stream, and there's a Stop button while streaming. Store the conversation in sessionStorage only. Add **no** server-side chat storage.
- **Accessibility:** the thread is `role="log"` with polite live updates, every card has a heading, and focus moves to the new answer's heading when it completes.

## Part 2: High-mosquito-population layer (data needed for the purple status)

NEA publishes the Gravitrap "Areas with High Aedes Population" layer as open data. I verified it: dataset `d_5d060d8b7838a15e8906fb22c50dbf51` has 99 polygons, is updated monthly, and its features carry `FMEL_UPD_D=20260929…`. Download it via `https://api-open.data.gov.sg/v1/public/api/datasets/d_5d060d8b7838a15e8906fb22c50dbf51/poll-download`. Ignore the dataset's stale "April to June 2019" description text; date it from the feature update stamp.

- Ingest it with the existing live-ingestion pattern (land the raw file in the Volume, then build a silver and a `gold_aedes_high_areas` table with the source date). Add it to the daily job; it's cheap, and skip it when unchanged.
- Add it as a toggleable Map layer (purple outline), use it in the location check card, and mention it in area cards ("Part of this area has high mosquito numbers (NEA, Aug 2026)").
- **Don't** fold it into the area ranking formula without telling me. Show it alongside the ranking.

## Part 3: Live activity feed

**Make it alive with real events, not scraped noise.** I tested a general "dengue Singapore" news search: most results were about Florida, Bangladesh, or unrelated Singapore news. A raw news feed would look broken.

**Feed items** (newest first, each with a type icon, relative time, one line, and a click-through):
1. **Data events** from what the pipeline already produces: new clusters, clusters growing by 5+, closed clusters (`growth.json`, `alerts.json`), the weekly MOH/CDA count, the forecast refresh, the NEA high-mosquito map update (Part 2), and the daily job run. Clicking an item flies the map to the cluster or area, or opens the forecast.
2. **Official updates:** dengue-related items from NEA's news page (`https://www.nea.gov.sg/media/news/news`), filtered by dengue, Aedes, Wolbachia or mosquito in the title.
3. **In the news:** Singapore publisher RSS feeds (CNA Singapore and Straits Times Singapore both returned 200 when I tested).
   - Keep items only if the **title** mentions dengue, Aedes, Wolbachia or mosquito, **and** the item is about Singapore.
   - Use a source allowlist.
   - Show **headline, source, date and link only**. Never store or summarise article text.
   - Google News RSS is too noisy. Don't use it unless the allowlisted sources return nothing for 30 days, and if you do, apply the same filters.

**Implementation:**
- Fetch news in a **new task in the daily Databricks job**, never at page load. Write a `gold_feed_items` table (title, source, url, published_at, kind) deduplicated by URL, and include it in the app snapshot. This also strengthens the Databricks-execution score.
- A "Live" dot appears only if the daily job ran today. Otherwise show "Updated 2 days ago".
- New items slide in with the motion tokens, relative times update every minute, and hovering a data event highlights it on any visible map.
- **Empty state:** "No dengue news this week". That's normal in a low season, so don't pad the feed.

## Part 4: Extra features (build in this order, after Parts 1–3)

1. **Feeling unwell card.** Triggered by symptom questions and by a suggestion chip.
   - List the warning signs that mean going to A&E now: bleeding gums or nose, persistent vomiting, severe abdominal pain, drowsiness or confusion, breathing difficulty, cold clammy skin, and little urine.
   - Highlight that danger often comes **as the fever drops**.
   - "Otherwise see a GP."
   - Cite and link gov.sg and NCID, and show it in 4 languages (translations marked "needs human review").
   - No diagnosis, and no model-generated medical text: this is fixed, sourced copy.
2. **Report breeding handoff.**
   - A sheet explaining that NEA acts on reports made through **myENV** ("Report to NEA", photo attachments supported) or **OneService**.
   - Store links to both apps, plus a "Copy location description" button (nearest block and street from OneMap, never the user's postal code unless they typed it into this sheet).
   - **DengueSUX doesn't collect resident photos.**
3. **Area watch.** "Remember this place" also offers "Get alerts", which links to myENV's cluster alerts (official). Don't build our own push system.
4. **Weekly brief share.** One button on the landing state: "Copy this week's brief". It copies plain text for a residents'-committee Telegram or WhatsApp group (top areas, national outlook, link to the plan, the notice link), with each language selectable.

Propose anything else you think is high value in your report, but don't build it.

## Process

1. **Mock first. Stop and wait for my OK.** Build `output/design/saas/mock-this-week-chat.html` with both states (landing and conversation) and a location card in all four statuses. Use real data and real OneMap lookups for one example. Capture screenshots at 1440 and 390.
2. **Phases** (one commit each, tests passing each time):
   1. Composer, landing layout and the shared conversation engine.
   2. Card payloads and components.
   3. Location check card with browser-side OneMap.
   4. High-mosquito layer ingestion and map layer.
   5. Live activity feed (data events, then the news job).
   6. Streaming.
   7. Part 4 features.
3. **Tests to add:**
   - Postal detection never sends the postal code to `/api/chat` (assert on the request bodies in a browser test).
   - Status rules for each tier, with fixtures at the threshold edges.
   - Feed filtering (relevant, irrelevant and duplicate items).
   - The no-diagnosis guardrail.
   - Card payload schemas.
   - Aedes ingestion dates taken from the feature stamp.
4. **Verify:**
   - Playwright videos: landing → postal check → follow-up question → open field plan; a judge's first 10 seconds; and the mobile flow.
   - The hosted-app path: postal lookup works with the server's OneMap blocked.
   - Throttled loading.
   - Reduced motion.
   - Zero console errors.
   - Portable HTML export still works (the feed and cards degrade cleanly offline).
5. **Report:** what changed, the final status wording, the feed sources and their filters, privacy guarantees (and how the tests prove them), and anything you deliberately didn't build. Update `design-qa.md`.
