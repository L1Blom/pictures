# Picture Analysis & Enhancement Tool

A Python project that analyzes pictures using OpenAI Vision API to generate detailed EXIF metadata, intelligently enhances them, and restores old slides.

## Features

### ✅ Implemented Features

**Image Analysis**
- Analyze pictures with OpenAI Vision API (GPT-4 Turbo with vision)
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
- Multiple AI model support (Claude, local models)
- Advanced noise reduction algorithms
- Image upscaling/resolution enhancement
- Batch optimization and progress tracking

## Setup

### Prerequisites
- Python 3.8+
- OpenAI API key

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
Create a `.env` file with:
```
OPENAI_APIKEY=your-openai-api-key

# Language for EXIF metadata and location names (default: en)
METADATA_LANGUAGE=nl  # e.g., 'nl' for Dutch, 'en' for English, 'de' for German

# GPS confidence threshold for embedding coordinates (default: 80)
# Only embed GPS when location detection confidence >= this threshold
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

### Context-Aware Analysis with description.txt

You can enhance EXIF analysis by placing a `description.txt` file in the output directory. The description provides context that helps AI understand the images better, resulting in more accurate and detailed metadata.

**Example description.txt:**
```
Family vacation in Switzerland, summer 2015.
Taken at Jungfrau region during hiking trip in late July.
Shows traditional alpine village with mountains in background.
Grandpa's 80th birthday celebration gathering.
Weather was partly cloudy, early morning light.
```

When you have a `description.txt` file in the output directory, the analysis will use this context for all images. This improves:
- Location and setting identification
- Event and occasion detection
- People and gathering context
- Time period estimation
- Overall scene understanding

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
- [ ] Multiple AI model support (Claude, local models)
- [ ] Advanced algorithms (noise reduction, upscaling)
- [ ] Result caching and indexing
- [ ] Image tagging and organization
- [ ] Docker containerization

## License

MIT
