# Enhanced Picture Analyzer & Enhancer - Quick Reference

## Quick Start

### Analyze and Enhance a Single Image

```bash
python3 cli.py --analyze image.jpg
# Saves analysis to: output/image_analysis.json

python3 cli.py --enhance output/image_analysis.json image.jpg
# Applies AI-recommended enhancements and saves to: output/enhanced_image.jpg
```

### Batch Process Multiple Images

```bash
# Analyze all images in a directory
python3 cli.py --batch-analyze pictures/Berlijn/

# Enhance all analyzed images
python3 cli.py --batch-enhance pictures/Berlijn/
```

### View Analysis Results

```bash
# Pretty-print analysis
python3 << 'EOF'
import json
with open('output/image_analysis.json') as f:
    data = json.load(f)
    print(json.dumps(data, indent=2))
EOF
```

---

## Example Analysis Output

When you analyze an image, you'll get detailed recommendations like:

```json
{
  "metadata": {
    "objects": ["building", "street", "people", "vehicles"],
    "persons": "Several people visible on street",
    "weather": "Partly cloudy",
    "mood": "Urban, dynamic",
    "time_of_day": "Late afternoon",
    "scene_type": "Street photography",
    "composition_quality": "Good - rule of thirds applied"
  },
  "enhancement": {
    "lighting_quality": {
      "current_state": "Slightly underexposed",
      "recommendation": "increase brightness by 25-30%"
    },
    "color_analysis": {
      "color_temperature": "6400K (slightly cool)",
      "saturation": "Normal",
      "recommendation": "shift color temperature 300K warmer"
    },
    "sharpness_clarity": {
      "overall_sharpness": "Sharp",
      "recommendation": "apply unsharp mask (radius=1.5, amount=80%)"
    },
    "recommended_enhancements": [
      "BRIGHTNESS: increase by 25%",
      "CONTRAST: boost by 20%",
      "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0",
      "COLOR_TEMPERATURE: warm by 300K",
      "VIBRANCE: increase by 20%"
    ]
  }
}
```

---

## Enhancement Recommendations Format

### Basic Adjustments

| Recommendation | Effect |
|---|---|
| `BRIGHTNESS: increase by 25%` | Makes image 25% brighter |
| `BRIGHTNESS: decrease by 15%` | Makes image 15% darker |
| `CONTRAST: boost by 20%` | Increases contrast by 20% |
| `SATURATION: increase by 30%` | More colorful |
| `SATURATION: decrease by 20%` | More grayscale |
| `SHARPNESS: increase by 40%` | Makes details more defined |

### Advanced Adjustments

| Recommendation | Effect |
|---|---|
| `UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0` | Sharpens with specific parameters |
| `COLOR_TEMPERATURE: warm by 500K` | Makes image warmer (more orange/red) |
| `COLOR_TEMPERATURE: cool by 300K` | Makes image cooler (more blue) |
| `SHADOWS: brighten by 20%` | Lifts dark areas |
| `HIGHLIGHTS: reduce by 15%` | Tones down bright areas |
| `VIBRANCE: increase by 25%` | Boosts less-saturated colors |
| `CLARITY: boost by 20%` | Enhances mid-tone contrast |

---

## Programmatic Usage

### Using SmartEnhancer Class

```python
from picture_enhancer import SmartEnhancer

# Create enhancer instance
enhancer = SmartEnhancer()

# Prepare enhancement data with recommendations
enhancement_data = {
    "recommended_enhancements": [
        "BRIGHTNESS: increase by 15%",
        "CONTRAST: boost by 20%",
        "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0",
        "VIBRANCE: increase by 20%"
    ]
}

# Apply enhancements
result = enhancer.enhance_from_analysis(
    image_path="original.jpg",
    enhancement_data=enhancement_data,
    output_path="enhanced.jpg"
)

print(f"Enhanced image saved to: {result}")
```

### Using Individual Enhancement Methods

```python
from picture_enhancer import (
    apply_unsharp_mask,
    adjust_color_temperature,
    adjust_shadows_highlights,
    adjust_vibrance,
    apply_clarity_filter
)

# Sharpen
apply_unsharp_mask(
    image_path="image.jpg",
    radius=1.5,
    percent=80,
    threshold=0,
    output_path="sharpened.jpg"
)

# Warm up the image
adjust_color_temperature(
    image_path="image.jpg",
    kelvin=7000,  # 500K warmer than 6500K neutral
    output_path="warm.jpg"
)

# Brighten shadows
adjust_shadows_highlights(
    image_path="image.jpg",
    shadow_adjust=15,  # Brighten shadows by 15%
    highlight_adjust=0,  # Keep highlights same
    output_path="lifted.jpg"
)

# Increase vibrance
adjust_vibrance(
    image_path="image.jpg",
    factor=1.25,  # 25% more vibrant
    output_path="vibrant.jpg"
)

# Apply clarity
apply_clarity_filter(
    image_path="image.jpg",
    strength=20,  # Mid-tone contrast boost
    output_path="clear.jpg"
)
```

