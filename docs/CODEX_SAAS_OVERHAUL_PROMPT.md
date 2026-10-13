# DengueSUX: product-grade design overhaul

You are the lead product designer and front-end engineer for DengueSUX (repo: `/Users/apollo/1m/dengueRadar`). It's a Singapore dengue early-warning app entered in the Databricks DAISI Challenge (problem A2). Demo Day is **27 Oct 2026**. Judges weight social impact 30%, Databricks execution 30%, **usability for non-technical users 20%**, data rigour 10% and presentation 10%.

Before touching anything, read `docs/CODEX_HANDOVER.md` (ground rules), `docs/PLATFORM_AUDIT.md`, `design-qa.md` and `README.md`. Then open the app (`.venv-prototype/bin/python -m uvicorn app:app --port 8787`) and use every feature yourself.

## The goal

Make DengueSUX feel like a **polished, shipping SaaS product**, the kind of tool a town council would pay for. Think Linear, Vercel, Stripe Dashboard or Mapbox Studio, not a hackathon dashboard. Concretely:

- **It feels fast.** Something meaningful paints on the first frame, every wait has a purposeful loading state, and every click gives feedback within 100 ms.
- **It feels alive.** A coherent motion system makes navigation, selection and data arriving feel physical and connected.
- **It feels considered.** It has a real design system, consistent components, a strong hierarchy and very few words.
- **It feels useful.** Features are organised around jobs people actually do, with power-user speed (command palette, shortcuts, deep links).

## Who it's for (in priority order)

1. **Town council / RC volunteer coordinator.** "Where do we send people this weekend, and what do we tell residents?"
2. **Resident.** "Is my block near a cluster? What should I do?"
3. **Demo Day judge.** Non-technical, has 3 minutes, and must get the value in the first 10 seconds.

## Non-negotiables

- **Tech:** vanilla JS and CSS, with no framework and no build step. FastAPI static serving in `app.py` stays. Use native platform APIs for motion: the View Transitions API, the Web Animations API, CSS transitions and `@starting-style`, each with graceful fallback. Add no new runtime dependencies unless they're vendored locally under `app/web/vendor/` with a pinned version and a written justification. Total new JS should stay under ~30 KB unminified.
- **Honesty:** this is a public-health tool.
  - Real data only; missing stays missing. Don't change the model, pipeline or any forecast number.
  - **Every loader must reflect real work.** No artificial delays, no fake progress percentages, no fake step sequences, and no animating "5/5 checks" as if they ran one by one when they didn't.
  - **No fake SaaS furniture.** No sign-in, pricing, customer logos, testimonials, avatars, fake notification counts or "AI insight" badges.
  - Keep these visible, once each and short: "Places to check, not confirmed breeding sites"; the forecast range is past error, not a guarantee; and saved data is never labelled live.
- **Accessibility:** keep everything that works today (focus management, dialog semantics, keyboard support, the mobile drawer). Under `prefers-reduced-motion: reduce`, every animation becomes instant or a simple fade, and shimmer becomes static.
- **Platforms:** desktop 1440, laptop 1280, tablet 1024 and mobile 390, with no horizontal scroll. The app must also work in the Databricks-hosted app (postal lookup is hidden there; `scripts/build_databricks_app.py` copies `app/`) and in the portable export (`scripts/export_html.py` inlines `<link rel="stylesheet" href="...">` and scripts by regex, so keep tags in that exact form and make sure new images are inlined or degrade cleanly).
- **Tests:** `.venv-prototype/bin/python -m pytest -q tests` must pass. Update tests that assert old copy or structure; never delete coverage.
- **Git:** work on a new branch, `design/saas-overhaul`, and make one local commit per phase. **Don't push and don't redeploy to Databricks.** I'll review first.

---

## Part A: App shell and information architecture

**Replace the 2 tabs (Area signals, Forecast lab) with 4 job-based sections.** Most of this means surfacing features that already exist but are buried:

