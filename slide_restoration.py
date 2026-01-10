"""
Specialized enhancement for scanned old slides and dia positives

Old slides have characteristic issues:
- Strong color casts (magenta, yellow, cyan) from aging
- Reduced saturation and faded colors
- Lost contrast from film degradation
- Film grain and dust artifacts
- Color balance shifts
- Potential dust marks and scratches
"""
from PIL import Image, ImageEnhance, ImageFilter
from typing import Optional, Dict, Any
import json


class SlideRestoration:
    """Specialized restoration for old slides and dia positives"""
    
    # Restoration profiles for different slide conditions
    RESTORATION_PROFILES = {
        'faded': {
            'description': 'Very faded slide with lost color and contrast',
            'saturation': 1.5,      # Restore color vibrancy
            'contrast': 1.6,        # Restore lost contrast
            'brightness': 1.15,     # Lift shadows
            'sharpness': 1.2,       # Enhance clarity
            'color_balance': {'red': 1.0, 'green': 1.05, 'blue': 1.15},  # Neutral with cool boost
        },
        'color_cast': {
            'description': 'Strong color cast from aging (magenta, yellow, or cyan)',
            'saturation': 1.3,      # Moderate saturation
            'contrast': 1.4,        # Enhance contrast
            'brightness': 1.1,      # Subtle lift
            'sharpness': 1.15,      # Enhance details
            'color_balance': {'red': 1.0, 'green': 1.05, 'blue': 0.95},  # Neutral shift
        },
        'red_cast': {
            'description': 'Strong red/magenta color cast from aging',
            'saturation': 1.25,     # Moderate saturation recovery
            'contrast': 1.35,       # Restore contrast
            'brightness': 1.1,      # Subtle lift
            'sharpness': 1.15,      # Enhance clarity
            'color_balance': {'red': 0.85, 'green': 1.08, 'blue': 1.12},  # Reduce red, boost green and blue
        },
        'yellow_cast': {
            'description': 'Strong yellow color cast (warm aging)',
            'saturation': 1.3,
            'contrast': 1.35,
            'brightness': 1.1,
            'sharpness': 1.15,
            'color_balance': {'red': 0.95, 'green': 1.0, 'blue': 1.15},  # Boost blue, reduce red slightly
        },
        'aged': {
            'description': 'Moderately aged with some fading and contrast loss',
            'saturation': 1.25,
            'contrast': 1.3,
            'brightness': 1.08,
            'sharpness': 1.1,
            'color_balance': {'red': 1.0, 'green': 1.02, 'blue': 1.05},
        },
        'well_preserved': {
            'description': 'Well-preserved slide with minimal aging',
            'saturation': 1.1,
            'contrast': 1.15,
            'brightness': 1.05,
            'sharpness': 1.08,
            'color_balance': {'red': 1.0, 'green': 1.0, 'blue': 1.0},
        }
    }
    
    @staticmethod
    def analyze_slide_condition(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze slide-specific characteristics from image analysis
        
        Args:
            analysis_data: Full analysis data from picture_analyzer
            
        Returns:
            Dictionary with slide condition assessment
        """
        assessment = {
            'condition': 'unknown',
            'confidence': 0.0,
            'characteristics': [],
            'recommended_profile': 'aged',
            'notes': []
        }
        
        # Extract enhancement data if available
        if 'enhancement' not in analysis_data:
            return assessment
        
        enhancement = analysis_data['enhancement']
        
        # Check for color cast indicators
        color_info = enhancement.get('color_analysis', {})
        if isinstance(color_info, dict):
            color_temp = str(color_info.get('color_temperature', '')).lower()
            if 'magenta' in color_temp or 'red' in color_temp:
                assessment['characteristics'].append('red_magenta_cast')
                assessment['notes'].append('Detected red/magenta color cast typical of aged slides')
                assessment['recommended_profile'] = 'red_cast'
            elif 'warm' in color_temp and 'yellow' in color_temp:
                assessment['characteristics'].append('yellow_cast')
                assessment['notes'].append('Detected yellow/warm color cast')
                assessment['recommended_profile'] = 'yellow_cast'
            elif 'warm' in color_temp:
                assessment['characteristics'].append('warm_cast')
                assessment['notes'].append('Detected warm color cast')
                assessment['recommended_profile'] = 'yellow_cast'
            elif 'cyan' in color_temp or 'cool' in color_temp:
                assessment['characteristics'].append('cool_cast')
                assessment['notes'].append('Detected cool/cyan color cast typical of aged slides')
            
            # Check for fading indicators
            saturation = str(color_info.get('saturation_level', '')).lower()
            if 'dull' in saturation or 'low' in saturation:
                assessment['characteristics'].append('faded_colors')
                assessment['notes'].append('Colors appear faded, consistent with age degradation')
        
        # Check for contrast loss
        contrast_info = enhancement.get('contrast_level', {})
        if isinstance(contrast_info, dict):
            contrast_level = str(contrast_info.get('current_contrast', '')).lower()
            if 'low' in contrast_level:
                assessment['characteristics'].append('low_contrast')
                assessment['notes'].append('Reduced contrast typical of aged film')
        
        # Check for noise/grain
        sharpness_info = enhancement.get('sharpness_clarity', {})
        if isinstance(sharpness_info, dict):
            noise_level = str(sharpness_info.get('noise_level', '')).lower()
            if 'high' in noise_level or 'grain' in noise_level:
                assessment['characteristics'].append('high_grain')
                assessment['notes'].append('Film grain or dust artifacts detected')
        
        # Determine condition based on characteristics
        if len(assessment['characteristics']) >= 3:
            assessment['condition'] = 'heavily_aged'
            assessment['confidence'] = 0.85
        elif 'red_magenta_cast' in assessment['characteristics']:
            assessment['condition'] = 'red_cast'
            assessment['recommended_profile'] = 'red_cast'
            assessment['confidence'] = 0.8
        elif 'yellow_cast' in assessment['characteristics'] or 'warm_cast' in assessment['characteristics']:
            assessment['condition'] = 'yellow_cast'
            assessment['recommended_profile'] = 'yellow_cast'
            assessment['confidence'] = 0.8
        elif 'faded_colors' in assessment['characteristics']:
            assessment['condition'] = 'faded'
            assessment['recommended_profile'] = 'faded'
            assessment['confidence'] = 0.8
        elif 'cool_cast' in assessment['characteristics']:
            assessment['condition'] = 'color_cast'
            assessment['recommended_profile'] = 'color_cast'
            assessment['confidence'] = 0.75
        elif len(assessment['characteristics']) > 0:
            assessment['condition'] = 'aged'
            assessment['recommended_profile'] = 'aged'
            assessment['confidence'] = 0.7
        else:
            assessment['condition'] = 'well_preserved'
            assessment['recommended_profile'] = 'well_preserved'
            assessment['confidence'] = 0.6
        
        return assessment
    
    @staticmethod
    def restore_slide(
        image_path: str,
        profile: str = 'aged',
        output_path: Optional[str] = None,
        denoise: bool = True,
        despeckle: bool = True
    ) -> Optional[str]:
        """
        Restore a scanned slide using specialized profile
        
        Args:
            image_path: Path to scanned slide
            profile: Restoration profile ('faded', 'color_cast', 'aged', 'well_preserved')
            output_path: Path to save restored image
            denoise: Apply noise reduction
            despeckle: Remove dust/speckle artifacts
            
        Returns:
            Path to restored image
        """
        if profile not in SlideRestoration.RESTORATION_PROFILES:
            print(f"Unknown profile: {profile}. Using 'aged'")
            profile = 'aged'
        
        profile_config = SlideRestoration.RESTORATION_PROFILES[profile]
        
        try:
            image = Image.open(image_path)
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            print(f"\nRestoring slide with '{profile}' profile:")
            print(f"  Description: {profile_config['description']}")
            
            # 1. Optional despeckle (dust/scratch removal)
            if despeckle:
                print("  → Removing dust and speckles...")
                image = image.filter(ImageFilter.MedianFilter(size=3))
            
            # 2. Color balance correction
            color_balance = profile_config.get('color_balance', {})
            if color_balance != {'red': 1.0, 'green': 1.0, 'blue': 1.0}:
                print(f"  → Correcting color balance...")
                r, g, b = image.split()
                r = ImageEnhance.Brightness(r).enhance(color_balance.get('red', 1.0))
                g = ImageEnhance.Brightness(g).enhance(color_balance.get('green', 1.0))
                b = ImageEnhance.Brightness(b).enhance(color_balance.get('blue', 1.0))
                image = Image.merge('RGB', (r, g, b))
            
            # 3. Brightness (lift shadows)
            brightness_factor = profile_config.get('brightness', 1.0)
            print(f"  → Adjusting brightness ({brightness_factor:.2f}x)...")
            image = ImageEnhance.Brightness(image).enhance(brightness_factor)
            
            # 4. Contrast restoration
            contrast_factor = profile_config.get('contrast', 1.0)
            print(f"  → Restoring contrast ({contrast_factor:.2f}x)...")
            image = ImageEnhance.Contrast(image).enhance(contrast_factor)
            
            # 5. Saturation (restore faded colors)
            saturation_factor = profile_config.get('saturation', 1.0)
            print(f"  → Restoring color saturation ({saturation_factor:.2f}x)...")
            image = ImageEnhance.Color(image).enhance(saturation_factor)
            
            # 6. Optional noise reduction
            if denoise:
                print("  → Reducing film grain and noise...")
                # Light Gaussian blur to reduce grain
                image = image.filter(ImageFilter.GaussianBlur(radius=0.5))
            
            # 7. Sharpness enhancement
            sharpness_factor = profile_config.get('sharpness', 1.0)
            print(f"  → Enhancing sharpness ({sharpness_factor:.2f}x)...")
            image = ImageEnhance.Sharpness(image).enhance(sharpness_factor)
            
            # Save result
            if output_path:
                image.save(output_path, 'JPEG', quality=95)
                print(f"\n✓ Slide restoration complete: {output_path}")
                return output_path
            else:
                image.save(image_path, 'JPEG', quality=95)
                print(f"\n✓ Slide restoration complete: {image_path}")
                return image_path
        
        except Exception as e:
            print(f"✗ Error during slide restoration: {e}")
            return None
    
    @staticmethod
    def auto_restore_slide(
        image_path: str,
        analysis_data: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Automatically restore slide based on detected condition
        
        Args:
            image_path: Path to scanned slide
            analysis_data: Analysis data from picture_analyzer
            output_path: Path to save restored image
            
        Returns:
            Path to restored image
        """
        # Analyze slide condition
        condition = SlideRestoration.analyze_slide_condition(analysis_data)
        
        print(f"\nSlide Condition Assessment:")
        print(f"  Condition: {condition['condition']}")
        print(f"  Confidence: {condition['confidence']:.0%}")
        if condition['characteristics']:
            print(f"  Characteristics: {', '.join(condition['characteristics'])}")
        for note in condition['notes']:
            print(f"  - {note}")
        
        print(f"\nApplying restoration profile: {condition['recommended_profile']}")
        
        # Apply restoration with recommended profile
        return SlideRestoration.restore_slide(
            image_path,
            profile=condition['recommended_profile'],
            output_path=output_path,
            denoise=True,
            despeckle=True
        )
