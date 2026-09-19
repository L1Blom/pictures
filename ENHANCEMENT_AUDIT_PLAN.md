# Enhancement Quality Audit — Plan

**Goal:** Determine whether the AI enhancement recommendations (`_enhanced.jpg`) and the
predefined restoration profiles (`_restored_<profile>.jpg`) actually produce the best
possible results, using an independent OpenAI judge.

**Status:** Approved 2026-09-18. Implementation: `enhancement_auditor.py` (standalone,
read-only). Results go to `audit_output/`.

## Decisions (confirmed by user)

| Decision | Choice |
|----------|--------|
| Judge model | `gpt-4.1` or newer (≠ analyzer `gpt-4o-mini`, avoids self-agreement bias) |
| Sampling | Stratified by restoration profile × decade, 50 images |
| Comparison scope | All variants (original + `_enhanced` + every `_restored_<profile>`) |
| Feedback loop | Judge proposes corrected parameters in the pipeline DSL |
| Output | Markdown summary report + HTML gallery (+ per-image JSON) |

## Corpus facts (measured 2026-09-18)

- `~/enhanced` contains ~15,876 `_analyzed.jpg` (untouched originals), ~15,804 `_enhanced.jpg`,
  ~27,560 `_restored_*.jpg`, ~15,875 `_analyzed.json`.
- Restored profile distribution: `well_preserved` 11,885 · `aged` 11,530 · `yellow_cast` 2,415 ·
  `faded` 943 · `color_cast` 685 · `red_cast` 97.
- Junk/hallucinated profile names exist in the corpus (`foggy`, `flooded`, `well_persu-er`,
  `well_presi…`) — a pipeline bug to flag, excluded from the audit sample.
- Images are ~5–6 MB JPGs → must be downscaled to ~1024px before sending to the Vision API.

## Phase 1 — Stratified sample of 50 images

- Walk `~/enhanced` (following symlinks) for images having the complete set:
  `*_analyzed.jpg` + `*_analyzed.json` + `*_enhanced.jpg` + ≥1 `*_restored_<profile>.jpg`.
- Stratify by restoration profile × decade (decade parsed from folder names like `1985-10 …`):
  - Guarantee coverage of rare profiles: `red_cast`, `color_cast`, `yellow_cast`, `faded`
    (e.g. 4–6 images each).
  - Fill the remainder proportionally from dominant `well_preserved` / `aged`, spread across
    decades 1950s→2010s.
- Fixed random seed; sample manifest saved as JSON (reproducible, re-runnable).
- Flag hallucinated profile names as a pipeline bug finding in the report.

## Phase 2 — Objective metrics (local, free, no API)

For every variant of each image (original, `_enhanced`, each `_restored_*`):

- Exposure: mean luminance, highlight clipping %, shadow clipping %
- Contrast: std-dev of luminance
- Color: mean saturation, R/G/B channel balance (cast detection)
- Sharpness: Laplacian variance (and halo/oversharpening indicator)
- Deltas vs. the original

These give hard numbers to cross-check the LLM judge and catch over-processing
(blown highlights, oversaturation) even where the judge is generous.

## Phase 3 — LLM judge (OpenAI Vision, gpt-4.1 or newer)

Images downscaled to ~1024px JPEG before upload (cost + token control). Two calls per image:

1. **Blind multi-way ranking** — all variants sent with randomized labels (A/B/C…), judge
   unaware which is the original. Scores each 1–10 on exposure, color fidelity,
   sharpness/noise, artifact-freeness, overall; then ranks them. Blind ordering prevents
   "enhanced must be better" bias.
2. **Recommendation audit** — original + the JSON's `recommended_enhancements` + chosen
   `slide_profiles` shown to the judge. It answers:
   - Were the recommendations appropriate, too strong, or too weak?
   - Was the profile choice correct for this slide's condition?
   - What *should* the parameters be — expressed in the pipeline's own DSL
     (`BRIGHTNESS: increase by X%`, `UNSHARP_MASK: radius=…`, etc.) so findings map
     directly onto prompt/profile tuning.

## Phase 4 — Outputs (in `audit_output/`)

- **Markdown summary report**: win rates (enhanced vs. original vs. each restored profile),
  which pipeline wins per profile type, systematic biases in recommendations,
  objective-metric vs. judge correlations, concrete tuning suggestions for
  `RESTORATION_PROFILES` and the analysis prompt.
- **HTML gallery**: side-by-side image comparisons per sample with scores, rankings, and
  judge verdicts for human spot-checking in the browser.
- Per-image JSON verdicts kept alongside for later re-analysis.

## Cost & runtime estimate

- ~50 images × 2 calls, ~3–5 variants per ranking call at 1024px → roughly **$15–40 total**
  with gpt-4.1 (depends on variant count per image), plus ~1 minute of local metrics.
- Sequential with modest rate limiting: ~30–60 minutes wall clock.

## Key design safeguards

- Judge model ≠ analyzer model (`gpt-4o-mini`) → no self-agreement bias.
- Blind labels + randomized order → no position bias.
- Read-only: originals in `~/enhanced` are never modified.
- Reproducible via seed + manifest; resumable per-image (skip already-audited).

## Open point (decide after first report)

- Optional Phase 5: apply the judge's suggested parameters to originals and re-score to
  prove the headroom empirically.