| Section | Answers | Built from |
|---|---|---|
| **This week** (default) | "What needs attention right now?" | National outlook (number and range), top 5 areas to check, what changed since the last snapshot (change feed), "Is my home near a cluster?" |
| **Map** | "Show me any area" | Area explorer: list, map, detail. Add a sortable table view as an alternative to the list. |
| **Field plan** | "Plan and run a check" | Area picker, then the walking route, stop checklist, 3D walk, resident notice in 4 languages, a **printable field sheet** (print CSS, one page) and **copy share link** |
| **Forecast** | "Is it getting worse nationally?" | Live outlook first. Retrospective and 2022 replay sit behind a secondary toggle. |

**Shell:**
- A labelled left sidebar that can collapse to icons, with an active-section indicator that slides between items.
- A top bar with a breadcrumb (`Field plan / Jurong East`).
- A **data freshness chip**, e.g. "Clusters · 3 h ago", with a colour that reflects real freshness. Clicking it opens sources.
- Ask DengueSUX stays a global entry point that opens a side panel. Help ("How to read this", shortcuts, replay tour) lives in a menu.
- **Deep links** for every section, area and plan (`#plan/jurong-east`), with back/forward working correctly.

**Command palette (⌘K / Ctrl+K):**
- Fuzzy-search all 55 areas.
- Jump to any section.
- Run actions: "Plan a check in …", "Check my postal code", "Open forecast", "Copy link", "Ask: …".
- Use the accessible combobox pattern, with recent items shown first.

**Keyboard shortcuts:** `g` then `t` / `m` / `p` / `f` to change section, `/` to focus search, `?` to open the shortcuts sheet, `Esc` to close any layer.

**First-run tour:** 3 coach marks (This week → Field plan → Ask). It's skippable, shows once (localStorage wrapped in try/catch), and can be replayed from Help. Also add `?tour=1` to force it for Demo Day.

## Part B: Design system

Evolve the existing forest-green / ivory identity into a proper system; don't replace it. Put everything as CSS custom properties in one tokens layer:

- **Colour:** semantic tokens (`--surface-1..3`, `--text-1..3`, `--border-*`, `--accent`, `--priority-low|medium|high`, `--success|warning|danger`). Structure them so dark mode could be added later (see stretch goals).
- **Type:** keep DM Sans. Use a 6-step scale and `font-variant-numeric: tabular-nums` for all figures. Each screen gets one hero number; everything else is clearly secondary.
- **Space and shape:** a 4 px spacing scale, a 3-step radius scale and 3 elevation levels (shadow and border, kept subtle).
- **Motion:** tokens as defined in Part D.

**Components** (each with hover, focus-visible, active, disabled, loading and error states where relevant): button (primary, secondary, ghost, icon), input, search, segmented control, tabs, badge, chip, tooltip, popover, menu, toast, dialog, drawer/side panel, KPI tile, data table (sortable, sticky header), list row, skeleton, empty state, inline banner, progress (determinate and indeterminate) and kbd hint.

**Living style guide:** a hidden route, `#styleguide` (not in the nav), that renders every token and every component in every state. It's your QA surface and evidence of rigour.

**Anti-slop rules:**
- No gradients, glassmorphism, glow, sparkle/AI icons, emoji, decorative blobs, or rows of identical cards.
- No eyebrow kickers ("SINGAPORE · DENGUE WATCH"), and no subtitles that restate the heading.
- Use asymmetric layouts where the most important thing is the biggest thing.
- The only saturated colours are one accent plus the priority colours.

## Part C: Loading experience

**Rule:** nothing shows for waits under 300 ms. Once a loader appears, it stays at least 400 ms to avoid flicker. Loaders always reflect real work.

