# DengueSUX: product design and UX streamlining pass

You are the product designer and front-end engineer for DengueSUX (repo: /Users/apollo/1m/dengueRadar). It's a Singapore dengue early-warning app entered in the Databricks DAISI Challenge (problem A2). Demo Day is **27 Oct 2026**. Judges weight social impact 30%, Databricks execution 30%, **usability for non-technical users 20%**, data rigour 10% and presentation 10%.

Read `docs/CODEX_HANDOVER.md` (ground rules), `docs/PLATFORM_AUDIT.md` and `design-qa.md` before you change anything.

## The problem

The app works and the data is honest, but:
1. **It feels like AI slop.** It's generic dashboard styling, with eyebrow kickers ("SINGAPORE · DENGUE WATCH"), marketing loader copy ("Bringing the signals together"), evenly weighted stat cards and a caption under every number.
2. **There are too many words.** Every number carries a sentence of explanation, so the screens read like documentation instead of a tool.
3. **The best features are buried.** There are only 2 tabs (Area signals, Forecast lab). Inspection plan, 3D walk, resident notices, Check my block and Ask DengueSUX all hide behind clicks or dialogs.

## Who it's for (design for these three, in this order)

1. **Town council / RC volunteer coordinator.** Asks: "Where do we send people this weekend, and what do we tell residents?"
2. **Resident.** Asks: "Is my block near a cluster? What should I do?"
3. **Demo Day judge.** Non-technical, has 3 minutes, and must understand the value in the first 10 seconds.

## What to do

### 1. Restructure around jobs, not data sources

Move from 2 tabs to **4 task-based tabs**, mostly by surfacing features that already exist:

| Tab | Answers | Built from |
|---|---|---|
| **This week** (default) | "What needs attention right now?" | National outlook number and range, top 5 areas to check, what changed since the last snapshot (change feed), "Is my home near a cluster?" |
| **Map** | "Show me any area" | Current area explorer: list, map, detail |
| **Field plan** | "Plan and run a check" | Pick an area, then the walking route, stop checklist, 3D walk, and resident notice in 4 languages. Today this is a hidden view behind an area click. |
| **Forecast** | "Is it getting worse nationally?" | Live outlook first. Retrospective and 2022 replay sit behind a secondary toggle. |

**Ask DengueSUX** stays global (header button), not a tab. **How to read this / sources** stays a dialog. Keep the nav rail and top tabs in sync, and give every tab and area a deep link (`#plan/jurong-east`) so a coordinator can send a link.

Add new features **only if** they serve one of the three users above and use real data already in the pipeline. Add at most two. Candidates I'd accept:
- A **printable field sheet** per area: print CSS with route, stops, checklist and notice, all on one page.
- **Share link / copy link** on any area or plan.

Don't add features that need new data, new model work or a new backend service. List any other ideas in your report instead of building them.

### 2. Cut the words

- Each view's headline is **the answer, with a number**, not a label. Write "3 areas need checking this week", not "Area signals".
- Delete eyebrow kickers, subtitle lines that restate the heading, and stat notes that restate the label. Delete the loader's marketing copy; a simple skeleton is enough.
- Keep helper text to **12 words or fewer** per section. Move longer caveats into an (i) popover or the "How to read this" dialog.
- **Keep these honesty statements visible, once each, short:** "Places to check, not confirmed breeding sites"; the forecast range is past error, not a guarantee; and saved data is never called live.
- Target: **at least 40% fewer visible words per view.** Measure with `document.body.innerText` word count on each tab before and after, and report the numbers.

### 3. Make it not look AI-generated

