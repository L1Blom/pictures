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
- Generate and embed EXIF metadata
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
- Auto-detection of slide condition from analysis
- 7-step restoration pipeline: despeckle → color balance → brightness → contrast → saturation → denoise → sharpness

**CLI Tool**
- 5 commands: `analyze`, `batch`, `enhance`, `process`, `restore-slide`
- `process` command: single image - analyze → enhance → optionally restore
- `batch` command: multiple images with optional enhancement and restoration in one pass
- Extensive help and argument validation
- Output directory organization with progress tracking
- Error handling and success reporting

**Metadata & EXIF**
- Automatic EXIF embedding with analysis data
- EXIF copying between processed images
- High-quality preservation (quality=95)
- Separates metadata (for EXIF) from enhancement data (JSON only)

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
```

## Usage

### Quick Start with CLI

```bash
# Analyze a single image
python cli.py analyze picture.jpg

# Analyze and save with EXIF
python cli.py analyze picture.jpg -o output/

# Batch analyze a directory
python cli.py batch pictures/

# Batch with full processing: analyze → enhance → restore-slide
python cli.py batch pictures/ --enhance --restore-slide red_cast

# Batch with auto-detect slide restoration
python cli.py batch pictures/ --enhance --restore-slide

# Full workflow for single image: analyze → enhance → restore-slide
python cli.py process picture.jpg --restore-slide red_cast

# Auto-detect slide restoration profile
python cli.py process picture.jpg --restore-slide

# Restore slide with specific profile only
python cli.py restore-slide picture.jpg -p faded -o output/restored.jpg
```

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
├── cli.py                   # Command-line interface (5 commands)
├── picture_analyzer.py      # OpenAI Vision API analysis
├── picture_enhancer.py      # Smart enhancement engine
├── slide_restoration.py     # Specialized slide restoration
├── exif_handler.py          # EXIF metadata handling
├── config.py                # Configuration and prompts
│
└── output/                  # Results directory
    └── [image_name]/
        ├── [name]_analyzed.jpg      # Original + EXIF
        ├── [name]_analyzed.json     # Detailed analysis
        ├── [name]_enhanced.jpg      # Enhanced version + EXIF
        └── [name]_restored.jpg      # Restored slide + EXIF (if requested)
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