1. **Boot / first paint:** inline critical CSS in `index.html` so the **app shell and skeletons paint on the first frame**, never a blank page. Add `<link rel="preload">` for `dashboard.json` and fonts. Show a quiet brand mark only if loading passes 300 ms. Escalate to "Still loading…" after 4 s, and to an error with **Retry** after the existing timeout.
2. **Skeletons that match the final layout exactly**, for KPI tiles, the area list, map panel, detail panel, forecast chart and field plan. Use a subtle shimmer that turns static under reduced motion. Content replaces each skeleton with **no layout shift** (target CLS < 0.05).
3. **Progressive reveal:** render panels as their data arrives rather than all at once. The map boundaries come first, then the priority fill fades in, then the cluster markers.
4. **Real multi-step work:** route and plan generation, notice generation and Ask DengueSUX should show their actual stages only where the code really has them (e.g. "Finding cluster blocks → Routing with OneMap → Ready"). For Ask, show a typing indicator, then render the answer with sources and SQL.
5. **Button-level states:** a spinner inside the button for any action over 300 ms, with its width locked so it doesn't jump. Show success as a brief check or a toast.
6. **Optimistic UI:** checklist ticks and copy-link apply instantly.
7. **Prefetch:** warm field plan data when an area is hovered or focused, and lazy-load the 3D view only when it's needed.
8. **Failure states:** inline banners with Retry. Offline gets its own banner. The saved-data fallback is clearly labelled. Empty states use the spot illustrations from Part F.

## Part D: Motion system

**Tokens:**
- `--dur-instant: 80ms`, `--dur-fast: 140ms`, `--dur-base: 220ms`, `--dur-slow: 360ms`, `--dur-deliberate: 600ms`
- `--ease-out: cubic-bezier(.2,0,0,1)`, `--ease-in-out: cubic-bezier(.4,0,.2,1)`, plus one spring via CSS `linear()`

**Choreography** (implement all of these; tune by eye):

| Moment | Animation |
|---|---|
| Section change | View Transition: cross-fade plus 8 px slide in the travel direction, `--dur-base` |
| Sidebar / tab indicator | Slides to the new item, `--dur-fast` |
| KPI numbers | Count up **once on first load only**, `--dur-deliberate`, using tabular nums so the width is stable. Values never re-animate on refresh. |
| Lists and table rows | Fade plus 4 px rise, 20 ms stagger, first 8 rows only |
| Area select | Map `flyTo` (~600 ms), detail cross-fade, selected row highlight moves (shared-element View Transition where supported) |
| Map data | Priority fill fades in; cluster markers scale 0.6→1 with a capped stagger |
| Forecast chart | Line draws on first view (~700 ms), then the 80% range band fades in, then the "now" marker appears |
| Field plan opens | Route path draws along the OneMap line (~800 ms); stops pop in sequence; the 3D walk keeps its existing camera motion |
| Checklist tick | Checkmark stroke draws, the row settles, and the progress ring advances |
| Dialogs and side panels | Scale 0.97→1 plus fade, `--dur-fast`; backdrop fade; faster exit than entrance |
| Drawer (mobile) | Slides from the edge, `--dur-base`, following the finger where practical |
| Toasts | Slide up, auto-dismiss after 4 s with a progress hairline that pauses on hover/focus |
| Buttons | Press scale 0.98 (`--dur-instant`), colour on hover (`--dur-fast`) |
| Freshness dot | Gentle pulse, **only when data is genuinely live** |

**Performance rules:**
- Animate only `transform` and `opacity` (plus `clip-path` or `stroke-dashoffset` for draws).
- Never block input during an animation.
- Nothing loops except loaders and the live dot.
- Hold 60 fps on a mid-range laptop.
- Respect reduced motion everywhere.

## Part E: Copy

- Each section's headline is **the answer with a number**: "3 areas need checking this week", not "Area signals".
- Keep helper text to 12 words or fewer per block; longer caveats move into (i) popovers or "How to read this".
- Delete marketing loader copy, kickers, redundant stat notes and duplicated explanations.
- Target: **at least 40% fewer visible words per section.** Measure with `document.body.innerText` word count on every section before and after, and report the numbers.
- Write in plain, Gov.uk-style language: verbs on buttons ("Plan a check", "Copy notice"), no jargon on primary surfaces.

## Part F: Brand assets and imagery

