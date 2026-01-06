# Advanced Enhancement System

## Overview

The picture enhancement system now supports detailed, quantifiable enhancement recommendations that are parsed and applied to images using both PIL (Pillow) basic adjustments and advanced image processing techniques.

## Architecture

### 1. Analysis Prompt Enhancement (config.py)

The `ANALYSIS_PROMPT` now requests specific, measurable enhancement recommendations instead of generic suggestions:

**Old Format (Generic):**
```
"increase brightness"
"sharpen the image"
```

**New Format (Detailed & Quantifiable):**
```
"BRIGHTNESS: increase by 25%"
"UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"
"COLOR_TEMPERATURE: warm by 500K"
"SHADOWS: brighten by 15%"
"VIBRANCE: increase by 25%"
"CLARITY: boost by 20%"
```

### 2. Enhanced Recommendation Parsing (_parse_recommendations)

The parser now handles detailed recommendation formats with parameters:

**Supported Recommendation Types:**

| Type | Format | Example |
|------|--------|---------|
| **Brightness** | `BRIGHTNESS: increase/decrease by XX%` | `BRIGHTNESS: increase by 25%` |
| **Contrast** | `CONTRAST: increase/boost by XX%` | `CONTRAST: boost by 20%` |
| **Saturation** | `SATURATION: increase/decrease by XX%` | `SATURATION: increase by 15%` |
| **Sharpness** | `SHARPNESS: increase/boost by XX%` | `SHARPNESS: increase by 30%` |
| **Color Temperature** | `COLOR_TEMPERATURE: warm/cool by XXXK` | `COLOR_TEMPERATURE: warm by 500K` |
| **Unsharp Mask** | `UNSHARP_MASK: radius=X, strength=XX%, threshold=X` | `UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0` |
| **Shadows/Highlights** | `SHADOWS: brighten/darken by XX%` | `SHADOWS: brighten by 15%` |
| **Vibrance** | `VIBRANCE: increase/decrease by XX%` | `VIBRANCE: increase by 25%` |
| **Clarity** | `CLARITY: boost/increase by XX%` | `CLARITY: boost by 20%` |

### 3. Multi-Stage Enhancement Pipeline

The enhancement process works in stages:

```
Original Image
    ↓
[Basic PIL Adjustments]
    - Brightness (affects overall exposure)
    - Contrast (affects perception of lighting)
    - Saturation (affects color vibrancy)
    - Sharpness (PIL sharpness filter)
    ↓
[Advanced Operations] (applied sequentially)
    - Unsharp Mask (local contrast enhancement)
    - Color Temperature (warm/cool adjustment)
    - Shadows/Highlights (selective brightness)
    - Vibrance (selective color saturation)
    - Clarity (mid-tone contrast boost)
    ↓
Enhanced Image
```

## New Methods in picture_enhancer.py

### Basic Methods (via PictureEnhancer class)
- `adjust_brightness()` - ✅ Existing (PIL)
- `adjust_contrast()` - ✅ Existing (PIL)
- `adjust_saturation()` - ✅ Existing (PIL)
- `adjust_sharpness()` - ✅ Existing (PIL)

### Advanced Methods (New)

#### apply_unsharp_mask(image_path, radius=1.5, percent=80, threshold=0, output_path=None)
Applies unsharp mask for local contrast enhancement and sharpening.

**Parameters:**
- `radius` (1.0-3.0): Radius of the unsharp mask
- `percent` (50-150): Strength of the effect as percentage
- `threshold` (0-10): Threshold for edge detection

**Example:**
```python
result = apply_unsharp_mask(
    "image.jpg",
    radius=1.5,
    percent=80,
    threshold=0,
    output_path="enhanced.jpg"
)
```

#### adjust_color_temperature(image_path, kelvin=6500, output_path=None)
Adjusts image color temperature (warm/cool).

**Parameters:**
- `kelvin`: Target color temperature (1500=warm/candle, 6500=neutral/daylight, 10000=cool/sky)

**Example:**
```python
# Warm up by 500K
result = adjust_color_temperature(
    "image.jpg",
    kelvin=7000,
    output_path="warm.jpg"
)
```

#### adjust_shadows_highlights(image_path, shadow_adjust=0, highlight_adjust=0, output_path=None)
Adjust shadow and highlight details separately.

**Parameters:**
- `shadow_adjust` (-100 to +100): Negative = darken, Positive = brighten shadows
- `highlight_adjust` (-100 to +100): Negative = darken, Positive = brighten highlights

**Example:**
```python
result = adjust_shadows_highlights(
    "image.jpg",
    shadow_adjust=15,
    highlight_adjust=-10,
    output_path="adjusted.jpg"
)
```

#### apply_clarity_filter(image_path, strength=20, output_path=None)
Apply clarity filter for mid-tone contrast enhancement.

**Parameters:**
- `strength` (0-100): Clarity strength (typically 20-40)

**Example:**
```python
result = apply_clarity_filter(
    "image.jpg",
    strength=20,
    output_path="clear.jpg"
)
```

#### adjust_vibrance(image_path, factor=1.0, output_path=None)
Adjust vibrance (selective saturation boost of less saturated colors).

**Parameters:**
- `factor` (0.5-2.0): 1.0 = original, <1.0 = less vibrant, >1.0 = more vibrant

**Example:**
```python
result = adjust_vibrance(
    "image.jpg",
    factor=1.25,  # 25% more vibrant
    output_path="vibrant.jpg"
)
```

