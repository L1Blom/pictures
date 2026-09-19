# Updates & Changelog

## September 2026 — v1.4

### Enhancement Quality Audit & Pipeline Retuning

A systematic audit of the enhancement pipeline (50-image stratified sample, blind
LLM judging with gpt-4.1) revealed that the **untouched original won 62% of blind
rankings** — the enhancers were making most photos worse. Root causes were found
and fixed; after retuning, the AI-enhanced version is the single best variant
(44% wins vs the original's 36%).

**Audit tooling** — new `enhancement_auditor.py` (standalone, read-only):
- Stratified sampling by restoration profile × decade (`sample`)
- Objective image metrics: luminance, contrast, saturation, cast, sharpness (`metrics`)
- Blind multi-way LLM judging with randomized labels, two styles:
  `faithful` (naturalness-first) and `vivid` (lively family-album look) (`judge --style`)
- Recommendation auditing: were the analyzer's suggestions appropriate? (`judge`)
- Markdown report + HTML side-by-side gallery + per-image score table (`report`, `scores`)
- Regeneration of variants with current settings, optionally reusing existing
  analysis JSONs to isolate enhancement-side changes (`regenerate --reuse-analysis`)
- Results in `audit_output/` (gitignored)

**Analyzer prompt fixes** (`src/picture_analyzer/data/templates/`, all 4 templates
including the `black`/`blue`/`red` tag variants):
- Brightness rules recalibrated for the vivid goal: genuinely dark slides now get
  +15–40% instead of the old 10% cap that left them dark
- Cast-direction self-check: warm cast = cool it, cool cast = warm it — with an
  explicit stop-rule against corrections that compound the described cast
- "Natural warm light is not a cast": golden-hour/tungsten atmosphere is preserved
- Monochrome images never get color operations
- Hard rule: neutral whites/greys → zero color corrections

**Restoration profile tuning** (`slide_restoration.py` + mirrored in
`src/picture_analyzer/data/profiles/*.yaml`): the old values oversaturated and
oversharpened (e.g. `faded`: saturation 1.5, contrast 1.6 — never won a blind
ranking). Pulled back toward the user's preferred intensity (e.g. `faded`:
1.25/1.3, `aged`: 1.18/1.22; `well_preserved` unchanged).

**Deterministic safety gates** (`picture_enhancer.py`, `SmartEnhancer`) — the small
local analyzer model only partially obeys prompt rules, so the enhancer now
enforces limits by measuring the original image directly:

| Gate | Trigger (measured on original) | Action |
|------|-------------------------------|--------|
| Cast-gate | color cast < 0.03 (neutral) | Drop color temperature + channel ops |
| Highlight-gate | luma ≥ 0.45 or highlight clipping ≥ 3% | Drop brightness increases + shadow brightening |
| Saturation-gate | mean saturation ≥ 0.55 | Drop vibrance/saturation increases |
| Sharpness-gate | already sharp (lap_var ≥ 1900), or stacked SHARPNESS + UNSHARP_MASK | Drop/cap sharpening (max 1.15×, unsharp ≤ 60%) |
| Exposure budget | (b−1) + 0.5(c−1) + 0.5(shadows/100) > adaptive cap | Trim shadows → brightness → contrast |

The exposure budget is adaptive: `0.35 + 0.40 × (1 − luma)` — dark slides get more
brightening headroom than bright images. Bright originals also get a tight
contrast cap (1.05×) because contrast alone was blowing highlights.

**Hallucinated profile fix**: AI-invented profile names (e.g. `_restored_foggy.jpg`)
are now validated against the 6 real profiles in both `_resolve_profiles`
(`src/picture_analyzer/cli/app.py`) and `auto_restore_slide`
(`slide_restoration.py`); unknown names are dropped with a warning instead of
being written into filenames. (Also fixed a duplicated `@staticmethod`
decorator in `slide_restoration.py`.)

**Measured results** (50-image sample, vivid judging, v1 → v8 audit cycles):

| Metric | Before | After |
|--------|--------|-------|
| Enhanced wins blind ranking | 14% | **44%** (top variant) |
| Original wins | 62% | 36% |
| Blown highlights | 29/50 | 14/50 |
| Cast drift (enhanced vs original) | 0.084 | 0.038 |
| Max sharpening increase | +363% | +150% |

See `ENHANCEMENT_AUDIT.md` for the full methodology and per-cycle results.

### Landmark Geocoding (pre-existing uncommitted work, included)