Generate a small, coherent asset set:
- Logo mark and wordmark. Generate concepts, then **hand-build the finals as SVG**.
- Favicon set (`favicon.svg`, 32 px PNG, 180 px `apple-touch-icon.png`) and a web app manifest.
- Open Graph card, 1200×630.
- 3 spot illustrations: empty search, error/offline, and "no clusters near you".
- A hero image for the README, the Demo Day deck and the optional overview page.

**Rules:**
- No text inside generated images.
- No fake maps, charts, numbers or data.
- No mosquito-on-skin or medical gore, and no stock-photo people.
- Use the palette from the tokens.
- Put finals in `app/web/brand/`, optimised (WebP/PNG, small).
- Record provenance under `output/imagegen/denguesux/`: sources, `prompts.jsonl`, and an `asset-manifest.json` with prompt, model, size and SHA-256 per file.

**How to generate:**
1. Use your built-in image generation first.
2. **If it fails with an access, auth or verification error**, use the existing local runner configured for codex-easy.ai from the terminal. The key goes only into the child process environment; never echo, log or write it anywhere:

```bash
OPENAI_API_KEY="$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.codex/auth.json")))["OPENAI_API_KEY"])')" \
OPENAI_BASE_URL="https://codex-easy.ai/v1" \
python3 ~/.codex/skills/.system/imagegen/scripts/image_gen.py generate-batch \
  --input output/imagegen/denguesux/prompts.jsonl \
  --out-dir output/imagegen/denguesux/sources \
  --model gpt-image-2 --quality high --concurrency 2 --no-augment
```

   Run with `--dry-run` first. If the `openai` package is missing, install it in a scratch venv, not `.venv-prototype`.
3. If the terminal route **also** returns 401/403 or a verification error, **stop and tell me**. Don't try other providers, keys or workarounds, and keep building everything else.

## Part G: Stretch goals (only after Parts A–F pass verification)

1. **Product overview page** (`#overview`): a hero, 3 feature rows using **real screenshots** of the app, the founder story (the current "Our story" content), data sources and a "Open the app" CTA. Same design system, and no fabricated claims or metrics.
2. **Dark mode** using the semantic tokens. The map tiles, chart and 3D view must all stay legible.
3. **Presenter mode** (`?present=1`): larger type and a scripted 3-minute walkthrough of the Demo Day story, advanced with the arrow keys.

---

## Process

**Phase 0: Audit and proposal. Stop here and wait for my OK.**
- Screenshots of every view at 1440 and 390, and a word count per view.
- The 10 worst slop/clutter offenders.
- The current load timeline (throttled to "Fast 4G").
- The proposed IA with a wireframe per section.
- **One static high-fidelity mock** of the "This week" section in the new system: `output/design/saas/mock-this-week.html`, with its loading → loaded transition working.

**Then build in phases, with one local commit each. The app must work and tests must pass at the end of every phase:**
1. Tokens, components and the `#styleguide` route
2. Shell, 4-section IA, deep links, command palette, shortcuts
3. Loading experience (Part C)
4. Motion system (Part D)
5. Copy pass (Part E)
6. Brand assets (Part F) and the first-run tour
7. Stretch goals, only if everything above passes

## Verification (attach evidence, don't just claim it)

- **Screenshots:** before/after of every section at 1440, 1024 and 390 in `output/design/saas/`, plus loading and error states for each.
- **Videos:** Playwright recordings (`recordVideo`) of the 3 core flows: judge first 10 seconds, coordinator plans a check and copies the notice, resident checks their block. Record each once with normal motion and once with reduced motion.
- **Throttled run:** "Slow 4G" plus 4× CPU slowdown, to prove the skeletons and loaders actually appear, look right and cause no layout shift.
- **Metrics:** before/after first contentful paint, LCP, CLS and the INP proxy (Lighthouse or a Chrome performance trace), word counts per section, and the number of clicks for each core task.
- **Checks:** zero console errors, all tests pass, `scripts/export_html.py` produces a working portable HTML, and `scripts/build_databricks_app.py` output includes the new assets.
- **Report:** what changed, what you cut, where each honesty statement now lives, any deviations from this brief and why, and ideas you deliberately didn't build. Update `design-qa.md`.
