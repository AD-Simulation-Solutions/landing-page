# ODRMaker AI junction-mapping article, contact form and home banner

## Overview
- Add a dedicated article page on adss.ai: how ODRMaker lets an AI agent map a road junction automatically from orthophoto imagery (written in English, cautious "AI-assisted" tone).
- The article ends with its own contact form (Formspree, same as /contact/), pre-tagged with the article as source.
- The home page gets a banner section linking to the article.
- Source material: ODRMaker repo `docs/ai_mode/` (MAPPING_PIPELINE.md, JUNCTION_RUN_2026-11-06.md, AGENT_SURFACE_ANALYSIS.md, tools/README.md, samples/) and PRs #254 (draft, "agent surface" fixes + run report + `junction-mapping` skill) and #255 (open, CV/ML tools, SmartVertex, VLM mapping in the editor).

## Context (from discovery)
- landing-page is a static site: `build.py` (stdlib Python) builds `src/` -> `dist/`; a page = `src/pages/<name>.html` with front matter (`title`, `description`, `url`, `nav`, `jsonld`); `url: /odrmaker/ai-junction-mapping/` becomes `dist/odrmaker/ai-junction-mapping/index.html`; sitemap is generated from pages.
- Build rejects inline styles/scripts/event handlers, `href="#"`, and pages without exactly one `<h1>`. CSP: `img-src 'self' data:`, `connect-src` and `form-action` allow only self + formspree.io. No third-party requests.
- Contact form in `src/pages/contact.html` (Formspree `xnjbwbow`, `data-enhance`, honeypot `_gotcha`, ids `f-name`, `f-company`, `f-email`, `f-interest`, `f-message`); `src/assets/js/site.js` enhances the first `form[data-enhance]` on a page (validation + fetch).
- `tests/check.py` has a hard-coded `PAGES` list, a CSP-equality check, a hype-word blacklist (e.g. "revolutionary", "seamless", "state-of-the-art"), contrast/target-size/no-horizontal-scroll checks, and tests the form only on `/contact/` (with ids `f-name` etc. and "4 messages under the fields" for an empty submit).
- Home page `src/pages/index.html` is sections; `cta-band` partial and `section--soft`/`section--navy on-dark` classes exist in `src/assets/css/site.css`.
- Facts for the article (verified in ODRMaker docs, keep numbers honest):
  - principle: the vision model decides meaning, classical CV supplies numbers, geometry is never written by the vision model; no trained ML models in the pipeline;
  - pipeline: orthophoto fetch (licence gate) -> georeference -> OSM prior -> paint evidence / heading scan / arm detection / ribbon & cross-section profiles -> spec with per-number provenance -> `build_junction.ts` drives the editor store -> overlay + reverse check + validators -> `.xodr` opened on top of its own imagery;
  - ⚠️ review finding: the 2026-11-06 run report (12 roads, 8 connections, 115 ms, 2 undo steps, "validators clean") is NOT the run shown in `lelystad-junction-2026-11-24-*` (rebuild: 11 roads, 8 connections, one undo step per tools/README.md, residual ~23 cm per spec). MAPPING_PIPELINE.md marks the Lelystad run as rejected ("негоден"). Every number in the article must come from ONE named run/build; "validators clean" is never a quality claim on its own (always paired with residual and lane-reachability results);
  - corpus: 7 junctions, 4 countries (NL, DE, BE, CH) per MAPPING_PIPELINE.md; 5 accepted, 2 early runs rejected because the metric was wrong;
  - accuracy, honestly: about 10 cm where a boundary has its own paint and the arm is lit; earlier 9.1 cm claim was a measuring artefact and is corrected in PR #254; in the Lelystad re-measure 5 of 29 boundaries were off by 1 m+.
- Sample assets available (source image is 1100x1100 px, ~291 KB; do not upscale): `ODRMaker/docs/ai_mode/samples/lelystad-junction-2026-11-24-overlay.jpg`, `...-24.xodr`, `...spec.json`.

