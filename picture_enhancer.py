"""
Picture enhancement utilities with AI-guided recommendations

This module provides:
- Smart enhancement based on AI analysis recommendations
- Color correction
- Brightness/contrast adjustment
- Saturation adjustment
- And more...

For advanced filters (unsharp mask, color temperature, etc.), see enhancement_filters module.
"""
from PIL import Image, ImageEnhance, ImageFilter
from typing import Optional, Tuple, List, Dict, Any
import os
import json
import re
from pathlib import Path
from enhancement_filters import (
    apply_unsharp_mask,
    adjust_color_temperature,
    adjust_shadows_highlights,
    apply_clarity_filter,
    adjust_vibrance,
    adjust_color_channel
)


class PictureEnhancer:
    """Handles picture enhancement operations"""
    
    # Map of property types to PIL ImageEnhance classes
    _ENHANCER_MAP = {
        'brightness': ImageEnhance.Brightness,
        'contrast': ImageEnhance.Contrast,
        'saturation': ImageEnhance.Color,
        'sharpness': ImageEnhance.Sharpness,
    }
    
    @staticmethod
    def adjust_property(
        image_path: str,
        property_type: str,
        factor: float = 1.0,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Generic method to adjust image properties
        
        Args:
            image_path: Path to source image
            property_type: Type of property ('brightness', 'contrast', 'saturation', 'sharpness')
            factor: Adjustment factor (1.0 = original, <1.0 = decrease, >1.0 = increase)
            output_path: Path to save enhanced image
            
        Returns:
            Path to saved image or None if failed
        """
        try:
            if property_type not in PictureEnhancer._ENHANCER_MAP:
                raise ValueError(f"Unknown property type: {property_type}. Must be one of: {list(PictureEnhancer._ENHANCER_MAP.keys())}")
            
            image = Image.open(image_path)
            enhancer_class = PictureEnhancer._ENHANCER_MAP[property_type]
            enhancer = enhancer_class(image)
            enhanced = enhancer.enhance(factor)
            
            if output_path:
                enhanced.save(output_path, quality=95)
                return output_path
            return None
        except Exception as e:
            print(f"Error adjusting {property_type}: {e}")
            return None
    
    @staticmethod
    def adjust_brightness(
        image_path: str,
        factor: float = 1.0,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Adjust image brightness
        
        Args:
            image_path: Path to source image
            factor: Brightness factor (1.0 = original, <1.0 = darker, >1.0 = brighter)
            output_path: Path to save enhanced image
            
        Returns:
            Path to saved image or None if failed
        """
        return PictureEnhancer.adjust_property(image_path, 'brightness', factor, output_path)
    
    @staticmethod
    def adjust_contrast(
        image_path: str,
        factor: float = 1.0,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Adjust image contrast
        
        Args:
            image_path: Path to source image
            factor: Contrast factor (1.0 = original, <1.0 = less contrast, >1.0 = more contrast)
            output_path: Path to save enhanced image
            
        Returns:
            Path to saved image or None if failed
        """
        return PictureEnhancer.adjust_property(image_path, 'contrast', factor, output_path)
    
    @staticmethod
    def adjust_saturation(
        image_path: str,
        factor: float = 1.0,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Adjust image color saturation
        
        Args:
            image_path: Path to source image
            factor: Saturation factor (0 = grayscale, 1.0 = original, >1.0 = more vibrant)
            output_path: Path to save enhanced image
            
        Returns:
            Path to saved image or None if failed
        """
        return PictureEnhancer.adjust_property(image_path, 'saturation', factor, output_path)
    
    @staticmethod
    def adjust_sharpness(
        image_path: str,
        factor: float = 1.0,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Adjust image sharpness
        
        Args:
            image_path: Path to source image
            factor: Sharpness factor (0 = blur, 1.0 = original, >1.0 = sharper)
            output_path: Path to save enhanced image
            
        Returns:
            Path to saved image or None if failed
        """
        return PictureEnhancer.adjust_property(image_path, 'sharpness', factor, output_path)
    
    @staticmethod
    def resize_image(
        image_path: str,
        size: Tuple[int, int],
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Resize an image
        
        Args:
            image_path: Path to source image
            size: Target size as (width, height)
            output_path: Path to save resized image
            
        Returns:
            Path to saved image or None if failed
        """
        try:
            image = Image.open(image_path)
            resized = image.resize(size, Image.Resampling.LANCZOS)
            
            if output_path:
                resized.save(output_path)
                return output_path
            return None
        except Exception as e:
            print(f"Error resizing image: {e}")
            return None
    
    @staticmethod
    def convert_to_grayscale(
        image_path: str,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Convert image to grayscale
        
        Args:
            image_path: Path to source image
            output_path: Path to save grayscale image
            
        Returns:
            Path to saved image or None if failed
        """
        try:
            image = Image.open(image_path)
            grayscale = image.convert('L')
            
            if output_path:
                grayscale.save(output_path)
                return output_path
            return None
        except Exception as e:
            print(f"Error converting to grayscale: {e}")
            return None
    
    @staticmethod
    def apply_filter(
        image_path: str,
        filter_type: str = 'blur',
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Apply various filters to the image
        
        Args:
            image_path: Path to source image
            filter_type: Type of filter ('blur', 'sharpen', 'smooth', etc.)
            output_path: Path to save filtered image
            
        Returns:
            Path to saved image or None if failed
        """
        try:
            image = Image.open(image_path)
            
            filters = {
                'blur': ImageFilter.GaussianBlur(radius=2),
                'sharpen': ImageFilter.SHARPEN,
                'smooth': ImageFilter.SMOOTH,
                'detail': ImageFilter.DETAIL,
                'edge_enhance': ImageFilter.EDGE_ENHANCE,
            }
            
            if filter_type not in filters:
                raise ValueError(f"Unknown filter type: {filter_type}")
            
            filtered = image.filter(filters[filter_type])
            
            if output_path:
                filtered.save(output_path)
                return output_path
            return None
        except Exception as e:
            print(f"Error applying filter: {e}")
            return None


class SmartEnhancer:
    """Intelligent image enhancer that parses AI recommendations and applies enhancements"""
    
    # ── Deterministic safety gates (audit-driven, see audit_output/) ──
    # Cast-gate: if the original image's measured color cast is below this
    # threshold, color-correction recommendations are dropped. The audit
    # showed the analyzer frequently "corrects" casts that are not there,
    # CREATING a cast on neutral images.
    CAST_GATE_THRESHOLD = 0.03   # |R - avg(G,B)| / 255, measured on a thumbnail
    # Highlight-gate: brightness INCREASES are dropped when the original is
    # already bright or already has clipped highlights. The v4 audit found
    # 29/50 images blowing highlights (up to 0% → 57% clipping) because the
    # analyzer recommends brightness lifts on already-bright images.
    BRIGHT_IMAGE_LUMA = 0.45      # mean luminance above this = bright image
    HIGH_CLIP_PCT = 3.0          # original highlight clipping above this = at risk
    # Saturation-gate: vibrance/saturation INCREASES are dropped when the
    # original is already colorful. The v4 audit found images going from
    # 0.62 → 0.82 saturation (cartoonish).
    SATURATED_ORIG = 0.55        # mean saturation above this = already colorful
    # Sharpness-gate: sharpening is capped when the original is already sharp
    # or when the analyzer stacks SHARPNESS + UNSHARP_MASK (compounding).
    # The v5 audit found a median +54% Laplacian-variance increase with p75
    # at +104% — visible halos. PIL Sharpness factor cap and unsharp-mask
    # strength cap keep the total sharpening in a natural range.
    # Threshold calibrated to the sample's p75 lap_var (~1900): only genuinely
    # sharp originals (top quartile) skip sharpening entirely.
    SHARP_ORIG_LAP_VAR = 1900.0   # original Laplacian variance above this = already sharp
    MAX_SHARPNESS_FACTOR = 1.15  # cap for PIL Sharpness (was up to 1.40)
    MAX_UNSHARP_PERCENT = 60.0   # cap for unsharp-mask strength (was up to 80-100)
    # Combined-exposure cap: the v6 audit showed two overbrightening patterns:
    # (a) bright originals blow highlights from CONTRAST alone (up to +40%
    #     clipping with brightness already gated), and
    # (b) dark originals blow from the STACKED ops (brightness + contrast +
    #     shadow brightening compounding, e.g. 1.25 × 1.30 + 20% shadows).
    # Rules: bright originals get a tight contrast cap; every image gets an
    # ADAPTIVE total exposure budget — dark originals get more headroom
    # (they need strong lifts for the vivid family-album goal), bright ones
    # less. Trim order: shadows → brightness → contrast.
    # (v7's flat 0.35 budget overcorrected: vibrancy dropped 6.30→5.78 and
    # the dull original started winning again — see audit v7 vs v6.)
    BRIGHT_CONTRAST_CAP = 1.05   # contrast cap for bright originals (luma ≥ 0.45)
    EXPOSURE_BUDGET_BASE = 0.35  # budget for a fully bright image (luma = 1.0)
    EXPOSURE_BUDGET_DARK_BONUS = 0.40  # extra headroom for a fully dark image
    # effective budget = BASE + DARK_BONUS × (1 − luma)
    #   luma 0.20 (dark slide)  → ~0.67
    #   luma 0.45 (mid)         → ~0.57
    #   luma 0.70 (bright)      → ~0.47
    
    def __init__(self):
        """Initialize smart enhancer"""
        self.enhancer = PictureEnhancer()
    
    @staticmethod
    def _measure_image_stats(image_path: str) -> dict:
        """Measure objective stats of an image on a small thumbnail.
        
        Returns a dict with:
          cast: |R - avg(G,B)| / 255  (0 = neutral, higher = red/blue bias)
          luma: mean luminance in [0, 1]
          highlight_clip_pct: % of pixels at/above 250 luminance
          saturation: mean HSV-style saturation in [0, 1]
          lap_var: Laplacian variance (sharpness; higher = sharper)
        Values are -1.0 when measurement fails (gates then stay open).
        """
        fallback = {"cast": -1.0, "luma": -1.0, "highlight_clip_pct": -1.0,
                    "saturation": -1.0, "lap_var": -1.0}
        try:
            from PIL import Image
            img = Image.open(image_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.thumbnail((256, 256))
            try:
                import numpy as np
                arr = np.asarray(img, dtype='float32')
                r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                mx = arr.max(axis=2)
                mn = arr.min(axis=2)
                sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
                # Laplacian variance (sharpness) on luminance
                lap = (
                    -4 * lum
                    + np.roll(lum, 1, 0) + np.roll(lum, -1, 0)
                    + np.roll(lum, 1, 1) + np.roll(lum, -1, 1)
                )
                return {
                    "cast": float(abs(r.mean() - (g.mean() + b.mean()) / 2.0) / 255.0),
                    "luma": float(lum.mean() / 255.0),
                    "highlight_clip_pct": float((lum >= 250).mean() * 100),
                    "saturation": float(sat.mean()),
                    "lap_var": float(lap.var()),
                }
            except ImportError:
                data = list(img.getdata())
                n = len(data)
                rs = [p[0] for p in data]; gs = [p[1] for p in data]; bs = [p[2] for p in data]
                r, g, b = sum(rs) / n, sum(gs) / n, sum(bs) / n
                lums = [0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in data]
                mean_lum = sum(lums) / n
                sats = [(max(p) - min(p)) / max(p) if max(p) > 0 else 0.0 for p in data]
                # Laplacian variance without numpy: sample a grid of pixels
                w, h = img.size
                lap_vals = []
                for y in range(1, h - 1, 4):
                    for x in range(1, w - 1, 4):
                        c = lums[y * w + x]
                        lap_vals.append(
                            -4 * c
                            + lums[(y-1) * w + x] + lums[(y+1) * w + x]
                            + lums[y * w + x - 1] + lums[y * w + x + 1]
                        )
                mean_lap = sum(lap_vals) / len(lap_vals) if lap_vals else 0.0
                lap_var = (sum((v - mean_lap) ** 2 for v in lap_vals) / len(lap_vals)
                           if lap_vals else 0.0)
                return {
                    "cast": abs(r - (g + b) / 2.0) / 255.0,
                    "luma": mean_lum / 255.0,
                    "highlight_clip_pct": sum(1 for l in lums if l >= 250) / n * 100,
                    "saturation": sum(sats) / n,
                    "lap_var": lap_var,
                }
        except Exception as e:
            print(f"  ⚠ Could not measure image stats ({e}) — safety gates disabled for this image")
            return fallback
    
    @staticmethod
    def _measure_color_cast(image_path: str) -> float:
        """Measure the color cast of an image as |R - avg(G,B)| / 255.
        
        Convenience wrapper around _measure_image_stats.
        """
        return SmartEnhancer._measure_image_stats(image_path)["cast"]
    
    
    def enhance_from_analysis(
        self,
        image_path: str,
        enhancement_data: Dict[str, Any],
        output_path: Optional[str] = None,
        analysis_data: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Enhance image based on AI analysis recommendations
        
        IMPORTANT: This applies ONLY AI enhancements from the analysis.
        For independent profile restoration, use SlideRestoration.restore_slide() separately.
        
        Args:
            image_path: Path to source image
            enhancement_data: Enhancement section from AI analysis
            output_path: Path to save enhanced image
            analysis_data: Full analysis data (optional, not used for profile application)
            
        Returns:
            Path to saved image or None if failed
        """
        try:
            # Validate enhancement_data is a dict
            if not isinstance(enhancement_data, dict):
                print(f"No valid enhancement data provided (got {type(enhancement_data).__name__})")
                return None
            
            # Start with the original image
            current_image_path = image_path
            
            # Extract recommendations
            recommendations = enhancement_data.get('recommended_enhancements', [])
            
            # Ensure recommendations is a list
            if isinstance(recommendations, str):
                # If it's a string, split by newlines or common delimiters
                recommendations = [r.strip() for r in recommendations.split('\n') if r.strip()]
            elif isinstance(recommendations, dict):
                # If it's a single dict, wrap it in a list
                recommendations = [recommendations]
            elif not isinstance(recommendations, list):
                # Convert any other iterable to list, otherwise empty list
                try:
                    recommendations = list(recommendations) if recommendations else []
                except TypeError:
                    recommendations = []
            
            if not recommendations:
                print("No enhancement recommendations found")
                return None
            
            # Parse and apply each recommendation
            adjustments = self._parse_recommendations(
                recommendations, enhancement_data, image_path=image_path
            )
            
            # Apply adjustments in optimal order
            current_image_path = self._apply_adjustments(
                current_image_path,
                adjustments,
                output_path
            )
            
            # NOTE: Profile restoration is now applied independently by CLI
            # This ensures both AI enhancement and profile restoration
            # start from the source image, not from each other
            
            return current_image_path
        
        except Exception as e:
            print(f"Error during smart enhancement: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def enhance_from_json(
        self,
        image_path: str,
        json_analysis_path: str,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Enhance image using analysis from JSON file
        
        Args:
            image_path: Path to source image
            json_analysis_path: Path to JSON analysis file
            output_path: Path to save enhanced image
            
        Returns:
            Path to saved image or None if failed
        """
        try:
            with open(json_analysis_path, 'r') as f:
                analysis = json.load(f)
            
            if 'enhancement' not in analysis:
                print("No enhancement data found in analysis file")
                return None
            
            return self.enhance_from_analysis(
                image_path,
                analysis['enhancement'],
                output_path,
                analysis_data=analysis  # Pass full analysis for AI-profile matching
            )
        except Exception as e:
            print(f"Error reading analysis file: {e}")
            return None
    
    def _parse_recommendations(
        self,
        recommendations: List[str],
        enhancement_data: Dict[str, Any],
        image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parse AI recommendations and extract adjustment factors
        
        Supports detailed recommendations like:
        - "BRIGHTNESS: increase by 25%"
        - "COLOR_TEMPERATURE: warm by 500K"
        - "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"
        - "SHADOWS: brighten by 15%"
        - "VIBRANCE: increase by 25%"
        - "CLARITY: boost by 20%"
        
        Args:
            recommendations: List of recommendation strings
            enhancement_data: Full enhancement data for context
            
        Returns:
            Dictionary of adjustments and advanced enhancement operations
        """
        adjustments = {}
        advanced_ops = []  # Track advanced operations to apply
        skipped_count = 0
        
        if not recommendations:
            return {'adjustments': adjustments, 'advanced_ops': advanced_ops}

        # Deduplicate and cap recommendations to prevent model runaway loops
        seen = set()
        capped = []
        for r in recommendations:
            key = str(r).strip()[:80]  # normalise for dedup
            if key not in seen:
                seen.add(key)
                capped.append(r)
            if len(capped) >= 15:  # hard cap — more than 15 is always a model loop
                break
        recommendations = capped

        for recommendation in recommendations:
            # Handle cases where recommendation might be a dict instead of string
            if isinstance(recommendation, dict):
                # If it's a dict, try to extract the text from various possible keys
                if 'action' in recommendation:
                    rec = recommendation['action']
                elif 'text' in recommendation:
                    rec = recommendation['text']
                elif 'description' in recommendation:
                    rec = recommendation['description']
                elif 'recommendation' in recommendation:
                    rec = recommendation['recommendation']
                else:
                    # Try to find any string value in the dict
                    for key, value in recommendation.items():
                        if isinstance(value, str):
                            rec = value
                            break
                    else:
                        # If no string found, convert dict to string representation
                        rec = str(recommendation)
            elif not isinstance(recommendation, str):
                # Skip non-string, non-dict items
                print(f"  ⚠ Skipping invalid recommendation format: {type(recommendation)}")
                skipped_count += 1
                continue
            else:
                rec = recommendation
                
            rec = rec.strip()
            
            # Skip empty recommendations or those with no parameters
            if not rec or rec.lower() in ['no enhancements needed', 'no_enhancements: maintain current quality', 'none needed', 'maintain', 'normalize']:
                continue
            
            # Check if recommendation has no numeric values (likely unparseable)
            if not re.search(r'\d+', rec):
                print(f"  ⚠ Skipping non-numeric recommendation: {rec}")
                skipped_count += 1
                continue
            
            rec_lower = rec.lower()
            
            # Track if this recommendation was successfully parsed
            parsed = False
            
            # ===== BRIGHTNESS =====
            if 'brightness' in rec_lower:
                match = re.search(r'(?:increase|decrease|by).*?([+-]?\d+)\s*%', rec_lower)
                if match:
                    percent = int(match.group(1))
                    factor = 1.0 + (percent / 100.0)
                    adjustments['brightness'] = factor
                    print(f"  → Brightness: {percent:+d}% (factor: {factor:.2f})")
            
            # ===== CONTRAST =====
            elif 'contrast' in rec_lower:
                match = re.search(r'(?:increase|boost|by).*?([+-]?\d+)\s*%', rec_lower)
                if match:
                    percent = int(match.group(1))
                    factor = 1.0 + (percent / 100.0)
                    adjustments['contrast'] = factor
                    print(f"  → Contrast: {percent:+d}% (factor: {factor:.2f})")
            
            # ===== COLOR TEMPERATURE =====
            elif 'color_temperature' in rec_lower or 'temperature' in rec_lower:
                match = re.search(r'([+-]?\d+)\s*k(?:elvin)?', rec_lower)
                if match:
                    kelvin_shift = int(match.group(1))
                    
                    # Check if recommendation says "cool" or "warm" to get the direction right
                    if 'cool' in rec_lower:
                        # Cool = bluer = lower kelvin = negative shift
                        kelvin_shift = -abs(kelvin_shift)
                    elif 'warm' in rec_lower:
                        # Warm = redder = higher kelvin = positive shift
                        kelvin_shift = abs(kelvin_shift)
                    
                    # Convert shift to absolute kelvin (assuming 6500K baseline)
                    target_kelvin = 6500 + kelvin_shift
                    # Clamp to valid range
                    target_kelvin = max(1500, min(15000, target_kelvin))
                    
                    advanced_ops.append({
                        'type': 'color_temperature',
                        'kelvin': target_kelvin
                    })
                    print(f"  → Color Temperature: {target_kelvin}K ({kelvin_shift:+d}K shift)")
            
            # ===== COLOR CHANNEL ADJUSTMENTS =====
            elif 'red_channel' in rec_lower or 'blue_channel' in rec_lower or 'green_channel' in rec_lower:
                # Determine which channel — match on *_channel keyword, not bare
                # substring, because "reduce" contains "red" and would misclassify
                # BLUE_CHANNEL: reduce as RED_CHANNEL.
                channel = None
                if 'red_channel' in rec_lower:
                    channel = 'red'
                elif 'blue_channel' in rec_lower:
                    channel = 'blue'
                elif 'green_channel' in rec_lower:
                    channel = 'green'
                
                # Extract percentage and direction
                percent_match = re.search(r'([+-]?\d+)\s*%', rec_lower)
                if percent_match and channel:
                    percent = int(percent_match.group(1))
                    # Check if "reduce" or "decrease" keywords present (negate the percentage)
                    if 'reduce' in rec_lower or 'decrease' in rec_lower:
                        percent = -percent
                    factor = 1.0 + (percent / 100.0)
                    factor = max(0.1, min(2.5, factor))  # Clamp to reasonable range
                    
                    advanced_ops.append({
                        'type': 'channel',
                        'channel': channel,
                        'factor': factor
                    })
                    print(f"  → {channel.capitalize()} Channel: {percent:+d}% (factor: {factor:.2f})")
            
            # ===== UNSHARP MASK =====
            elif 'unsharp_mask' in rec_lower or 'unsharp mask' in rec_lower:
                radius = 1.5
                percent = 80
                threshold = 0
                
                radius_match = re.search(r'radius\s*=\s*([\d.]+)', rec_lower)
                if radius_match:
                    radius = float(radius_match.group(1))
                
                percent_match = re.search(r'strength\s*=\s*([\d.]+)', rec_lower)
                if percent_match:
                    percent = int(float(percent_match.group(1)))
                elif re.search(r'(\d+)\s*%', rec_lower):
                    percent_match = re.search(r'(\d+)\s*%', rec_lower)
                    percent = int(percent_match.group(1))
                
                threshold_match = re.search(r'threshold\s*=\s*(\d+)', rec_lower)
                if threshold_match:
                    threshold = int(threshold_match.group(1))
                
                advanced_ops.append({
                    'type': 'unsharp_mask',
                    'radius': radius,
                    'percent': percent,
                    'threshold': threshold
                })
                print(f"  → Unsharp Mask: radius={radius}, strength={percent}%, threshold={threshold}")
            
            # ===== SHADOWS/HIGHLIGHTS =====
            elif 'shadow' in rec_lower or 'highlight' in rec_lower:
                shadow_adjust = 0
                highlight_adjust = 0
                
                if 'shadow' in rec_lower:
                    shadow_match = re.search(r'(?:brighten|darken).*?([+-]?\d+)\s*%', rec_lower)
                    if shadow_match:
                        shadow_adjust = int(shadow_match.group(1))
                
                if 'highlight' in rec_lower:
                    highlight_match = re.search(r'(?:brighten|darken).*?([+-]?\d+)\s*%', rec_lower)
                    if highlight_match:
                        highlight_adjust = int(highlight_match.group(1))
                
                if shadow_adjust != 0 or highlight_adjust != 0:
                    advanced_ops.append({
                        'type': 'shadows_highlights',
                        'shadow_adjust': shadow_adjust,
                        'highlight_adjust': highlight_adjust
                    })
                    print(f"  → Shadows/Highlights: shadows {shadow_adjust:+d}%, highlights {highlight_adjust:+d}%")
            
            # ===== VIBRANCE =====
            elif 'vibrance' in rec_lower:
                match = re.search(r'(?:increase|boost|by).*?([+-]?\d+)\s*%', rec_lower)
                if match:
                    percent = int(match.group(1))
                    factor = 1.0 + (percent / 100.0)
                    advanced_ops.append({
                        'type': 'vibrance',
                        'factor': factor
                    })
                    print(f"  → Vibrance: {percent:+d}% (factor: {factor:.2f})")
            
            # ===== CLARITY =====
            elif 'clarity' in rec_lower:
                match = re.search(r'(?:boost|increase|by).*?([+-]?\d+)\s*%', rec_lower)
                if match:
                    percent = int(match.group(1))
                    strength = percent / 100.0
                    advanced_ops.append({
                        'type': 'clarity',
                        'strength': strength
                    })
                    print(f"  → Clarity: {percent:+d}%")
            
            # ===== SATURATION =====
            elif 'saturation' in rec_lower or 'saturate' in rec_lower:
                match = re.search(r'(?:increase|boost|by).*?([+-]?\d+)\s*%', rec_lower)
                if match:
                    percent = int(match.group(1))
                    factor = 1.0 + (percent / 100.0)
                    adjustments['saturation'] = factor
                    print(f"  → Saturation: {percent:+d}% (factor: {factor:.2f})")
            
            # ===== SHARPNESS =====
            elif 'sharpness' in rec_lower or 'sharpen' in rec_lower:
                match = re.search(r'(?:increase|boost|enhance|by).*?([+-]?\d+)\s*%', rec_lower)
                if match:
                    percent = int(match.group(1))
                    factor = 1.0 + (percent / 100.0)
                    adjustments['sharpness'] = factor
                    print(f"  → Sharpness: {percent:+d}% (factor: {factor:.2f})")
        
        # Return both basic and advanced adjustments
        # Deduplicate channel ops — models sometimes emit conflicting operations
        # for the same channel (e.g. RED_CHANNEL: +20% and RED_CHANNEL: -15%).
        # Keep the FIRST occurrence: the template lists recommendations in
        # priority order, so the first is the intended one.
        seen_channels: set[str] = set()
        deduped_ops: list = []
        for op in advanced_ops:
            ch = op.get('channel') if isinstance(op, dict) else None
            if ch is not None:
                if ch in seen_channels:
                    continue
                seen_channels.add(ch)
            deduped_ops.append(op)
        advanced_ops = deduped_ops

        # ── SAFETY GATES (deterministic, audit-driven) ────────────────
        # Measure the original once; gates stay open on measurement failure.
        if image_path and (advanced_ops or adjustments):
            stats = self._measure_image_stats(image_path)

            # Cast-gate: neutral originals get no color corrections
            if 0.0 <= stats["cast"] < self.CAST_GATE_THRESHOLD and any(
                isinstance(op, dict) and op.get('type') in ('color_temperature', 'channel')
                for op in advanced_ops
            ):
                dropped = [
                    op for op in advanced_ops
                    if isinstance(op, dict) and op.get('type') in ('color_temperature', 'channel')
                ]
                advanced_ops = [
                    op for op in advanced_ops
                    if not (isinstance(op, dict) and op.get('type') in ('color_temperature', 'channel'))
                ]
                print(f"  ⚠ Cast-gate: original is color-neutral (cast={stats['cast']:.4f} < "
                      f"{self.CAST_GATE_THRESHOLD}) — dropping {len(dropped)} color-correction "
                      f"op(s) that would have introduced a cast")

            # Highlight-gate: no brightness increases on bright/clipped originals
            at_risk = (
                (stats["luma"] >= self.BRIGHT_IMAGE_LUMA)
                or (stats["highlight_clip_pct"] >= self.HIGH_CLIP_PCT)
            )
            if at_risk:
                if adjustments.get('brightness', 1.0) > 1.0:
                    print(f"  ⚠ Highlight-gate: original is bright (luma={stats['luma']:.2f}, "
                          f"hi_clip={stats['highlight_clip_pct']:.1f}%) — dropping brightness "
                          f"increase {adjustments['brightness']:.2f}x that would blow highlights")
                    del adjustments['brightness']
                # Shadow brightening also pushes pixels toward clipping
                kept_ops = []
                for op in advanced_ops:
                    if (isinstance(op, dict) and op.get('type') == 'shadows_highlights'
                            and op.get('shadow_adjust', 0) > 0):
                        print(f"  ⚠ Highlight-gate: dropping shadow brightening "
                              f"(+{op['shadow_adjust']}%) on bright/clipped original")
                        continue
                    kept_ops.append(op)
                advanced_ops = kept_ops

            # Saturation-gate: no vibrance/saturation increases on colorful originals
            if stats["saturation"] >= self.SATURATED_ORIG:
                if adjustments.get('saturation', 1.0) > 1.0:
                    print(f"  ⚠ Saturation-gate: original is already colorful "
                          f"(sat={stats['saturation']:.2f}) — dropping saturation increase")
                    del adjustments['saturation']
                kept_ops = []
                for op in advanced_ops:
                    if (isinstance(op, dict) and op.get('type') == 'vibrance'
                            and op.get('factor', 1.0) > 1.0):
                        print(f"  ⚠ Saturation-gate: dropping vibrance boost "
                              f"({op['factor']:.2f}x) on already-colorful original")
                        continue
                    kept_ops.append(op)
                advanced_ops = kept_ops

            # Sharpness-gate: cap total sharpening (halo prevention)
            # a) Already-sharp originals get no additional sharpening at all
            if stats.get("lap_var", 0.0) >= self.SHARP_ORIG_LAP_VAR:
                if adjustments.get('sharpness', 1.0) > 1.0:
                    print(f"  ⚠ Sharpness-gate: original is already sharp "
                          f"(lap_var={stats['lap_var']:.0f}) — dropping sharpness increase")
                    del adjustments['sharpness']
                kept_ops = []
                for op in advanced_ops:
                    if isinstance(op, dict) and op.get('type') == 'unsharp_mask':
                        print(f"  ⚠ Sharpness-gate: dropping unsharp mask on already-sharp original")
                        continue
                    kept_ops.append(op)
                advanced_ops = kept_ops
            else:
                # b) Not already sharp: cap the PIL Sharpness factor
                if adjustments.get('sharpness', 1.0) > self.MAX_SHARPNESS_FACTOR:
                    print(f"  ⚠ Sharpness-gate: capping sharpness "
                          f"{adjustments['sharpness']:.2f}x → {self.MAX_SHARPNESS_FACTOR}x")
                    adjustments['sharpness'] = self.MAX_SHARPNESS_FACTOR
                # c) Cap unsharp-mask strength; and if BOTH SHARPNESS and
                #    UNSHARP_MASK are recommended, drop the unsharp mask
                #    entirely (compounding sharpening = halos)
                has_sharpness = adjustments.get('sharpness', 1.0) > 1.0
                kept_ops = []
                for op in advanced_ops:
                    if isinstance(op, dict) and op.get('type') == 'unsharp_mask':
                        if has_sharpness:
                            print(f"  ⚠ Sharpness-gate: dropping unsharp mask "
                                  f"(compounds with SHARPNESS increase — halo risk)")
                            continue
                        if op.get('percent', 0) > self.MAX_UNSHARP_PERCENT:
                            print(f"  ⚠ Sharpness-gate: capping unsharp strength "
                                  f"{op['percent']:.0f}% → {self.MAX_UNSHARP_PERCENT:.0f}%")
                            op['percent'] = self.MAX_UNSHARP_PERCENT
                    kept_ops.append(op)
                advanced_ops = kept_ops

            # Combined-exposure cap: limit the TOTAL brightening effect of
            # stacked ops (brightness × contrast × shadow brightening).
            # Trim order: shadow brightening first, then brightness, then contrast.
            if stats["luma"] >= 0.0:  # measurement succeeded
                # (a) Bright originals: contrast alone blows highlights
                if (stats["luma"] >= self.BRIGHT_IMAGE_LUMA
                        and adjustments.get('contrast', 1.0) > self.BRIGHT_CONTRAST_CAP):
                    print(f"  ⚠ Exposure-cap: capping contrast {adjustments['contrast']:.2f}x → "
                          f"{self.BRIGHT_CONTRAST_CAP}x on bright original "
                          f"(luma={stats['luma']:.2f}) — contrast blows highlights too")
                    adjustments['contrast'] = self.BRIGHT_CONTRAST_CAP

                # (b) Adaptive total exposure budget across all brightening ops:
                #     dark originals get more headroom than bright ones.
                budget_cap = (self.EXPOSURE_BUDGET_BASE
                              + self.EXPOSURE_BUDGET_DARK_BONUS * (1.0 - stats["luma"]))

                def _budget(b, c, sh):
                    return (b - 1.0) + 0.5 * (c - 1.0) + 0.5 * (sh / 100.0)

                shadow_pct = 0.0
                for op in advanced_ops:
                    if (isinstance(op, dict) and op.get('type') == 'shadows_highlights'
                            and op.get('shadow_adjust', 0) > 0):
                        shadow_pct = max(shadow_pct, op['shadow_adjust'])
                b = adjustments.get('brightness', 1.0)
                c = adjustments.get('contrast', 1.0)
                bud = _budget(b, c, shadow_pct)
                if b > 1.0 and bud > budget_cap:
                    # Trim 1: drop shadow brightening
                    if shadow_pct > 0:
                        print(f"  ⚠ Exposure-cap: dropping shadow brightening "
                              f"(+{shadow_pct:.0f}%) — combined exposure budget "
                              f"{bud:.2f} > {budget_cap:.2f}")
                        kept_ops = []
                        for op in advanced_ops:
                            if (isinstance(op, dict) and op.get('type') == 'shadows_highlights'
                                    and op.get('shadow_adjust', 0) > 0):
                                # keep the op only if it still has a highlight component
                                if op.get('highlight_adjust', 0) != 0:
                                    op = dict(op, shadow_adjust=0)
                                else:
                                    continue
                            kept_ops.append(op)
                        advanced_ops = kept_ops
                        shadow_pct = 0.0
                        bud = _budget(b, c, shadow_pct)
                    # Trim 2: reduce brightness
                    if bud > budget_cap:
                        max_b = 1.0 + budget_cap - 0.5 * (c - 1.0)
                        max_b = max(1.0, round(max_b, 4))
                        if max_b < b:
                            print(f"  ⚠ Exposure-cap: reducing brightness {b:.2f}x → "
                                  f"{max_b:.2f}x — combined exposure budget "
                                  f"{bud:.2f} > {budget_cap:.2f}")
                            adjustments['brightness'] = max_b
                            b = max_b
                            bud = _budget(b, c, shadow_pct)
                    # Trim 3: reduce contrast (last resort)
                    if bud > budget_cap and c > 1.0:
                        max_c = 1.0 + 2.0 * (budget_cap - (b - 1.0))
                        max_c = max(1.0, round(max_c, 4))
                        if max_c < c:
                            print(f"  ⚠ Exposure-cap: reducing contrast {c:.2f}x → "
                                  f"{max_c:.2f}x — combined exposure budget "
                                  f"{bud:.2f} > {budget_cap:.2f}")
                            adjustments['contrast'] = max_c

        return {
            'basic': adjustments,
            'advanced': advanced_ops
        }
    
    def _apply_adjustments(
        self,
        image_path: str,
        adjustments: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Apply extracted adjustments to image (both basic PIL adjustments and advanced operations)
        
        Args:
            image_path: Path to source image
            adjustments: Dictionary with 'basic' (PIL adjustments) and 'advanced' (operations) keys
            output_path: Final output path
            
        Returns:
            Path to saved image
        """
        try:
            image = Image.open(image_path)
            if image.mode != 'RGB' and image.mode != 'RGBA':
                image = image.convert('RGB')
            
            # Extract basic and advanced adjustments
            basic_adjustments = adjustments.get('basic', {})
            advanced_ops = adjustments.get('advanced', [])
            
            # Apply basic PIL adjustments in optimal order
            # 1. Brightness (affects overall exposure)
            if 'brightness' in basic_adjustments:
                print(f"    → Adjusting brightness ({basic_adjustments['brightness']:.2f}x)...")
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(basic_adjustments['brightness'])
            
            # 2. Contrast (affects perception of lighting)
            if 'contrast' in basic_adjustments:
                print(f"    → Adjusting contrast ({basic_adjustments['contrast']:.2f}x)...")
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(basic_adjustments['contrast'])
            
            # 3. Saturation (affects color vibrancy)
            if 'saturation' in basic_adjustments:
                print(f"    → Adjusting saturation ({basic_adjustments['saturation']:.2f}x)...")
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(basic_adjustments['saturation'])
            
            # 4. Sharpness (final detail enhancement)
            if 'sharpness' in basic_adjustments:
                print(f"    → Adjusting sharpness ({basic_adjustments['sharpness']:.2f}x)...")
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(basic_adjustments['sharpness'])
            
            # Save intermediate result after basic adjustments
            if not advanced_ops:
                # No advanced ops, save and return
                if output_path:
                    image.save(output_path, quality=95)
                    return output_path
                else:
                    image.save(image_path, quality=95)
                    return image_path
            
            # Create temporary directory for intermediate results
            # Use the same filesystem as the output to avoid filling up /tmp
            import tempfile
            import os
            if output_path:
                temp_dir = os.path.dirname(os.path.abspath(output_path))
            else:
                temp_dir = os.path.dirname(os.path.abspath(image_path))
            temp_image = os.path.join(temp_dir, '.intermediate_enhancement.jpg')
            image.save(temp_image, quality=95)
            current_path = temp_image
            
            # Apply advanced operations sequentially
            for op in advanced_ops:
                op_type = op.get('type')
                
                if op_type == 'unsharp_mask':
                    print("    → Applying unsharp mask...")
                    current_path = apply_unsharp_mask(
                        current_path,
                        radius=op.get('radius', 1.5),
                        percent=op.get('percent', 80),
                        threshold=op.get('threshold', 0),
                        output_path=current_path
                    )
                
                elif op_type == 'color_temperature':
                    print("    → Adjusting color temperature...")
                    current_path = adjust_color_temperature(
                        current_path,
                        kelvin=op.get('kelvin', 6500),
                        output_path=current_path
                    )
                
                elif op_type == 'shadows_highlights':
                    print("    → Adjusting shadows and highlights...")
                    current_path = adjust_shadows_highlights(
                        current_path,
                        shadow_adjust=op.get('shadow_adjust', 0),
                        highlight_adjust=op.get('highlight_adjust', 0),
                        output_path=current_path
                    )
                
                elif op_type == 'vibrance':
                    print("    → Adjusting vibrance...")
                    current_path = adjust_vibrance(
                        current_path,
                        factor=op.get('factor', 1.0),
                        output_path=current_path
                    )
                
                elif op_type == 'clarity':
                    print("    → Applying clarity filter...")
                    current_path = apply_clarity_filter(
                        current_path,
                        strength=op.get('strength', 20) * 100,  # Convert 0-1 to 0-100
                        output_path=current_path
                    )
                
                elif op_type == 'channel':
                    print(f"    → Adjusting {op.get('channel', 'unknown')} channel...")
                    current_path = adjust_color_channel(
                        current_path,
                        channel=op.get('channel', 'red'),
                        factor=op.get('factor', 1.0),
                        output_path=current_path
                    )
                
                if not current_path:
                    print(f"    → Error applying {op_type}")
                    # Fall back to saved intermediate image
                    break
            
            # Save final result
            if output_path:
                # Copy final result to output path
                import shutil
                shutil.copy(current_path, output_path)
                result_path = output_path
            else:
                # Copy final result back to original image
                import shutil
                shutil.copy(current_path, image_path)
                result_path = image_path
            
            # Clean up temporary file
            try:
                os.remove(temp_image)
            except:
                pass
            
            return result_path
        
        except Exception as e:
            print(f"Error applying adjustments: {e}")
            import traceback
            traceback.print_exc()
            return None


# Advanced filters are now in enhancement_filters module
# They are already imported at the top of this file