Refine the existing forest-green / ivory identity; don't replace it. Rules:
- One accent colour, used sparingly. Priority colours (Low/Medium/High) are the only other saturated colours.
- Give it a real type hierarchy. Use one big number per screen and make everything else clearly secondary. Use tabular numbers for figures. Keep DM Sans.
- Use asymmetric layouts that put the most important thing biggest. Avoid rows of identical cards.
- No gradients, glassmorphism, glow, sparkle/AI icons, emoji, decorative blobs or illustrations inside data views.
- Use a single spacing scale and a single radius scale, both defined as tokens in `styles.css` / `experience.css`.
- Motion should be functional only, and `prefers-reduced-motion` must stay respected.

Reference feel: Linear's restraint, the FT's data graphics and Gov.uk's plain language. It should read as a calm public-health tool, not a startup landing page.

### 4. Brand assets (image generation)

Generate a small, coherent asset set. Don't scatter illustrations through the app.
- Logo mark and wordmark. Generate concepts, then **hand-build the final as SVG** (image models garble text and paths).
- Favicon set (`favicon.svg`, 32px PNG, `apple-touch-icon.png` 180px).
- Open Graph / social card, 1200×630.
- 2–3 small spot illustrations, **only** for empty, error and "no clusters near you" states.
- A hero image for the README and Demo Day deck.

Asset rules: no text inside generated images; no fake maps, charts, numbers or data; no mosquito-on-skin or medical gore; no stock-photo people. Use the palette from the CSS tokens. Put final assets in `app/web/brand/`, optimised (WebP/PNG, small).

**Provenance:** save sources, the exact prompts (`prompts.jsonl`) and an `asset-manifest.json` (prompt, model, size, SHA-256 per file) under `output/imagegen/denguesux/`. Follow the same pattern as the earlier simly-folio artwork work.

**How to generate:**
1. Use your built-in image generation first.
2. **If it fails with an access, auth or verification error**, fall back to the terminal using the existing local runner configured for codex-easy.ai. The key goes only into the child process environment; never echo, log or write it anywhere:

```bash
OPENAI_API_KEY="$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.codex/auth.json")))["OPENAI_API_KEY"])')" \
OPENAI_BASE_URL="https://codex-easy.ai/v1" \
python3 ~/.codex/skills/.system/imagegen/scripts/image_gen.py generate-batch \
  --input output/imagegen/denguesux/prompts.jsonl \
  --out-dir output/imagegen/denguesux/sources \
  --model gpt-image-2 --quality high --concurrency 2 --no-augment
```

   If the `openai` package is missing, install it in a scratch venv, not `.venv-prototype`. Use `--dry-run` first to check the batch file.
3. If the terminal route **also** returns 401/403 or a verification error, **stop and tell me**. Don't try other providers, keys or workarounds, and keep building the UI without the assets.

### 5. Constraints (don't break these)

- Vanilla JS, no framework and no build step. FastAPI in `app.py`. Match the existing code style.
- Real data only. Missing stays missing. Don't change the model, pipeline or forecast numbers.
- Keep accessibility work already done: focus management, dialog semantics, keyboard support, reduced motion, and the mobile drawer.
- It must work at 390px mobile width with no horizontal scroll, and in the Databricks-hosted app (postal lookup is hidden there).
- Tests must pass: `.venv-prototype/bin/python -m pytest -q tests`. Update tests that assert old copy or structure; don't delete coverage.
- Don't commit, push or redeploy to Databricks. I'll review first.

## Process

1. **Audit (stop here and show me).** Screenshot every view at 1440 and 390 widths. Give word counts per view and list the 10 worst slop and clutter offenders. Propose the 4-tab IA with a rough wireframe per tab (ASCII or a quick HTML mock). **Wait for my OK before building.**
2. **Build.** Do the IA first, then copy, then the visual system, then assets.
3. **Verify.** Take before/after screenshots of every tab at both widths in `output/design/streamline/`, report before/after word counts, run the tests, check the browser console for errors, and walk through each user's main task, counting the clicks needed.
4. **Report.** Summarise what changed, what you cut, any honesty statements you moved and where they went, and ideas you deliberately didn't build. Update `design-qa.md`.