## Development Approach
- **testing approach**: Regular (content first, then extend `tests/check.py`)
- complete each task fully before moving to the next
- make small, focused changes; reuse existing CSS classes (`page-head`, `section`, `card`, `btn`, `form-card`, `form-grid`) before adding new CSS
- **CRITICAL: every task MUST include new/updated tests** (here: `tests/check.py` extensions and `python3 build.py` validation)
- **CRITICAL: `python3 build.py` and `python3 tests/check.py` must pass before starting next task**
- **CRITICAL: update this plan file when scope changes during implementation**
- no inline styles/scripts, no new external requests, no cookies/storage; images are local files under `src/assets/img/`
- do not claim more than the docs support: use "AI-assisted", name limits, no hype words from the check.py blacklist

## Testing Strategy
- **build checks**: `python3 build.py` (forbidden-pattern and single-h1 validation)
- **e2e**: `tests/check.py` (Playwright): add the new page to `PAGES`, assert the banner link on `/`, and test the article form with a mocked Formspree response (success, validation errors, honeypot, hidden `source` field)
- manual: view at 320 and 1440 px, keyboard-tab through the form, banner contrast on the home page

## Progress Tracking
- mark completed items with `[x]` immediately when done
- add newly discovered tasks with ➕ prefix
- document issues/blockers with ⚠️ prefix
- keep plan in sync with actual work done

