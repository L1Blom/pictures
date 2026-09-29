# Picture Analysis & Enhancement Tool

A Python project that analyzes pictures using AI vision models (Ollama local models or OpenAI) to generate detailed EXIF metadata, intelligently enhances them, restores old slides, and — via a browser-based **admin UI** — lets you review, pick, reorder, and publish the results into [Immich](https://immich.app/).

**New here?** → **[SETUP.md](SETUP.md)** is a complete, step-by-step guide from `git clone` to a running admin UI. This README is the feature/reference overview.

## Features

**Image Analysis**
- Analyze pictures with **Ollama** (local models, e.g. `llama3.2-vision:11b`, `ministral-3:3b`) or the **OpenAI** Vision API (`gpt-4o-mini` by default)
- Local Ollama analysis runs fully offline — no API key or cloud costs required
- Two pipeline modes: `single` (one AI call, all sections) or `stepped` (one call per section, steps can run in parallel and use different models/providers — see [Pipeline Modes](#pipeline-modes))
- Detects: objects/subjects, people count, weather, mood, time of day, season/date, scene type, location/setting, activity, photography style, composition quality
- **Location detection with GPS embedding** — visual-clue/landmark recognition, confidence scoring, geocoded via Nominatim, embedded in standard EXIF GPS IFD (Immich map display)
- Multiple image formats: JPG, PNG, GIF, BMP, TIFF, WebP, **HEIC/HEIF**
- Batch processing with a `description.txt` per folder for ground-truth date/location context (see below)

**Smart Enhancement**
- AI-guided enhancement (brightness, contrast, saturation, sharpness) from the analysis recommendations
- **Deterministic safety gates**: measures each original image and automatically drops/caps recommendations that would introduce a color cast on neutral images, blow highlights, over-saturate, or over-sharpen. An adaptive exposure budget prevents stacked brightness/contrast/shadow operations from overbrightening. See [ENHANCEMENT_AUDIT.md](ENHANCEMENT_AUDIT.md) for how these were calibrated.

**Slide Restoration**
- 6 restoration profiles for scanned slides/dia positives: `faded`, `color_cast`, `red_cast`, `yellow_cast`, `aged`, `well_preserved`
- AI-suggested profiles with confidence scores; auto-detect can generate multiple restored versions for comparison
- 7-step pipeline: despeckle → color balance → brightness → contrast → saturation → denoise → sharpness

**Metadata & EXIF**
- EXIF written in your configured language (`nl`, `en`, `de`, `fr`, `es`, ...), including `ImageDescription` (human-readable summary), `UserComment` (full JSON backup), GPS IFD, and `DateTimeOriginal`
- `date_taken` ground truth comes from `description.txt`'s `Datum:`/`Date:` line when present, otherwise a synthetic sequential timestamp is assigned per image (see [Admin Web UI](#admin-web-ui--reviewreorderpublish) for how to fix/reorder these)

**Report & Gallery**
- `report` — Markdown report: summary table + full per-image metadata
- `gallery` — Markdown gallery table with original/enhanced/restored thumbnails

**Admin Web UI** (Flask app, `api.py`) — browse folders, review/pick the best variant per photo, edit `description.txt`, run analyze/enhance/restore jobs with live per-image progress, and publish to Immich. See [Admin Web UI](#admin-web-ui--reviewreorderpublish) below.

**Immich Integration** — publish your picked "best" variants into a dedicated Immich external library and keep albums (assets, sort order, description) in sync declaratively. See [Immich Integration](#immich-integration) below.

## Setup

Full walkthrough: **[SETUP.md](SETUP.md)**. Short version:

```bash
git clone <repository-url> && cd pictures
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.yaml.example config.yaml   # then edit: provider, language, photos_root, ...
echo "OPENAI_APIKEY=sk-..." >> .env  # only if using the OpenAI provider
picture-analyzer analyze path/to/photo.jpg   # or: python cli.py analyze ...
python api.py --port 7000            # admin UI at http://127.0.0.1:7000/admin
```

Requires Python **3.10+**. For local/offline analysis, install [Ollama](https://ollama.com) and pull a vision model (e.g. `ollama pull llama3.2-vision:11b`); no system dependencies (no exiftool/ffmpeg) are needed — all EXIF/XMP writing is pure Python (`piexif`).

## CLI Reference

Installed as the `picture-analyzer` console script (`pyproject.toml`), or run directly as `python cli.py` (older argparse-based entry point, being phased out) — the commands below are for the current Click-based CLI (`src/picture_analyzer/cli/app.py`):

| Command | Description |
|---|---|
| `analyze IMAGE\|DIR --batch` | Analyze a single image, or a whole folder with `--batch`. Options: `--output`, `--provider {openai,ollama}`, `--enhance`, `--restore-slide {auto,faded,color_cast,red_cast,yellow_cast,aged,well_preserved}`, `--pipeline-mode {single,stepped}`, `--skip-existing`, `--steps`, `--update-existing` |
| `process IMAGE` | Analyze → enhance → optionally restore, in one step |
| `regenerate SOURCE --batch` | Re-render enhanced/restored images from *existing* analysis JSON — no AI calls |
| `report DIRECTORY` | Generate a Markdown analysis report |
| `gallery DIRECTORY` | Generate a Markdown image gallery |
| `update-exif OUTPUT_DIR SOURCE_DIR` | Re-write EXIF from the current `description.txt` without re-analyzing |
| `check-locations ROOT_DIR` | Check/geocode locations from every `description.txt` under a root |
| `config` | Print the fully-resolved current configuration (JSON) |
| `publish-immich DIRECTORY` | Publish a folder's picked variants into the Immich picks library |
| `sync-immich` | Make Immich albums mirror the picks library (`--scan` to trigger a library scan first) |

Run `picture-analyzer <command> --help` for full option details. (`batch`, `enhance`, `restore-slide` still work as hidden legacy aliases for `analyze --batch`/`process`/`process --restore-slide`.)

### Report Generation

The `report` command creates a comprehensive markdown file with:
- **Summary Table**: Numbered images with key metadata (objects, persons, location, mood)
- **Detailed Analysis** for each image:
  - Description.txt content (if available)
  - Image references (original, enhanced, restored)
  - Complete metadata table (11 aspects)
  - Enhancement recommendations
  - Slide restoration profile recommendations with confidence scores

### Gallery Generation

The `gallery` command creates a visual markdown table showing all analyzed images:
- **6-Column Table**: Image number, name, original, enhanced, and up to 2 restored profiles
- **Image Display**: Thumbnails (150px width) for consistent display
- **Profile Names**: Restoration profile names displayed with each restored image
- **Smart Display**: Shows enhanced and restored versions only when available
- **Flat Directory Support**: Works with images directly in the output directory

### Pipeline Modes

The analyzer supports two analysis pipeline modes, selectable per-invocation or via configuration.

| Mode | Description |
|------|-------------|
| `single` (default) | One AI call returns all analysis sections — identical to pre-pipeline behaviour |
| `stepped` | Each section (metadata, location, enhancement, slide profiles) is a separate AI call, followed by GPS geocoding |

**Select mode via CLI flag:**
```bash
# Use stepped pipeline for a single image
picture-analyzer analyze photo.jpg --pipeline-mode stepped

# Batch-process with stepped pipeline
picture-analyzer analyze photos/ --batch --pipeline-mode stepped
```

**Select mode via environment variable** (persists for the session):
```bash
export PA_PIPELINE__MODE=stepped
picture-analyzer analyze photo.jpg
```

**Select mode via `config.yaml`:**
```yaml
pipeline:
  mode: stepped          # "single" | "stepped"
  location:
    enabled: false       # skip the location step entirely
  slide_profiles:
    model: gpt-4o        # use a different model for this step only
```

Per-step overrides let you route each section to a different model or provider, or disable individual steps without changing the others. See [`config.yaml.example`](config.yaml.example) for the full list of knobs and [`PIPELINE_DECOUPLING_PROPOSAL.md`](PIPELINE_DECOUPLING_PROPOSAL.md) for design rationale.

### Context-Aware Analysis with description.txt

Place a `description.txt` in the image folder to provide ground-truth context to the AI. Supported in both Dutch and English.

**Dutch example:**
```
Albumnaam: 1986-12-25 Geboorte Leendert-Jan
Locatie: Han Hollanderweg 17, Gouda, Nederland
Datum: 25 december 1986
Personen: Leendert en Leny Blom, Leendert-Jan Blom en familieleden
Activiteit: Geboorte, kraamtijd, doop en bezoek
Weer: n.v.t.
Stemming: Vrolijk, blij
```

**English example:**
```
Album: 1984 Goes streetscapes
Location: Goes, Zeeland, Netherlands
Date: June 1984
Activity: Documenting the old town centre
```

**Field handling:**

| Field | Dutch | English | Used for |
|---|---|---|---|
| Location/date | `Locatie:`, `Datum:` | `Location:`, `Date:` | EXIF DateTimeOriginal, GPS ground truth |
| Persons/activity | `Personen:`, `Activiteit:` | `People:`, `Activity:` | **Stripped** — prevents hallucination |
| Notes | `Opmerkingen:` | `Notes:` | **Stripped** — prevents biography → person hallucination |

Stripping person/activity fields prevents the AI from copying description text verbatim into metadata fields instead of deriving them from the image.

### Python API

```python
from picture_analyzer_legacy import PictureAnalyzer
from picture_enhancer import SmartEnhancer
from slide_restoration import SlideRestoration

# Analyze an image
analyzer = PictureAnalyzer()
analysis = analyzer.analyze_and_save('image.jpg', 'output.jpg')

# Enhance from analysis
enhancer = SmartEnhancer()
enhancer.enhance_from_analysis('analyzed.jpg', analysis['enhancement'], 'enhanced.jpg')

# Restore a slide
SlideRestoration.restore_slide('image.jpg', profile='red_cast', output_path='restored.jpg')

# Auto-detect slide condition
condition = SlideRestoration.analyze_slide_condition(analysis)
print(f"Detected: {condition['condition']} ({condition['confidence']:.0%})")
```

## Admin Web UI — review/reorder/publish

`python api.py --port 7000` starts a Flask server at `http://127.0.0.1:7000` serving two apps:
- **`/`** — a lightweight description-editor UI for writing each folder's `description.txt`
- **`/admin`** — the main admin single-page app:
  - **Folder sidebar** — every folder under `photos_root`, with image counts and pick counts (loaded progressively in the background so it stays fast on slow/networked storage)
  - **Image grid** — thumbnails per folder, sorted by `date_taken` (the order Immich will show them in); badges show enhanced/restored variant counts and the current pick
  - **Viewer** — compare original/analyzed/enhanced/restored variants side by side, zoom/pan, and mark one as the **pick** (★) — only picked images get published to Immich
  - **Reordering** — since Immich always sorts by capture date/time, use the ▲▼ buttons or drag-and-drop to nudge a photo's position (only allowed for images without a real camera EXIF date, e.g. scanned slides — genuinely dated photos are never touched); **🔧 Fix sequence** re-numbers colliding/duplicate dates in one click
  - **Jobs** — Process folder / Analyze only run as background jobs with live `(n/total · filename)` progress; every other action is locked while a job is running
  - **Immich publish/sync** — see below

Run it persistently with the included `picture-analyzer.service` systemd unit — see [SETUP.md](SETUP.md) ("Running as a systemd service").

## Immich Integration

Rather than dumping every generated variant (original/enhanced/restored ×N) into Immich, the workflow publishes only your **picked** "best" version per photo:

1. **Pick** the best variant per image in the admin viewer (★).
2. **Publish** (`📤 Immich publish` button, or `picture-analyzer publish-immich <folder>`) hardlinks each pick into `<picks_root>/<Albumnaam>/<stem>.jpg` — one file per source image, so Immich never sees duplicates. Re-picking replaces the same path.
3. **Sync** (`🔄 Immich sync` button, or `picture-analyzer sync-immich --scan`) makes Immich albums mirror the picks library: creates missing albums (sorted oldest-first), adds/removes assets to match, and pushes each folder's `description.txt` content into the album's description field. It's declarative and idempotent — safe to run repeatedly.

Set up `picks_root` as its own Immich **external library** (see [SETUP.md](SETUP.md) — "Immich integration setup" — for the exact steps) and configure `immich.picks_root` / `immich.url` in `config.yaml` plus `PA_IMMICH__API_KEY` in `.env`.

## Configuration Reference

Priority (highest wins): **CLI args → environment variables → `.env` → `config.yaml` → built-in defaults**.

Copy [`config.yaml.example`](config.yaml.example) to `config.yaml` and uncomment what you need. Key sections:

| Section | Controls |
|---|---|
| `analyzer_provider` | `"openai"` or `"ollama"` |
| `openai:` / `ollama:` | model, host, tokens, timeout, etc. per provider |
| `metadata:` | output language, EXIF/XMP/GPS write toggles, description length |
| `geo:` | geocoding provider, confidence threshold, cache |
| `enhancement:` / `slide_restoration:` | enable/disable, quality, thresholds |
| `output:` | naming patterns, thumbnails, **`enhanced_root`** (admin UI's analysis-output root, default `~/enhanced`) |
| `photos_root` (top-level) | admin UI's source-photos root (default `~/fotos`) |
| `pipeline:` | `mode: single\|stepped`, per-step provider/model overrides — see [Pipeline Modes](#pipeline-modes) |
| `immich:` | `url`, `picks_root`, `immich_picks_root` — **not** `api_key` (see below) |
| `web:` / `report:` / `prompt:` | description-editor UI, report/gallery generation, prompt content toggles |

**Secrets go in `.env`, never `config.yaml`** (which is typically committed to git). Uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) with `PA_` prefix and `__` nesting:

```bash
# .env
OPENAI_APIKEY=sk-...              # legacy flat name, still supported
PA_IMMICH__API_KEY=your-immich-api-key
```

Any config value can also be set via `PA_SECTION__FIELD=value` (e.g. `PA_METADATA__LANGUAGE=nl`, `PA_PIPELINE__MODE=stepped`) — useful for one-off overrides without editing `config.yaml`.

## Project Structure

```
pictures/
├── config.yaml.example        # Copy to config.yaml and customize
├── .env                       # Secrets (not in git): OPENAI_APIKEY, PA_IMMICH__API_KEY
├── requirements.txt / pyproject.toml
├── api.py                     # Flask admin UI + REST API (port 7000)
├── static/admin.html          # Admin single-page app
├── picture-analyzer.service   # systemd unit (see SETUP.md)
│
├── src/picture_analyzer/      # Current implementation (installed as the `picture-analyzer` console script)
│   ├── cli/app.py             #   Click CLI (analyze, process, report, gallery, publish-immich, sync-immich, ...)
│   ├── config/                #   pydantic-settings Settings, defaults, config.yaml loader
│   ├── core/                  #   shared typed data models/protocols
│   ├── analyzers/              #   OpenAI / Ollama vision-model implementations
│   ├── pipeline/               #   the "stepped" per-section analysis pipeline + geocoding step
│   ├── enhancers/               #   new-style enhancement filter pipeline
│   ├── metadata/                #   EXIF/XMP writers (date-aware, unlike the legacy exif_handler.py)
│   ├── geo/                     #   Nominatim geocoding client
│   ├── immich/                  #   client.py / publisher.py / sync.py — see Immich Integration
│   ├── web/editor_app.py        #   description-editor Flask app (mounted at `/` by api.py)
│   └── data/                    #   prompt templates, restoration profile YAMLs, translations
│
├── picture_analyzer_legacy.py, picture_enhancer.py, slide_restoration.py,
│   metadata_manager.py, report_generator.py, exif_handler.py, xmp_handler.py,
│   geolocation.py, config.py, cli_commands.py    # Legacy implementation, still actively used
│                                                  # (wrapped by src/picture_analyzer/cli/app.py)
├── cli.py                     # Old argparse CLI — superseded by `picture-analyzer` but still runnable
│
└── <enhanced_root>/<Albumnaam>/       # Analysis output (configurable, default ~/enhanced)
    ├── <stem>_analyzed.jpg / .json    # Untouched copy + full analysis
    ├── <stem>_enhanced.jpg            # AI-enhanced version (if generated)
    ├── <stem>_restored_<profile>.jpg  # Slide-restored version(s) (if generated)
    ├── report.md / gallery.md         # Generated by `report`/`gallery` commands
    └── description.txt                # Optional per-folder context (user-created, lives in the SOURCE folder)
```

## Further Documentation

- **[SETUP.md](SETUP.md)** — complete setup walkthrough for a fresh clone (incl. Ollama, Immich, systemd)
- **[SLIDE_RESTORATION_GUIDE.md](SLIDE_RESTORATION_GUIDE.md)** — detailed guide for slide restoration profiles
- **[PIPELINE_DECOUPLING_PROPOSAL.md](PIPELINE_DECOUPLING_PROPOSAL.md)** — design rationale for the stepped pipeline
- **[ENHANCEMENT_AUDIT.md](ENHANCEMENT_AUDIT.md)** / **[ENHANCEMENT_README.md](ENHANCEMENT_README.md)** — how the enhancement safety gates were calibrated
- **[BACKUP_RESTORE.md](BACKUP_RESTORE.md)** — backup strategy and disaster-recovery steps for photos/enhanced output/Immich DB
- **[SECURITY.md](SECURITY.md)** — known dependency vulnerabilities and mitigations
- **[ROADMAP.md](ROADMAP.md)** — development phases and planned features

## License

MIT

