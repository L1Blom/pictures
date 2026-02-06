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
    
    def __init__(self):
        """Initialize smart enhancer"""
        self.enhancer = PictureEnhancer()
    
    def enhance_from_analysis(
        self,
        image_path: str,
        enhancement_data: Dict[str, Any],
        output_path: Optional[str] = None,
        analysis_data: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Enhance image based on AI analysis recommendations
        
        Args:
            image_path: Path to source image
            enhancement_data: Enhancement section from AI analysis
            output_path: Path to save enhanced image
            analysis_data: Full analysis data (optional, for profile matching)
            
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
            adjustments = self._parse_recommendations(recommendations, enhancement_data)
            
            # Apply adjustments in optimal order
            current_image_path = self._apply_adjustments(
                current_image_path,
                adjustments,
                output_path
            )
            
            # Step 2: Apply AI-detected profile if confidence is high (>70%)
            if analysis_data and current_image_path:
                slide_profiles = analysis_data.get('slide_profiles', [])
                if slide_profiles and isinstance(slide_profiles, list):
                    # Get the top-confidence profile
                    top_profile = None
                    max_confidence = 0
                    
                    for p in slide_profiles:
                        if isinstance(p, dict) and 'profile' in p and 'confidence' in p:
                            confidence = p.get('confidence', 0)
                            if confidence > max_confidence:
                                max_confidence = confidence
                                top_profile = p.get('profile')
                    
                    # Apply profile if confidence is high enough
                    if top_profile and max_confidence >= 70:
                        print(f"  → Applying AI-detected profile: {top_profile} ({max_confidence}% confidence)")
                        from slide_restoration import SlideRestoration
                        
                        # Create temporary output for profile
                        profile_output = current_image_path.replace('.jpg', '_profiled.jpg') if current_image_path.endswith('.jpg') else current_image_path + '_profiled.jpg'
                        
                        SlideRestoration.restore_slide(
                            current_image_path,
                            profile=top_profile,
                            output_path=profile_output
                        )
                        
                        if Path(profile_output).exists():
                            # Use profiled version as final output
                            if output_path:
                                import shutil
                                shutil.move(profile_output, output_path)
                                current_image_path = output_path
                            else:
                                current_image_path = profile_output
            
            return current_image_path
        
        except Exception as e:
            print(f"Error during smart enhancement: {e}")
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
        enhancement_data: Dict[str, Any]
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
                # Determine which channel
                channel = None
                if 'red' in rec_lower:
                    channel = 'red'
                elif 'blue' in rec_lower:
                    channel = 'blue'
                elif 'green' in rec_lower:
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
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(basic_adjustments['brightness'])
            
            # 2. Contrast (affects perception of lighting)
            if 'contrast' in basic_adjustments:
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(basic_adjustments['contrast'])
            
            # 3. Saturation (affects color vibrancy)
            if 'saturation' in basic_adjustments:
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(basic_adjustments['saturation'])
            
            # 4. Sharpness (final detail enhancement)
            if 'sharpness' in basic_adjustments:
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
            import tempfile
            import os
            temp_dir = tempfile.gettempdir()
            temp_image = os.path.join(temp_dir, 'intermediate_enhancement.jpg')
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