### Full Workflow Example

```python
from picture_analyzer import PictureAnalyzer
from picture_enhancer import SmartEnhancer

# Step 1: Analyze the image
analyzer = PictureAnalyzer()
analysis = analyzer.analyze_image("image.jpg")

print("Image Analysis:")
print(f"  Scene: {analysis['metadata']['scene_type']}")
print(f"  Mood: {analysis['metadata']['mood']}")
print(f"  Recommendations: {len(analysis['enhancement']['recommended_enhancements'])} enhancements")

# Step 2: Enhance based on analysis
enhancer = SmartEnhancer()
enhanced_path = enhancer.enhance_from_analysis(
    image_path="image.jpg",
    enhancement_data=analysis['enhancement'],
    output_path="enhanced.jpg"
)

print(f"\nEnhancement Results:")
print(f"  Original: image.jpg")
print(f"  Enhanced: {enhanced_path}")
print(f"  Improvements applied: {', '.join(analysis['enhancement']['recommended_enhancements'][:3])}...")
```

---

## Command Reference

### CLI Commands

```bash
# Analyze single image
python3 cli.py --analyze <image_path>

# Enhance using analysis
python3 cli.py --enhance <analysis_json> <image_path>

# Batch process directory
python3 cli.py --batch-analyze <directory>
python3 cli.py --batch-enhance <directory>

# Generate report
python3 cli.py --report <analysis_json>

# Generate gallery
python3 cli.py --gallery <directory>
```

---

## Common Enhancement Scenarios

### Underexposed Image
```json
{
  "recommended_enhancements": [
    "BRIGHTNESS: increase by 30%",
    "CONTRAST: boost by 25%",
    "SHADOWS: brighten by 20%"
  ]
}
```

### Overexposed Image
```json
{
  "recommended_enhancements": [
    "BRIGHTNESS: decrease by 20%",
    "HIGHLIGHTS: reduce by 30%",
    "CONTRAST: boost by 15%"
  ]
}
```

### Dull/Flat Image
```json
{
  "recommended_enhancements": [
    "CONTRAST: boost by 30%",
    "VIBRANCE: increase by 35%",
    "CLARITY: boost by 25%"
  ]
}
```

### Soft/Blurry Image
```json
{
  "recommended_enhancements": [
    "SHARPNESS: increase by 50%",
    "UNSHARP_MASK: radius=1.5px, strength=100%, threshold=1",
    "CLARITY: boost by 30%"
  ]
}
```

### Cool/Blue Tinted Image
```json
{
  "recommended_enhancements": [
    "COLOR_TEMPERATURE: warm by 600K",
    "SATURATION: increase by 15%"
  ]
}
```

### Warm/Orange Tinted Image
```json
{
  "recommended_enhancements": [
    "COLOR_TEMPERATURE: cool by 500K",
    "CONTRAST: boost by 20%"
  ]
}
```

---

## Performance Tips

1. **Batch Processing**: Process multiple images in parallel for faster results
2. **Resolution**: Scale down images for preview, then process full resolution
3. **Selective Enhancement**: Apply only necessary adjustments to reduce processing time
4. **Order Matters**: Enhancements are applied in a specific order for best results:
   - Basic adjustments first (brightness, contrast, saturation)
   - Advanced operations after (unsharp mask, color temperature, etc.)

---

## Troubleshooting

### Enhancement Not Applied
- Check if the recommendation format matches supported patterns
- Verify image path and permissions
- Check if output directory exists

### Poor Enhancement Results
- Review the AI analysis recommendations
- Try adjusting parameters manually
- Consider using fewer enhancements at once

### Performance Issues
- Reduce image resolution for testing
- Process images in smaller batches
- Check available disk space for temporary files

---

## File Locations

```
project_root/
├── pictures/               # Your image files
│   ├── Berlijn/           # Example directory
│   └── ...
├── output/                # Analysis and enhancement output
│   ├── *_analysis.json    # AI analysis files
│   ├── enhanced_*.jpg     # Enhanced images
│   ├── report.md          # Generated reports
│   ├── thumbnails/        # Thumbnail gallery
│   └── gallery.md         # Gallery index
├── config.py              # Configuration & ANALYSIS_PROMPT
├── picture_analyzer.py    # Analysis engine
├── picture_enhancer.py    # Enhancement engine
└── cli.py                 # Command-line interface
```

---

## Next Steps

1. Run analysis on your images: `python3 cli.py --batch-analyze pictures/`
2. Review the enhancement recommendations
3. Apply enhancements: `python3 cli.py --batch-enhance pictures/`
4. Compare results and fine-tune if needed
5. Generate gallery: `python3 cli.py --gallery output/`

For more details, see [ENHANCEMENT_SYSTEM.md](ENHANCEMENT_SYSTEM.md)
