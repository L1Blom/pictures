# Picture Analysis & Enhancement Tool

A Python project that analyzes pictures using AI vision models (Ollama local models or OpenAI) to generate detailed EXIF metadata, intelligently enhances them, and restores old slides.

## Features

### ✅ Implemented Features

**Image Analysis**
- Analyze pictures with **Ollama** (local models, e.g. `llama3.2-vision:11b`) or OpenAI Vision API (GPT-4 Turbo)
- Local Ollama analysis runs fully offline — no API key or cloud costs required
- Detect 11 comprehensive aspects:
  - Objects and subjects
  - Persons/people count and positioning
  - Weather conditions
  - Mood/atmosphere
  - Time of day estimation
  - Season and date detection
  - Scene type classification
  - Location/setting identification
  - Activity detection
  - Photography style
  - Composition quality assessment
- **✨ Location Detection with GPS Embedding**:
  - Auto-detect geographic location from visual clues
  - Confidence scoring (0-100%)
  - Generate GPS coordinates when confidence ≥ threshold (default 80%)
  - Embed in standard EXIF GPS IFD for Immich map display
  - Works globally with Nominatim geocoding service
  - Caching to avoid repeated API calls
- Generate and embed EXIF metadata in user's language
- Support for multiple image formats: JPG, PNG, GIF, BMP, TIFF, WebP, **HEIC/HEIF** (Apple devices)
- Batch processing of multiple images

**Smart Enhancement**
- AI-guided enhancement from analysis recommendations
- Automatic adjustment of lighting, contrast, saturation, and sharpness
- Smart factor calculation from percentage recommendations
- Separate enhancement recommendations (not cluttering EXIF)

**Slide Restoration**
- Specialized restoration for scanned old slides and dia positives
- 6 restoration profiles:
  - **faded**: Very faded slides with lost color and contrast
  - **color_cast**: Generic color casts from aging
  - **red_cast**: Red/magenta color casts (cool down red, boost green/blue)
  - **yellow_cast**: Yellow/warm color casts (boost blue)
  - **aged**: Moderately aged with some fading
  - **well_preserved**: Minimal aging
- **AI-guided profile recommendations**: Analysis automatically suggests best restoration profiles with confidence scores
- **Multiple profile processing**: Auto-detection can generate multiple restored versions with different profiles for comparison
- Auto-detection of slide condition from analysis
- 7-step restoration pipeline: despeckle → color balance → brightness → contrast → saturation → denoise → sharpness

**CLI Tool**
- 7 commands: `analyze`, `batch`, `enhance`, `process`, `restore-slide`, `report`, `gallery`
- `process` command: single image - analyze → enhance → optionally restore
- `batch` command: multiple images with optional enhancement and restoration in one pass
- `report` command: generate comprehensive markdown report with tables and image references
- `gallery` command: generate visual image gallery table showing original, enhanced, and restored versions
- Extensive help and argument validation
- Output directory organization with progress tracking
- Error handling and success reporting

**Metadata & EXIF**
- Automatic EXIF embedding with analysis data in user's language
- **Language Support**: Metadata generated in configured language (Dutch, English, French, German, Spanish, etc.)
- **Location Detection**: Auto-detects geographic location with confidence scoring (0-100%)
- **GPS Coordinates**: Auto-generates and embeds GPS when confidence ≥ threshold (default 80%)
  - Uses Nominatim (OpenStreetMap) geocoding service
  - Stores in standard EXIF GPS IFD for map display compatibility
  - Caches results to minimize API calls
- **ImageDescription Field**: All metadata + location formatted for Immich display
- **UserComment Field**: Complete JSON backup of all analysis data
- EXIF copying between processed images
- High-quality preservation (quality=95)
- Separates metadata (for EXIF) from enhancement data (JSON only)

**Report & Gallery Generation**
- Markdown report generation from analysis results
- Summary table with numbered images and key details
- Detailed analysis for each image with full metadata tables
- Description.txt content integration
- Image references and restoration profile recommendations
- Enhancement suggestions display
- Visual image gallery table with original, enhanced, and restored versions
- Consistent image sizing in gallery (150px width)

### 🔜 Planned Features
- Web interface for easier use
- Database storage of analysis results
- Advanced noise reduction algorithms
- Image upscaling/resolution enhancement

## Setup

