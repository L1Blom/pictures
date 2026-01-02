# Picture Analysis & Enhancement Tool

A Python project that analyzes pictures using OpenAI API to generate EXIF metadata with detected topics, and enhances pictures.

## Features

### Current Features
- Analyze pictures with OpenAI Vision API
- Detect multiple aspects:
  - Objects in the image
  - Persons/people detection
  - Weather conditions
  - Mood/atmosphere
  - Time of day estimation
  - Date estimation (if visible)
- Generate and embed EXIF data
- Support for common image formats (JPG, PNG, etc.)

### Planned Features
- Picture enhancement (color correction, resolution upscaling, etc.)
- Batch processing
- Image filtering and organization based on detected topics
- Web interface for easier use

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

### Basic Picture Analysis

```python
from picture_analyzer import PictureAnalyzer

analyzer = PictureAnalyzer()
results = analyzer.analyze_picture('path/to/image.jpg')
print(results)
```

### Analyze and Save with EXIF

```python
from picture_analyzer import PictureAnalyzer

analyzer = PictureAnalyzer()
analyzer.analyze_and_save('path/to/image.jpg', 'output/image.jpg')
```

## Project Structure

```
pictures/
├── .env                 # Environment variables (not in git)
├── .gitignore          # Git ignore file
├── requirements.txt    # Python dependencies
├── README.md           # This file
├── picture_analyzer.py # Main analysis module
├── exif_handler.py    # EXIF metadata handling
├── config.py          # Configuration settings
└── pictures/          # Sample pictures directory
```

## Configuration

Settings can be adjusted in `config.py`:
- API model selection
- Analysis prompts
- Output formats
- EXIF tag mappings

## API Usage Notes

- Each picture analysis makes a request to OpenAI Vision API
- Costs depend on image size (tokens)
- Consider batch processing for multiple images

## Future Enhancements

- [ ] Picture enhancement algorithms
- [ ] Web UI
- [ ] Batch processing with progress tracking
- [ ] Result caching
- [ ] Image tagging and organization
- [ ] Database storage for results

## License

MIT