- `GeocodingStep` now builds a `location_data` dict and calls
  `geocode_from_location_info`, which supports `landmark_name` for precise
  geocoding (e.g. "Centre Pompidou, Paris, France" → exact GPS)
- Landmark results are validated against the city/region location: if a landmark
  geocodes > 50 km from the expected area, the LLM likely invented a
  non-standard name and the geocoder falls back to city-level geocoding
- "No landmark" responses in various languages are filtered out
- Location prompt/footer templates updated to request landmark names

---

## April 2026 — v1.3

### Ollama Local AI Support
- Added `OllamaAnalyzer` (`src/picture_analyzer/analyzers/ollama.py`) — full drop-in replacement for OpenAI in all pipeline modes
- Runs fully offline with no API key; tested with `llama3.2-vision:11b`
- Configurable via `config.yaml`: `model`, `base_url`, `num_ctx`, `timeout`, `keep_alive`
- Stepped pipeline mode runs each section (metadata, location, enhancement, slide_profiles) as a separate AI call

### Batch Hallucination Fixes
Three independent root causes identified and fixed:

| Problem | Root Cause | Fix |
|---|---|---|
| Visual bleed between batch images | Ollama KV-cache reuses prefix states from previous image | `subprocess.run(["ollama", "stop", model])` in `finally` block after each image |
| `Activiteit:` copied verbatim into `scene_type` | Dutch activity field injected into prompt without stripping | Strip `Activiteit:`, `Personen:`, `Opmerkingen:` from prompt context |
| Infinite repetition in `objects` field | Model enters repetition loop (e.g. "badkamermeubel, badkamermeubel…") | Added `repeat_penalty: 1.3` to Ollama API options |
| Phantom person from `Notes:` biography | Model infers person from biography text, hallucinates them into image | Strip `Notes:` / `Opmerkingen:` from prompt context |
| Cage → prison hallucination | No visual-only constraint on scene_type | Added explicit instruction: "A cage containing animals is NOT a prison" |

**Files changed:**
- `src/picture_analyzer/analyzers/ollama.py` — regex extended to strip `personen|activiteit|opmerkingen|notes`; cage instruction added; `repeat_penalty: 1.3`
- `src/picture_analyzer/cli/app.py` — `finally` block after each batch image calls `ollama stop`

### Dutch description.txt Support
Previously only English field names were recognised. Now both Dutch and English are supported:

| Field | Dutch | English |
|---|---|---|
| Date → EXIF DateTimeOriginal | `Datum:` | `Date:` |
| Location → GPS ground truth | `Locatie:` | `Location:` |
| Persons (stripped) | `Personen:` | `People:` |
| Activity (stripped) | `Activiteit:` | `Activity:` |
| Notes (stripped) | `Opmerkingen:` | `Notes:` |

Also added the `D Month YYYY` date format (e.g. `25 december 1986`) to the date parser alongside the existing `Month YYYY`, `Month D, YYYY`, and ISO formats.

**Files changed:**
- `src/picture_analyzer/metadata/exif_writer.py` — `(?:date|datum)` regex; `D Month YYYY` pattern
- `src/picture_analyzer/analyzers/ollama.py` — `(?:location|locatie)` regex in `_enforce_location_from_description`

### Token Statistics in Pipeline Output
Each stepped pipeline step now shows prompt/output token counts and generation speed:
```
✓ [metadata] done in 159.0s  (847→312 tok, 2.0 tok/s)
✓ [location] done in 131.3s  (612→98 tok, 1.9 tok/s)
```

**Files changed:**
- `src/picture_analyzer/analyzers/ollama.py` — stores `_last_call_stats` after each API call
- `src/picture_analyzer/pipeline/pipeline.py` — `_format_tok_stats()` helper; stats appended to `done in` line

---

## January 2026 — v1.2

- Location detection with confidence scoring
- GPS coordinate generation and EXIF embedding via Nominatim (OpenStreetMap)
- Multi-language metadata support (nl, en, de, fr, es, …)
- Stepped pipeline mode (`--pipeline-mode stepped`)
- `--skip-existing` flag for resumable batch runs
- Slide profile auto-detection in analysis

---

## 2025 — v1.0 / v1.1

- Initial OpenAI Vision API integration
- Batch processing, EXIF embedding, enhancement pipeline
- Slide restoration with 6 profiles
- CLI: `analyze`, `batch`, `enhance`, `process`, `restore-slide`, `report`, `gallery`
- description.txt context injection (English)
