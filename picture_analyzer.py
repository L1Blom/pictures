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
            Dictionary containing analysis results
        """
        # Validate file
        if not self._validate_image_file(image_path):
            raise ValueError(f"Invalid or unsupported image file: {image_path}")
        
        # Encode image to base64
        image_data = self._encode_image(image_path)
        
        # Send to OpenAI Vision API
        response = self._call_openai_vision(image_data)
        
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
        
        # Create output directory
        os.makedirs(os.path.dirname(output_path) or OUTPUT_DIR, exist_ok=True)
        
        # Save with EXIF data
        success = self.exif_handler.write_exif(image_path, output_path, analysis)
        
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
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
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
    
    def _call_openai_vision(self, image_data: str) -> str:
        """Call OpenAI Vision API with the image"""
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": ANALYSIS_PROMPT
                        }
                    ],
                }
            ],
        )
        
        return message.content[0].text
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse OpenAI response into structured format"""
        try:
            # Try to extract JSON from the response
            # Look for JSON block in the response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                analysis = json.loads(json_str)
            else:
                # If no JSON found, create structured response from text
                analysis = {
                    "raw_response": response,
                    "objects": [],
                    "persons": "Not detected",
                    "weather": "Unknown",
                    "mood": "Unknown",
                    "time_of_day": "Unknown",
                    "date_season": "Unknown",
                    "additional_notes": response
                }
        except json.JSONDecodeError:
            analysis = {
                "raw_response": response,
                "objects": [],
                "persons": "Not detected",
                "weather": "Unknown",
                "mood": "Unknown",
                "time_of_day": "Unknown",
                "date_season": "Unknown",
                "additional_notes": response
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