### Prerequisites
- Python 3.8+
- **Ollama** (recommended) — install from [ollama.com](https://ollama.com), then `ollama pull llama3.2-vision:11b`
- OpenAI API key (optional, only if using OpenAI provider)

### Installation

1. Clone or initialize the repository:
```bash
git clone <repository-url>
cd pictures
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
Create a `.env` file or `config.yaml` (see `config.yaml.example`):
```yaml
# config.yaml — Ollama (local, no API key needed)
ollama:
  model: llama3.2-vision:11b
  base_url: http://127.0.0.1:11434
  num_ctx: 16384
  timeout: 1200
  keep_alive: 2h

metadata:
  language: nl   # nl, en, de, fr, es, ...

pipeline:
  mode: stepped  # stepped|single
```

Or for OpenAI:
```
OPENAI_APIKEY=your-openai-api-key
METADATA_LANGUAGE=nl
GPS_CONFIDENCE_THRESHOLD=80
```

## Configuration

### Language Support
The system automatically generates metadata and location names in your configured language:
```bash
export METADATA_LANGUAGE=nl  # Dutch
export METADATA_LANGUAGE=en  # English
export METADATA_LANGUAGE=de  # German
export METADATA_LANGUAGE=fr  # French
export METADATA_LANGUAGE=es  # Spanish
```

Supported in:
- All metadata field labels and descriptions
- Location names (country, region, city)
- EXIF ImageDescription display

### GPS Configuration
Control GPS coordinate embedding:
```bash
export GPS_CONFIDENCE_THRESHOLD=80  # Only embed GPS when 80%+ confident (default)
export GPS_CONFIDENCE_THRESHOLD=90  # Conservative: 90%+ confidence required
export GPS_CONFIDENCE_THRESHOLD=50  # Aggressive: embed most detections
```

GPS coordinates are:
- Generated via Nominatim (OpenStreetMap) geocoding service
- Stored in standard EXIF GPS IFD (latitude, longitude, datum)
- Compatible with Immich map display and standard photo tools
- Cached locally to minimize API calls
- Only embedded when confidence threshold is met

## Usage

### Quick Start with CLI

```bash
# Analyze a single image
python cli.py analyze picture.jpg

# Analyze and save with EXIF
python cli.py analyze picture.jpg -o output/

# Batch analyze a directory
python cli.py batch pictures/

# Batch with full processing: analyze → enhance → restore-slide (specific profile)
python cli.py batch pictures/ --enhance --restore-slide red_cast

# Batch with auto-detect slide restoration
# Generates multiple restored versions if multiple profiles recommended
python cli.py batch pictures/ --enhance --restore-slide

# Full workflow for single image: analyze → enhance → restore-slide (specific profile)
python cli.py process picture.jpg --restore-slide red_cast

# Auto-detect slide restoration profile with AI recommendations
# May generate multiple restored versions for comparison
python cli.py process picture.jpg --restore-slide

# Restore slide with specific profile only
python cli.py restore-slide picture.jpg -p faded -o output/restored.jpg

# Generate markdown report from analysis results
python cli.py report output/

# Generate report and save to specific location
python cli.py report output/ -o my_report.md

# Generate image gallery showing original, enhanced, and restored versions
python cli.py gallery output/

# Generate gallery and save to specific location
python cli.py gallery output/ -o my_gallery.md
```

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
from picture_analyzer import PictureAnalyzer
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

## Project Structure

```
pictures/
├── .env                      # Environment variables (not in git)
├── .gitignore               # Git ignore file
├── requirements.txt         # Python dependencies
├── README.md                # This file
├── ROADMAP.md               # Development roadmap
├── SETUP_COMPLETE.md        # Setup summary
├── SLIDE_RESTORATION_GUIDE.md # Detailed slide restoration docs
│
├── cli.py                   # Command-line interface (7 commands)
├── picture_analyzer.py      # OpenAI Vision API analysis
├── picture_enhancer.py      # Smart enhancement engine
├── slide_restoration.py     # Specialized slide restoration
├── exif_handler.py          # EXIF metadata handling
├── report_generator.py      # Markdown report generation
├── config.py                # Configuration and prompts
│
└── output/                  # Results directory
    ├── report.md                    # Generated detailed analysis report
    ├── gallery.md                   # Generated image gallery
    ├── [image_name]_analyzed.jpg    # Original + EXIF
    ├── [image_name]_analyzed.json   # Detailed analysis
    ├── [image_name]_enhanced.jpg    # Enhanced version (if generated)
    ├── [image_name]_restored_[profile].jpg  # Restored version (if generated)
    └── description.txt              # Optional context file (user-created)
```

## Configuration

Settings can be adjusted in `config.py`:
- OpenAI API model (GPT-4 Turbo with vision)
- Analysis prompts (11 metadata + enhancement recommendations)
- Supported image formats
- EXIF tag mappings
- Slide restoration profiles

## Environment Setup

1. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set your OpenAI API key:
```bash
echo "OPENAI_APIKEY=sk-..." > .env
```

## Documentation

- **[ROADMAP.md](ROADMAP.md)** - Development phases and planned features
- **[SLIDE_RESTORATION_GUIDE.md](SLIDE_RESTORATION_GUIDE.md)** - Detailed guide for slide restoration
- **[SETUP_COMPLETE.md](SETUP_COMPLETE.md)** - Project setup summary

## API Usage Notes

- Each image analysis makes one request to OpenAI Vision API
- Costs depend on image size (tokens used)
- Consider batch processing with `batch` command for multiple images
- HEIC/HEIF support requires pillow_heif library (included in requirements)

## Future Enhancements

- [ ] Web UI for interactive use
- [ ] Database storage for analysis results
- [ ] Advanced algorithms (noise reduction, upscaling)
- [ ] Result caching and indexing
- [ ] Image tagging and organization
- [ ] Docker containerization

## License

MIT
