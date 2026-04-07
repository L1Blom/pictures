# Updates & Changelog

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