## Solution Overview
- **Page**: `src/pages/ai-junction-mapping.html` with `url: /odrmaker/ai-junction-mapping/`, `nav: odrmaker` (conscious choice: marks the ODRMaker menu item current), `og_type: article`; no JSON-LD (build supports only `organization`). Avoid the uppercase word "ROADS" anywhere (check.py drafts guard).
- **Article structure** (English): lead + one-sentence claim -> "The problem: hand-drawing junctions in OpenDRIVE" -> "Who decides what: vision model vs measurements" (the table/principle) -> "The pipeline" (step list, reuse `pipeline` partial style or a new simple ordered list) -> "A real run: Lelystad junction" (decision: present Lelystad openly as the run that exposed a flattering metric and led to the corrected tools; use only numbers of the single 2026-11-24 rebuild, confirmed in Task 1; overlay image from that same build; if Task 1 finds the rebuild's numbers cannot be stated cleanly, say so and ask the user to pick an accepted junction instead) -> "What it checks itself" (overlay residuals, reverse check, lane reachability, per-number provenance, undo/validators) -> "Honest limits" (accuracy only where paint exists, early over-claim corrected, human review expected, status: PRs in review, not yet a shipped one-click feature) -> "Try it on your junction" form.
- **Links and wording**: no links to GitHub/PDOK (check.py allowlist is adss.ai, www.linkedin.com, formspree.io, odrmaker.com); PDOK attribution is plain text "© Beeldmateriaal Nederland, PDOK" (exact text in JUNCTION_RUN_2026-11-06.md); status is worded "in development / under review" with no PR numbers.
- **Form**: a second copy of the contact-form markup inside the article (user chose a separate page with its own form rather than a shared partial, to leave `/contact/` and its tests untouched). Differences: `_subject` = "adss.ai enquiry — AI junction mapping", hidden `source=ai-junction-mapping`, `interest` preselected to "ODRMaker" via the `selected` attribute (so `form.reset()` keeps it), message label identical to the contact page ("What would you like to test or discuss?"), which matches the hard-coded JS error text (JS is not changed, to leave /contact/ untouched), unique ids prefixed `aj-` to avoid clashes (JS looks fields up by `form.elements[name]`, so ids may differ; verify in site.js).
- **Banner on home**: new section after the hero/problem flow (before `beyond` or the CTA band): eyebrow "New in ODRMaker", headline about AI-assisted junction mapping, one sentence, `btn` link "Read how it works" to `/odrmaker/ai-junction-mapping/`, small overlay thumbnail. Also add a short text link from `/odrmaker/` page.
- **Accuracy of claims** is the main risk: every figure in the article is traceable to a doc in ODRMaker; list sources in a plan note so a reviewer can verify.

## Technical Details
- New files: `src/pages/ai-junction-mapping.html`; images `src/assets/img/ai-junction-lelystad-overlay.jpg` (recompressed copy of the sample overlay at <=1100 px, `width="1100" height="1100"`, alt text, referenced with `{{ asset "/assets/img/..." }}` so it gets the `?v=` hash). No home-page thumbnail (dropped: extra weight for little gain).
- Possible small CSS additions in `src/assets/css/site.css` for `.article` (readable measure ~70ch, figure/figcaption, numbered steps) and `.promo-banner`; check that contrast and target-size tests (check.py requires 44x44 at 390 px for `.btn`, `.link-arrow`, form controls) still pass; use existing `.link-arrow` for text links.
- Formspree: same form id as contact; Formspree free-plan field `source` is just another field; no change to CSP.
- `check.py` currently asserts form details only on `/contact/` (ids `f-*`); the new form should be tested separately without altering those assertions.
- Sitemap updates automatically from the page front matter.

## What Goes Where
- **Implementation Steps**: article page, images, form, banner, CSS, `tests/check.py`, README note.
- **Post-Completion**: fact-check by ODRMaker authors, decision on publishing while PRs #254/#255 are unmerged, upload of `dist/` to OVH, confirming Formspree delivery.
- `tests/results.md` is deliberately left uncommitted (generated output).

## Implementation Steps

### Task 1: Collect and verify article facts

**Files:**
- Create: `docs/plans/ai-junction-mapping-facts.md` (working note, not published)

- [x] read ODRMaker `docs/ai_mode/MAPPING_PIPELINE.md`, `JUNCTION_RUN_2026-11-06.md`, `tools/README.md` and the `junction-mapping` skill in PR #254 (`.claude/skills/junction-mapping/SKILL.md`); read PR #255 description for the SmartVertex/VLM in-editor features
- [x] write a short facts note: each claim for the article with its source file/line (pipeline stages, run numbers, corpus, accuracy and limits)
- [x] decide with the user whether the PR #255 in-editor features (SmartVertex, VLM mapping panel) are mentioned or only the agent pipeline from #254 (decided autonomously: only the agent pipeline from #254; #255 not mentioned; see facts note)
- [x] for each claim store the original Russian line plus an English rendering (so ODRMaker authors can check e.g. "негоден", "годен при допуске 0.8 м") (done in facts note, sections A-G)
- [x] pin ONE run/build for the Lelystad example (2026-11-24 rebuild: roads, connections, undo steps, residual from `.spec.json`/`.xodr`/tools README) and drop numbers from other runs (pinned: 2026-11-24 rebuild, build 3: 3 arms + 8 connectors = 11 roads, 8 connections, worst boundary 23 cm; unknowns listed in facts note)
- [x] verify the facts note contains no number that the docs retract (9 cm claim) except as an acknowledged correction

### Task 2: Prepare the illustration

**Files:**
- Create: `src/assets/img/ai-junction-lelystad-overlay.jpg`

- [x] copy (output 1100x1100 px, 226 KB) `ODRMaker/docs/ai_mode/samples/lelystad-junction-2026-11-24-overlay.jpg`, recompress (keep <=1100 px, no upscaling; Pillow or ImageMagick)
- [x] confirm the imagery licence allows publication (PDOK open data; licence `PDOK-open`, layer allows derivatives per facts note D3) and use the plain-text attribution in the figcaption (no link): "© Beeldmateriaal Nederland, PDOK" (reminder for task 3; image width="1100" height="1100")
- [x] run `python3 build.py` - must pass before task 3 (hash check moves to task 3)

### Task 3: Build the article page

**Files:**
- Create: `src/pages/ai-junction-mapping.html`
- Modify: `src/assets/css/site.css`

- [x] create front matter (`title`, `description`, `url: /odrmaker/ai-junction-mapping/`, `nav: odrmaker`) and the page head with one `<h1>`
- [x] write the sections listed in Solution Overview using existing classes; figure with alt text, width/height, `<img src="{{ asset ... }}">`
- [x] after build, confirm the built HTML has `?v=<hash>` on the image URL
- [x] add minimal `.article` CSS for reading width, figure and step list (no inline styles)
- [x] add the honest-limits section and a status line (in review, not a shipped one-click feature)
- [x] run `python3 build.py` (forbidden-pattern + single-h1 validation) - must pass
- [x] add the page to `PAGES` in `tests/check.py` and run `python3 tests/check.py` for layout, link, hype-word, contrast and CSP checks - must pass before task 4 (initially skipped - Playwright was not installed; the orchestrator later ran the full suite and it passed 349/349 at that point; final full run after the review fixes: 363/363; build.py, sitemap, hype-word, ROADS, link and inline-style checks were done statically on dist/)

### Task 4: Add the contact form to the end of the article

**Files:**
- Modify: `src/pages/ai-junction-mapping.html`
- Modify: `tests/check.py`

- [x] copy the form markup from `contact.html` into a closing "Try it on your junction" section; change `_subject`, add hidden `source`, preselect "ODRMaker", adjust message label; use unique ids
- [x] check `site.js` enhancement works with the new ids (focus on first invalid field, error messages, success text)
- [x] lean checks in `tests/check.py` (do not copy all contact-form checks): action/method, interest preselected, honeypot hidden, empty submit shows 4 errors, mocked 200 with `source=ai-junction-mapping` in the posted body and the success text
- [x] check the error path (mocked failure shows the error text with the email)
- [x] run `python3 tests/check.py` - must pass before task 5

### Task 5: Banner on the home page and link from /odrmaker/

**Files:**
- Modify: `src/pages/index.html`
- Modify: `src/pages/odrmaker.html`
- Modify: `src/assets/css/site.css`
- Modify: `tests/check.py`

- [x] add the banner section to `index.html` (eyebrow, headline, one sentence, button to the article; no thumbnail). Place after the hero/problem block or use `section--soft`, not directly before the navy `beyond` section
- [x] add a short text link from `odrmaker.html` to the article
- [x] style the banner in `site.css` (reuse `section--navy on-dark` where possible); verify contrast and tap target size (no CSS needed: reused existing section--soft, btn--primary, link-arrow, after-grid)
- [x] write one check in `tests/check.py`: home page contains a link to `/odrmaker/ai-junction-mapping/` (link resolution and widths are already covered globally once the page is in `PAGES`)
- [x] run `python3 build.py && python3 tests/check.py` - must pass before task 6

### Task 6: Verify acceptance criteria
- [x] article exists at `/odrmaker/ai-junction-mapping/`, in sitemap, in English, all claims match the facts note
- [x] contact form at the end works (mocked) and tags the source
- [x] banner on `/` leads to the article
- [x] run full `python3 build.py && python3 tests/check.py`
- [x] view screenshots in `tests/screenshots/` for the new page at mobile and desktop widths (note: the figure shows blank in full-page screenshots because of loading="lazy"; verified it loads at 390 and 1280 px, 349 and 634 px wide, no overflow)

### Task 7: [Final] Update documentation
- [x] update README.md ("all 11 published pages" -> 12; mention the second form in the Checks paragraph and the form copy)
- [x] add a news item in `src/content/news/` only if the user wants an announcement (ask) (skipped - not requested)
- [x] move this plan to `docs/plans/completed/` (done by the harness after all review phases)

## Post-Completion
*Items requiring manual intervention or external systems - no checkboxes, informational only*

**Manual verification**:
- ODRMaker authors fact-check the article text and the accuracy statements
- decide whether publishing is appropriate while PRs #254 (draft) and #255 are unmerged
- check on a phone and with keyboard-only navigation

**External system updates**:
- upload `dist/` contents to OVH `www/` (see README deploy section)
- submit the article form once after deploy and confirm the email arrives with `source=ai-junction-mapping`

**Open points for the ODRMaker authors (from code review)**:
- confirm the corpus status (5 accepted / 2 rejected) after the 2026-11-24 Lelystad rebuild; the article currently states no counts (facts note C4, open point 3)
- confirm which mask and tolerance the 23 cm worst-boundary figure refers to (facts D9, open points 1-3)
- the article deliberately omits the PR #255 features (in-editor SmartVertex / VLM mapping)
- the page says "in development" with a date ("as of November 2026") so it does not go stale; update or remove when the feature ships
- `docs/plans/ai-junction-mapping-facts.md` is internal (Russian quotes, PR numbers) and untracked via `.gitignore` (`docs/plans/*-facts.md`); it stays on disk only
