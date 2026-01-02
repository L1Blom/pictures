# Slide & Dia Positive Restoration Guide

## Overview

Specialized tools for restoring scanned old slides, dia positives, and vintage film. The system automatically detects aging conditions and applies appropriate restoration profiles.

## Quick Start

### Option 1: Full Workflow (Recommended)
```bash
# Analyze and auto-restore in one command
python cli.py process old_slide.jpg -o output/
python cli.py restore-slide output/old_slide_analyzed.jpg \
  -a output/old_slide_analyzed.json -o output/old_slide_restored.jpg
```

### Option 2: Separate Steps
```bash
# Step 1: Analyze the slide
python cli.py analyze old_slide.jpg -o output/

# Step 2: Auto-detect condition and restore
python cli.py restore-slide output/old_slide_analyzed.jpg \
  -a output/old_slide_analyzed.json
```

### Option 3: Manual Profile Selection
```bash
# Restore with specific profile
python cli.py restore-slide old_slide.jpg -p faded -o restored.jpg
```

## Restoration Profiles

### `faded` - Heavily Aged Slide
**Use when:** Colors are very washed out, low contrast
- **Saturation:** +50% (strong color recovery)
- **Contrast:** +60% (restore depth)
- **Brightness:** +15% (lift shadows)
- **Sharpness:** +20% (enhance details)
- **Color correction:** Warm + blue lift

**Best for:**
- Very old Kodachrome slides
- Heavily faded Fujichrome
- Slides stored in sunlight
- Color negative film from 1970s-80s

### `color_cast` - Color-Cast Slides
**Use when:** Strong magenta, cyan, or yellow color shift
- **Saturation:** +30% (moderate recovery)
- **Contrast:** +40% (enhance depth)
- **Brightness:** +10% (subtle lift)
- **Sharpness:** +15% (enhance clarity)
- **Color correction:** Neutral shift

**Best for:**
- Slides with strong magenta cast
- Cyan-shifted Kodachrome
- Mixed aging indicators

### `aged` - Moderately Aged
**Use when:** Some fading and contrast loss but not severe
- **Saturation:** +25%
- **Contrast:** +30%
- **Brightness:** +8%
- **Sharpness:** +10%
- **Color correction:** Subtle neutral shift

**Best for:**
- Slides stored in cool conditions
- Relatively well-preserved slides
- Kodachrome from 1980s-90s

### `well_preserved` - Minimal Aging
**Use when:** Slide looks nearly original
- **Saturation:** +10% (subtle enhancement)
- **Contrast:** +15% (gentle lift)
- **Brightness:** +5% (minimal adjustment)
- **Sharpness:** +8% (light clarification)
- **Color correction:** Minimal

**Best for:**
- Recently scanned slides
- Professionally stored collections
- Slides in excellent condition

### `auto` - Automatic Detection
**Use when:** Uncertain of condition
- Analyzes image characteristics
- Detects fading, color cast, contrast loss
- Selects optimal profile automatically

```bash
python cli.py restore-slide slide.jpg -p auto -a analysis.json
```

## Restoration Pipeline

Each restoration follows this sequence for optimal results:

1. **Dust/Speckle Removal**
   - Median filter to remove dust artifacts
   - Use `--no-despeckle` to skip

2. **Color Balance Correction**
   - Corrects color casts from aging
   - Balances RGB channels appropriately

3. **Brightness Adjustment**
   - Lifts shadows while preserving highlights
   - Recovers detail in dark areas

4. **Contrast Restoration**
   - Strongest adjustment to restore 3D depth
   - Critical for aged/faded slides

5. **Color Saturation Recovery**
   - Restores vibrant colors
   - Most visual impact for faded slides

6. **Noise/Grain Reduction**
   - Light Gaussian blur (0.5px)
   - Use `--no-denoise` to skip

7. **Sharpness Enhancement**
   - Final detail clarification
   - Compensates for film degradation

## Advanced Usage

### Batch Restore Multiple Slides
```bash
# Analyze all slides
python cli.py batch slide_folder/ -o output/

# Restore with auto-detection
for f in output/*_analyzed.json; do
  img="${f/_analyzed.json/_analyzed.jpg}"
  python cli.py restore-slide "$img" -a "$f" \
    -o "${img/_analyzed/_restored}"
done
```

### Custom Enhancement
```bash
# Analyze
python cli.py analyze old_slide.jpg -o output/

# Restore with auto profile
python cli.py restore-slide output/old_slide_analyzed.jpg \
  -a output/old_slide_analyzed.json

# Further enhance if needed
python cli.py enhance output/old_slide_restored.jpg \
  -a output/old_slide_analyzed.json -o output/old_slide_final.jpg
```

### Skip Specific Restoration Steps
```bash
# Skip dust removal (if slide is clean)
python cli.py restore-slide slide.jpg -p aged --no-despeckle

# Skip noise reduction (to preserve grain as artistic element)
python cli.py restore-slide slide.jpg -p aged --no-denoise

# Skip both
python cli.py restore-slide slide.jpg -p aged --no-despeckle --no-denoise
```

## Understanding Auto-Detection

The system analyzes:
- **Color temperature:** Detects warm/cool/magenta/cyan casts
- **Saturation levels:** Identifies fading by low saturation
- **Contrast quality:** Detects loss of depth
- **Grain/noise:** Identifies film grain and dust artifacts

Confidence levels:
- **85%+:** High confidence in condition assessment
- **70-85%:** Good confidence, reliable profile
- **Below 70%:** Lower confidence, may want manual review

## Tips for Best Results

1. **Scan Quality Matters**
   - Use high-res scans (2400+ DPI for slides)
   - Scan in linear/unprocessed mode if possible
   - Clean physical slide before scanning

2. **Profile Selection**
   - Start with `auto` to get analysis
   - Fine-tune with manual profile if needed
   - Some slides need multiple profiles (original + adjustment)

3. **Preserve Original**
   - Always keep original scan
   - Use different output filenames for iterations
   - Compare results side-by-side

4. **Color Reference**
   - If you remember the original colors, use as reference
   - Test profile on small area first
   - Saturation +50% can be too aggressive sometimes

5. **Film Type Specific**
   - Kodachrome: Often just needs contrast/saturation
   - Fujichrome: May need cyan/blue correction
   - Color negatives: Usually need stronger restoration
   - B&W: Use 'aged' profile, ignore saturation boost

## Output Files

After restoration, you get:
- `slide_restored.jpg` - Final restored image
- `slide_analyzed.jpg` - Image with EXIF metadata
- `slide_analyzed.json` - Complete analysis data

## Troubleshooting

**Result looks too saturated?**
- Try lower profile: `faded` → `aged` → `well_preserved`
- Reduce saturation with `enhance` command

**Colors still have cast?**
- Color cast might be intentional (original slide issue)
- Try `color_cast` profile explicitly

**Too much grain visible?**
- Use default denoise (it's applied automatically)
- Skip with `--no-denoise` if grain is desired

**Loss of detail in dark areas?**
- Try higher saturation profile
- Original scan quality might be limiting factor

## Examples

### Restoring 1950s Kodachrome
```bash
python cli.py process kodachrome_1952.jpg -o output/
python cli.py restore-slide output/kodachrome_1952_analyzed.jpg \
  -a output/kodachrome_1952_analyzed.json -p faded
```

### Well-Preserved Color Negative Scan
```bash
python cli.py restore-slide negative_scan.jpg -p aged
```

### Color Negative with Strong Cast
```bash
python cli.py process negative.jpg -o output/
python cli.py restore-slide output/negative_analyzed.jpg \
  -a output/negative_analyzed.json -p auto
```