## SmartEnhancer Class

The `SmartEnhancer` class orchestrates the entire enhancement pipeline:

### Methods

#### enhance_from_analysis(image_path, enhancement_data, output_path=None)
Main method that applies AI-recommended enhancements.

**Example:**
```python
enhancer = SmartEnhancer()
enhancement_data = {
    "recommended_enhancements": [
        "BRIGHTNESS: increase by 25%",
        "CONTRAST: boost by 20%",
        "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"
    ]
}
result = enhancer.enhance_from_analysis(
    "original.jpg",
    enhancement_data,
    output_path="enhanced.jpg"
)
```

## Workflow Example

### 1. Analysis Phase (picture_analyzer.py)
```python
from picture_analyzer import PictureAnalyzer

analyzer = PictureAnalyzer()
analysis = analyzer.analyze_image("image.jpg")
# Returns: {metadata, enhancement, slide_profiles}
```

The AI analysis now includes detailed recommendations like:
```json
{
  "enhancement": {
    "lighting_quality": "Slightly underexposed with shadow crushing",
    "color_analysis": "Neutral white balance with cool tones",
    "sharpness_clarity": "Generally sharp, good detail",
    "recommended_enhancements": [
      "BRIGHTNESS: increase by 25%",
      "CONTRAST: boost by 20%",
      "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0",
      "SHADOWS: brighten by 15%",
      "VIBRANCE: increase by 25%",
      "CLARITY: boost by 20%"
    ],
    "overall_priority": "Fix brightness first, then add contrast"
  }
}
```

### 2. Enhancement Phase (picture_enhancer.py)
```python
from picture_enhancer import SmartEnhancer

enhancer = SmartEnhancer()
enhanced_path = enhancer.enhance_from_analysis(
    "image.jpg",
    analysis['enhancement'],
    output_path="enhanced.jpg"
)
```

The enhancer will:
1. Parse detailed recommendations
2. Apply basic adjustments (brightness, contrast, saturation)
3. Apply advanced operations in sequence (unsharp mask, color temperature, etc.)
4. Save the final enhanced image

## Key Improvements

### 1. Quantifiable Recommendations
- AI provides specific percentages instead of generic descriptions
- Directly correlates with parameter values in enhancement methods
- Easier to validate and reproduce results

### 2. Advanced Technique Support
- Unsharp mask with specific radius, strength, and threshold
- Color temperature in Kelvin units
- Separate shadow/highlight adjustments
- Vibrance and clarity enhancements

### 3. Robust Parsing
- Flexible regex patterns handle variations in recommendation format
- Supports multiple recommendation formats
- Falls back gracefully if parsing fails

### 4. Extensible Architecture
- Easy to add new enhancement methods
- Plugin-style approach for advanced operations
- Maintains backward compatibility with basic PIL adjustments

## Testing

Test the recommendation parser:
```bash
cd /home/leen/projects/pictures
python3 << 'EOF'
from picture_enhancer import SmartEnhancer

enhancer = SmartEnhancer()
recommendations = [
    "BRIGHTNESS: increase by 25%",
    "CONTRAST: boost by 20%",
    "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"
]
result = enhancer._parse_recommendations(recommendations, {})
print(result)
EOF
```

Test full enhancement pipeline:
```bash
python3 << 'EOF'
from picture_enhancer import SmartEnhancer

enhancer = SmartEnhancer()
enhancement_data = {
    "recommended_enhancements": [
        "BRIGHTNESS: increase by 15%",
        "CONTRAST: boost by 20%",
        "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"
    ]
}
result = enhancer.enhance_from_analysis(
    "image.jpg",
    enhancement_data,
    output_path="enhanced.jpg"
)
print(f"Enhanced: {result}")
EOF
```

## Performance Considerations

- **Basic adjustments** (brightness, contrast): Very fast (< 100ms)
- **Unsharp mask**: Fast (200-500ms depending on image size)
- **Color temperature**: Moderate (500-1000ms - pixel-by-pixel operation)
- **Shadows/highlights**: Moderate (500-1000ms - per-pixel luminance calculation)
- **Vibrance**: Moderate (700-1500ms - HSV conversion required)
- **Clarity**: Fast (200-500ms - uses unsharp mask internally)

For batch processing of 1000+ images, consider:
- Processing in parallel batches
- Caching intermediate results
- Using lower resolution for preview

## Future Enhancements

Planned methods for expansion:
- `reduce_noise()` - Advanced noise reduction using bilateral filtering
- `correct_vignetting()` - Lens vignette correction
- `auto_white_balance()` - Automatic color correction
- `enhance_details()` - Detail enhancement using edge detection
- `remove_distortion()` - Lens distortion correction

## Files Modified

1. **config.py**
   - Enhanced `ANALYSIS_PROMPT` with 19 detailed sections
   - Quantifiable recommendations with specific parameters
   - Examples of detailed AI recommendations

2. **picture_enhancer.py**
   - New advanced enhancement methods
   - Updated `_parse_recommendations()` for detailed formats
   - Updated `_apply_adjustments()` for multi-stage pipeline
   - Support for sequential advanced operations

3. No changes to other files (backward compatible)

## Compatibility

- ✅ Backward compatible with existing code
- ✅ Works with existing analysis JSON format
- ✅ Supports both new and old recommendation formats
- ✅ Graceful fallback if advanced methods unavailable
