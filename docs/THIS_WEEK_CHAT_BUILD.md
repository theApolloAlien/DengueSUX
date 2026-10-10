# Conversational home — 10 October 2026

The local build replaces the static “This week” overview with a greeting, a prominent composer, a single shared conversation and compact evidence cards. It retains the existing DM Sans, forest/ivory palette, wordmark and neighbourhood illustration. Following the user's visual feedback, the national outlook has **no illustration**: the full-width graph stays clear.

## Delivered

- Landing and conversation states, desktop evidence rail and mobile horizontal context strip. One DOM composer/thread moves into the global side panel on other tabs. New chat, Enter/Shift+Enter, edit-last with Up, Stop/Esc, log semantics, focus on completed answers, and session-only transcript persistence.
- Tool-derived area, top-area, forecast and field-plan cards, with validated backend payloads. The home ranking and answer ranking share a renderer. Forecast values never come from generated prose; chart paths use real observations or returned forecast values. Notices use the existing saved drafts and support four languages.
- Browser-side OneMap postal lookup and local geometry calculation. The real lightweight API result was tested: `getAddrDetails=N` provides `SEARCHVAL`, latitude and longitude even when a token warning accompanies it. Postal matching accepts the exact postal suffix in that field; it does not treat the token warning as a successful empty result. The server lookup is not called.
- Actual NEA high-Aedes data downloaded: **98 valid polygons, source date 29 September 2026**, with one invalid source polygon (`67932`) excluded and disclosed. Original bytes are retained in an immutable raw file and landing envelope. Source dates come from `FMEL_UPD_D`, never the stale dataset description. The silver/gold publication and daily task are implemented. The purple overlay does not alter rankings.
- Real snapshot events (newly observed clusters, growth of at least five, closures), MOH/CDA weekly count, forecast issuance and mosquito-map updates. “All updates” exposes the entire feed. Relative times refresh each minute; cluster events navigate to their map geometry. No Live dot is displayed without today's confirmed job completion.
- News collected by a separate daily Databricks task, not by page-load requests. The official NEA RSS endpoint is linked from its RSS directory; its news listing itself returned no article markup. No relevant current headlines were present in the three inspected feeds. The normal empty state remains visible.
- `/api/chat/stream` sends actual tool invocation events and actual serving-endpoint text deltas. The final model answer is genuinely streamed. The current implementation makes a non-streamed tool-planning turn before requesting the final streamed answer, so first-token latency includes that planning work. It falls back to `/api/chat`, then deterministic saved-data answers labelled “Local, no AI”. No stored transcripts or fake typing animation.
- Fixed medical guidance bypasses the model in the browser and API. Seven warning signs, the danger as fever falls, and GP advice are included in four languages. Translations are labelled as needing human review. The copy follows the supplied brief; gov.sg/NCID publication dates are left unavailable, not invented. Direct source verification was limited by gov.sg 403 responses and NCID's redirect/rate-limit response. Clinical and translation review remains appropriate before a public launch.
- myENV/OneService handoff, description copying without the postal code, official myENV alert links, device-only remembered places, Forget/Forget all, and a four-language weekly brief with working plan/notice deep links. DengueSUX collects no resident photos.

## Location status rules

Rules are applied in order using `LocationCheck.THRESHOLDS`. Distances are to actual cluster polygons, including polygon holes and MultiPolygons.

| Status | Rule | Pill | Headline |
|---|---|---|---|
| Red | Any cluster with 10+ people within 150 m, including inside | Act now | You're in a dengue cluster area |
| Amber | Any cluster within 1 km, after the red rule | Be vigilant | Dengue cluster [distance] away, or “Dengue cluster at this location” when inside |
| Purple | No cluster within 1 km and inside a valid NEA high-Aedes polygon | Mosquitoes high | Mosquito numbers are high here |
| Green | None of the above in the dated snapshot | No cluster nearby | No active cluster within 1 km |

Green also says “Not an all-clear. Keep up the weekly Mozzie Wipeout.” Every map card shows the cluster snapshot date. A missing or incomplete mosquito layer is explicitly disclosed. Colour is accompanied by a text pill and a distinct icon shape. The application never describes the result as “safe”.

