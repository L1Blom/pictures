"""
Main picture analyzer module using OpenAI Vision API
"""
import json
import base64
import os
from pathlib import Path
from typing import Dict, Any, Optional
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, ANALYSIS_PROMPT, SUPPORTED_FORMATS, OUTPUT_DIR
from exif_handler import EXIFHandler

# Try to import HEIC support
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False


class PictureAnalyzer:
    """Analyzes pictures using OpenAI Vision API"""
    
    def __init__(self):
        """Initialize the analyzer with OpenAI client"""
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL
        self.exif_handler = EXIFHandler()
        
        # Create output directory if it doesn't exist
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    def analyze_picture(self, image_path: str) -> Dict[str, Any]:
        """
        Analyze a picture and extract detailed information
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary containing analysis results with 'metadata' and 'enhancement' sections
        """
        # Validate file
        if not self._validate_image_file(image_path):
            raise ValueError(f"Invalid or unsupported image file: {image_path}")
        
        # Check for description.txt in the same directory
        description = self._read_description(image_path)
        
        # Encode image to base64
        image_data = self._encode_image(image_path)
        
        # Send to OpenAI Vision API
        response = self._call_openai_vision(image_data, description)
        
        # Parse response
        analysis_result = self._parse_response(response)
        
        return analysis_result
    
    def analyze_and_save(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        save_json: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze a picture and save it with embedded EXIF data
        
        Args:
            image_path: Path to the source image
            output_path: Path to save the processed image (optional)
            save_json: Whether to also save analysis as JSON file
            
        Returns:
            Dictionary containing analysis results
        """
        # Analyze the picture
        analysis = self.analyze_picture(image_path)
        
        # Determine output path if not provided
        if output_path is None:
            filename = Path(image_path).stem
            output_path = os.path.join(OUTPUT_DIR, f"{filename}_analyzed.jpg")
        else:
            # Ensure output is JPG format (HEIC becomes JPG)
            output_path = str(Path(output_path).with_suffix('.jpg'))
        
        # Create output directory
        os.makedirs(os.path.dirname(output_path) or OUTPUT_DIR, exist_ok=True)
        
        # Convert HEIC to JPG first if needed
        converted_image_path = self._convert_heic_to_jpg(image_path)
        
        # Save with EXIF data
        success = self.exif_handler.write_exif(converted_image_path, output_path, analysis)
        
        if success:
            print(f"✓ Image saved with EXIF data: {output_path}")
        else:
            print(f"⚠ Could not embed EXIF, saved without: {output_path}")
        
        # Save JSON analysis
        if save_json:
            json_path = output_path.replace('.jpg', '.json').replace('.jpeg', '.json')
            with open(json_path, 'w') as f:
                json.dump(analysis, f, indent=2)
            print(f"✓ Analysis saved as JSON: {json_path}")
        
        return analysis
    
    def batch_analyze(
        self,
        directory: str,
        output_directory: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Analyze multiple pictures in a directory
        
        Args:
            directory: Path to directory containing images
            output_directory: Path to save processed images
            
        Returns:
            Dictionary with results for each image
        """
        if output_directory is None:
            output_directory = OUTPUT_DIR
        
        os.makedirs(output_directory, exist_ok=True)
        
        results = {}
        image_files = self._get_image_files(directory)
        
        print(f"Found {len(image_files)} images to analyze...")
        
        for i, image_path in enumerate(image_files, 1):
            try:
                filename = os.path.basename(image_path)
                print(f"\n[{i}/{len(image_files)}] Analyzing: {filename}")
                
                output_path = os.path.join(output_directory, f"{Path(filename).stem}_analyzed.jpg")
                analysis = self.analyze_and_save(image_path, output_path, save_json=True)
                results[filename] = analysis
                
            except Exception as e:
                print(f"✗ Error analyzing {image_path}: {e}")
                results[filename] = {"error": str(e)}
        
        # Save batch results summary
        summary_path = os.path.join(output_directory, "batch_analysis_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✓ Batch analysis complete. Summary saved: {summary_path}")
        return results
    
    def _validate_image_file(self, image_path: str) -> bool:
        """Check if file exists and has supported format"""
        if not os.path.exists(image_path):
            return False
        
        file_ext = Path(image_path).suffix.lower()
        return file_ext in SUPPORTED_FORMATS
    
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 string"""
        # Convert HEIC to JPG if needed
        image_path = self._convert_heic_to_jpg(image_path)
        
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def _convert_heic_to_jpg(self, image_path: str) -> str:
        """
        Convert HEIC image to JPG if needed
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Path to the image (JPG if converted, original otherwise)
        """
        file_ext = Path(image_path).suffix.lower()
        
        if file_ext != '.heic':
            return image_path
        
        if not HEIC_SUPPORT:
            raise ImportError(
                "HEIC support requires pillow-heif. "
                "Install it with: pip install pillow-heif"
            )
        
        try:
            from PIL import Image
            
            # Open HEIC image
            heic_image = Image.open(image_path)
            
            # Convert RGBA to RGB if needed
            if heic_image.mode in ('RGBA', 'LA', 'P'):
                rgb_image = Image.new('RGB', heic_image.size, (255, 255, 255))
                rgb_image.paste(heic_image, mask=heic_image.split()[-1] if heic_image.mode in ('RGBA', 'LA') else None)
                heic_image = rgb_image
            elif heic_image.mode != 'RGB':
                heic_image = heic_image.convert('RGB')
            
            # Save as JPG in temp directory (not in source directory to avoid permission issues)
            os.makedirs(os.path.join(os.getcwd(), 'tmp'), exist_ok=True)
            jpg_path = os.path.join(os.getcwd(), 'tmp', Path(image_path).stem + '.jpg')
            heic_image.save(jpg_path, 'JPEG', quality=95)
            
            return jpg_path
        except Exception as e:
            print(f"Warning: Could not convert HEIC file: {e}")
            raise
    
    def _get_image_media_type(self, image_path: str) -> str:
        """Get media type for the image file"""
        ext = Path(image_path).suffix.lower()
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        return media_types.get(ext, 'image/jpeg')
    
    def _read_description(self, image_path: str) -> Optional[str]:
        """
        Read description.txt from the same directory as the image
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Description text if found, None otherwise
        """
        image_dir = Path(image_path).parent
        description_file = image_dir / 'description.txt'
        
        if description_file.exists():
            try:
                with open(description_file, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                print(f"Warning: Could not read description.txt: {e}")
                return None
        
        return None
    
    def _call_openai_vision(self, image_data: str, description: Optional[str] = None) -> str:
        """Call OpenAI Vision API with the image"""
        # Prepare the prompt with optional context
        prompt = ANALYSIS_PROMPT
        if description:
            prompt = f"{prompt}\n\n=== CONTEXT FROM DESCRIPTION.TXT ===\n{description}\n\nPlease consider this context when analyzing the image."
        
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                            },
                        }
                    ],
                }
            ],
        )
        
        return response.choices[0].message.content
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse OpenAI response into structured format with metadata and enhancement sections"""
        try:
            # Try to extract JSON from the response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                analysis = json.loads(json_str)
                
                # If response has metadata and enhancement sections, return as-is
                if isinstance(analysis, dict) and ('metadata' in analysis or 'enhancement' in analysis):
                    return analysis
                else:
                    # Backward compatibility: wrap old format response
                    return {
                        "metadata": analysis,
                        "enhancement": {
                            "note": "Enhancement data not available for this analysis"
                        }
                    }
            else:
                # If no JSON found, create structured response from text
                analysis = {
                    "metadata": {
                        "raw_response": response,
                        "objects": [],
                        "persons": "Not detected",
                        "weather": "Unknown",
                        "mood": "Unknown",
                        "time_of_day": "Unknown",
                        "season_date": "Unknown",
                    },
                    "enhancement": {
                        "raw_response": response,
                        "lighting_quality": "Unable to assess",
                        "color_analysis": "Unable to assess",
                        "sharpness_clarity": "Unable to assess",
                        "contrast_level": "Unable to assess",
                        "composition_issues": "Unable to assess",
                        "recommended_enhancements": []
                    }
                }
                return analysis
        except json.JSONDecodeError:
            analysis = {
                "metadata": {
                    "raw_response": response,
                    "objects": [],
                    "persons": "Not detected",
                    "weather": "Unknown",
                    "mood": "Unknown",
                    "time_of_day": "Unknown",
                    "season_date": "Unknown",
                },
                "enhancement": {
                    "raw_response": response,
                    "lighting_quality": "Unable to assess",
                    "color_analysis": "Unable to assess",
                    "sharpness_clarity": "Unable to assess",
                    "contrast_level": "Unable to assess",
                    "composition_issues": "Unable to assess",
                    "recommended_enhancements": []
                }
            }
            return analysis
    
    def _get_image_files(self, directory: str) -> list:
        """Get all image files in a directory"""
        image_files = []
        for ext in SUPPORTED_FORMATS:
            image_files.extend(Path(directory).glob(f"*{ext}"))
            image_files.extend(Path(directory).glob(f"*{ext.upper()}"))
        
        return sorted(list(set(image_files)))


# Example usage
if __name__ == "__main__":
    analyzer = PictureAnalyzer()
    
    # Example: Analyze a single image
    # results = analyzer.analyze_and_save("path/to/image.jpg")
    # print(json.dumps(results, indent=2))
    
    # Example: Batch analyze images
    # results = analyzer.batch_analyze("pictures/")
    
    print("Picture Analyzer initialized successfully!")
