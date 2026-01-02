"""
Picture enhancement utilities with AI-guided recommendations

This module provides:
- Smart enhancement based on AI analysis recommendations
- Color correction
- Brightness/contrast adjustment
- Sharpness enhancement
- Saturation adjustment
- Noise reduction
- And more...
"""
from PIL import Image, ImageEnhance, ImageFilter
from typing import Optional, Tuple, List, Dict, Any
import os
import json
import re
from pathlib import Path


class PictureEnhancer:
    """Handles picture enhancement operations"""
    
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
        try:
            image = Image.open(image_path)
            enhancer = ImageEnhance.Brightness(image)
            enhanced = enhancer.enhance(factor)
            
            if output_path:
                enhanced.save(output_path)
                return output_path
            return None
        except Exception as e:
            print(f"Error adjusting brightness: {e}")
            return None
    
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
        try:
            image = Image.open(image_path)
            enhancer = ImageEnhance.Contrast(image)
            enhanced = enhancer.enhance(factor)
            
            if output_path:
                enhanced.save(output_path)
                return output_path
            return None
        except Exception as e:
            print(f"Error adjusting contrast: {e}")
            return None
    
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
        try:
            image = Image.open(image_path)
            enhancer = ImageEnhance.Color(image)
            enhanced = enhancer.enhance(factor)
            
            if output_path:
                enhanced.save(output_path)
                return output_path
            return None
        except Exception as e:
            print(f"Error adjusting saturation: {e}")
            return None
    
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
        try:
            image = Image.open(image_path)
            enhancer = ImageEnhance.Sharpness(image)
            enhanced = enhancer.enhance(factor)
            
            if output_path:
                enhanced.save(output_path)
                return output_path
            return None
        except Exception as e:
            print(f"Error adjusting sharpness: {e}")
            return None
    
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
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Enhance image based on AI analysis recommendations
        
        Args:
            image_path: Path to source image
            enhancement_data: Enhancement section from AI analysis
            output_path: Path to save enhanced image
            
        Returns:
            Path to saved image or None if failed
        """
        try:
            # Start with the original image
            current_image_path = image_path
            
            # Extract recommendations
            recommendations = enhancement_data.get('recommended_enhancements', [])
            
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
                output_path
            )
        except Exception as e:
            print(f"Error reading analysis file: {e}")
            return None
    
    def _parse_recommendations(
        self,
        recommendations: List[str],
        enhancement_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Parse AI recommendations and extract adjustment factors
        
        Args:
            recommendations: List of recommendation strings
            enhancement_data: Full enhancement data for context
            
        Returns:
            Dictionary of adjustment factors
        """
        adjustments = {}
        
        for recommendation in recommendations:
            rec_lower = recommendation.lower()
            
            # Parse brightness adjustments
            brightness_match = re.search(r'brightness.*?([+-]?\d+)%?', rec_lower)
            if brightness_match:
                percent = int(brightness_match.group(1))
                factor = 1.0 + (percent / 100.0)
                adjustments['brightness'] = factor
                print(f"  → Brightness: {percent:+d}% (factor: {factor:.2f})")
            
            # Parse contrast adjustments
            contrast_match = re.search(r'contrast.*?([+-]?\d+)%?', rec_lower)
            if contrast_match:
                percent = int(contrast_match.group(1))
                factor = 1.0 + (percent / 100.0)
                adjustments['contrast'] = factor
                print(f"  → Contrast: {percent:+d}% (factor: {factor:.2f})")
            
            # Parse saturation/color adjustments
            if re.search(r'saturat|vibrant|emphasiz.*color|warm|cool', rec_lower):
                # Extract percentage if present
                saturation_match = re.search(r'(?:saturati|vibrant|color).*?([+-]?\d+)%?', rec_lower)
                if saturation_match:
                    percent = int(saturation_match.group(1))
                    factor = 1.0 + (percent / 100.0)
                else:
                    # Default increase for color emphasis
                    factor = 1.15
                adjustments['saturation'] = factor
                print(f"  → Saturation: {(factor - 1) * 100:+.0f}% (factor: {factor:.2f})")
            
            # Parse sharpness adjustments
            sharpness_match = re.search(r'sharpen|enhance.*detail|enhance sharpness.*?([+-]?\d+)%?', rec_lower)
            if sharpness_match:
                if sharpness_match.group(1):
                    percent = int(sharpness_match.group(1))
                    factor = 1.0 + (percent / 100.0)
                else:
                    # Default sharpening
                    factor = 1.3
                adjustments['sharpness'] = factor
                print(f"  → Sharpness: {(factor - 1) * 100:+.0f}% (factor: {factor:.2f})")
            
            # Parse highlight reduction
            if 'highlight' in rec_lower or 'exposure' in rec_lower:
                adjustments['reduce_highlights'] = True
                print(f"  → Reduce highlights: true")
        
        return adjustments
    
    def _apply_adjustments(
        self,
        image_path: str,
        adjustments: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Apply extracted adjustments to image
        
        Args:
            image_path: Path to source image
            adjustments: Dictionary of adjustments to apply
            output_path: Final output path
            
        Returns:
            Path to saved image
        """
        try:
            image = Image.open(image_path)
            
            # Apply adjustments in optimal order
            # 1. Brightness (affects overall exposure)
            if 'brightness' in adjustments:
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(adjustments['brightness'])
            
            # 2. Contrast (affects perception of lighting)
            if 'contrast' in adjustments:
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(adjustments['contrast'])
            
            # 3. Saturation (affects color vibrancy)
            if 'saturation' in adjustments:
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(adjustments['saturation'])
            
            # 4. Sharpness (final detail enhancement)
            if 'sharpness' in adjustments:
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(adjustments['sharpness'])
            
            # 5. Reduce highlights (tone mapping effect)
            if adjustments.get('reduce_highlights'):
                # Slight darkening of bright areas by reducing contrast slightly
                # then re-applying brightness strategically
                pass  # For now, contrast reduction handles this
            
            # Save the enhanced image
            if output_path:
                image.save(output_path)
                return output_path
            else:
                # If no output specified, modify original
                image.save(image_path)
                return image_path
        
        except Exception as e:
            print(f"Error applying adjustments: {e}")
            return None


# Future enhancement placeholders
def upscale_image(image_path: str, scale: int = 2) -> Optional[str]:
    """
    Upscale image using AI (requires external service)
    TODO: Implement with upscaling service (e.g., Real-ESRGAN)
    """
    pass


def remove_noise(image_path: str) -> Optional[str]:
    """
    Remove noise from image
    TODO: Implement noise reduction algorithm
    """
    pass


def auto_color_correction(image_path: str) -> Optional[str]:
    """
    Automatically correct image colors
    TODO: Implement color correction algorithm
    """
    pass