## Feed sources and filtering

- NEA: `https://www.nea.gov.sg/rss/news_update`, discovered from `https://www.nea.gov.sg/rss/rss-feeds`. The public listing requested in the brief is `https://www.nea.gov.sg/media/news/news`.
- CNA Singapore: `https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416`.
- Straits Times Singapore: `https://www.straitstimes.com/news/singapore/rss.xml`.

Each item must have an allowlisted publisher hostname, a valid date, and dengue/Aedes/Wolbachia/mosquito in the **title**. Singapore is established by the official NEA source, “Singapore” in the title, or a Singapore section URL. Titles about selected foreign countries are excluded unless Singapore is explicit. Future dates are rejected and old headlines expire after 90 days; the news-week view uses seven days. Canonical URLs remove tracking parameters and deduplicate. Only title, publisher, URL, date and kind are retained. Article bodies and RSS descriptions are neither stored nor summarised. Google News is not used.

## Privacy and verification evidence

The browser detects six-digit postal text, including adjacent Chinese characters, before building an assistant request. It sends the postal only to OneMap with a no-referrer policy. Exact geolocation and coordinates remain in the browser. Follow-up context contains only the planning area, a distance band and a public cluster ID (digit groups keep it distinct from a postal code). The user-entered postal and exact coordinates are excluded from sessionStorage; remembered coordinates live only in guarded localStorage on that device. No server-side chat storage was added.

`demo/verify_chat_home.py` intercepts **actual browser request bodies**. It proves postal checks make no chat request, that subsequent SSE and fallback bodies contain neither the postal nor precise coordinates, and that the session transcript omits both. It also blocks `/api/locate` while a real browser-to-OneMap lookup succeeds. API validation rejects raw postal/coordinate text before contacting the model. `tests/test_location_check.py` covers 150 m / 1 km edges, the 10-person boundary, a nearby larger cluster beyond the nearest smaller one, holes, and the actual OneMap response shape.

- Full Python suite: **192 tests passed** (baseline 165), with existing dependency deprecation warnings.
- Browser: **59 boolean checks passed** across main and edge reports, including all four actual status examples, 1440/1024/390 layouts, restored conversation, shared side panel, field-plan navigation, four-language notice controls, saved places, cancellation, keyboard shortcuts, and the offline portable export.
- Zero page exceptions and zero console errors in the main verification run.
- Slow network (150 ms latency, 200 KB/s download) with 4× CPU throttle: actual skeleton displayed, page became usable, CLS **0.000056** in the final measured run.
- Screenshots and recorded desktop/mobile/throttled flows: `output/verification/chat/`. The scripts create Playwright videos with each run.
- Portable HTML: `output/denguesux.html`; health copy and assets are embedded. Maps retain dated vector geometry offline, with unavailable base tiles degrading gracefully.
- Databricks app bundle built successfully in `/tmp/denguesux-chat-build`, including new frontend assets and request-time Python modules.

The local server has no configured hosted model. SSE unit/API tests use controlled serving chunks, and browser tests verify fallback and cancellation. A real cloud model stream and the new Spark tasks have **not** been executed in Databricks; deployment was explicitly out of scope.

## Design QA and scope

See `design-qa.md` for source comparisons, the removed-artwork correction and viewport evidence. The review mock at `output/design/saas/mock-this-week-chat.html` contains landing/conversation controls and real public map points for all four statuses. The mock was continued without an approval pause because the user explicitly requested autonomous building; it was refreshed after the user's illustration feedback.

No packages or frontend framework were introduced. Net new application JavaScript is about 29 KB, below the brief's approximate 30 KB allowance. Forecast/model numbers and ranking formula are unchanged. Existing deck edits and the supplied prompt documents are outside these commits. No push, deployment, cloud grants, messages, notifications or resident reports were sent.

Not built: an independent push-notification system, Google News fallback, block-level prediction, a manufactured 14-day trend when only other comparison windows exist, automated clinical advice, or a persistent chat service. Higher-value follow-up: obtain human clinical/translation review, then run one staging cloud job and a real streaming-model smoke test before deployment.
