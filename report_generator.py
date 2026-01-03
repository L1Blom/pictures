"""Report generator for picture analysis results"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from PIL import Image
import base64


class ReportGenerator:
    """Generates markdown reports from analysis results with thumbnails"""
    
    def __init__(self, thumbnail_size: tuple = (200, 200)):
        """
        Initialize report generator
        
        Args:
            thumbnail_size: Size of thumbnails in report (width, height)
        """
        self.thumbnail_size = thumbnail_size
    
    def generate_report(self, output_dir: Path, report_path: Optional[Path] = None) -> str:
        """
        Generate markdown report from analysis results in output directory
        
        Args:
            output_dir: Directory containing analyzed images and analyzed.json files
            report_path: Optional path to save report. If None, returns as string
            
        Returns:
            Markdown report content
        """
        output_dir = Path(output_dir)
        
        # Collect all image analysis results
        # Handle both flat structure (files in output_dir) and nested structure (in subdirs)
        analyses = []
        
        # First, try to find JSON files directly in output_dir
        for json_file in output_dir.glob("*_analyzed.json"):
            with open(json_file, 'r') as f:
                analysis = json.load(f)
            
            # Find corresponding image
            base_name = json_file.stem.replace('_analyzed', '')
            
            # Look for images
            analyzed_img = None
            for ext in ['*.jpg', '*.png', '*.gif', '*.bmp', '*.tiff', '*.webp', '*.heic']:
                for file in output_dir.glob(f"{base_name}*_analyzed.{ext.split('.')[-1]}"):
                    analyzed_img = file
                    break
                if analyzed_img:
                    break
            
            # Look for enhanced and restored versions
            enhanced_img = None
            for file in output_dir.glob(f"{base_name}*_enhanced.*"):
                enhanced_img = file
                break
            
            restored_imgs = []
            for file in output_dir.glob(f"{base_name}*_restored*.jpg"):
                restored_imgs.append(file)
            
            analyses.append({
                'name': base_name,
                'analysis': analysis,
                'description': None,  # No description in flat structure
                'analyzed_img': analyzed_img,
                'enhanced_img': enhanced_img,
                'restored_imgs': sorted(restored_imgs),
                'dir': output_dir
            })
        
        # Then, look for nested structure (subdirectories with image-specific results)
        image_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        for img_dir in sorted(image_dirs):
            analysis_file = img_dir / "analyzed.json"
            if analysis_file.exists():
                with open(analysis_file, 'r') as f:
                    analysis = json.load(f)
                
                # Read description.txt if available
                desc_text = None
                desc_file = img_dir / "description.txt"
                if desc_file.exists():
                    with open(desc_file, 'r') as f:
                        desc_text = f.read().strip()
                
                # Find image files
                analyzed_img = None
                enhanced_img = None
                restored_imgs = []
                
                for file in img_dir.glob("*_analyzed.jpg"):
                    analyzed_img = file
                
                for file in img_dir.glob("*_enhanced.jpg"):
                    enhanced_img = file
                
                for file in img_dir.glob("*_restored*.jpg"):
                    restored_imgs.append(file)
                
                analyses.append({
                    'name': img_dir.name,
                    'analysis': analysis,
                    'description': desc_text,
                    'analyzed_img': analyzed_img,
                    'enhanced_img': enhanced_img,
                    'restored_imgs': sorted(restored_imgs),
                    'dir': img_dir
                })
        
        # Generate report
        markdown = self._build_markdown(analyses)
        
        # Save if path provided
        if report_path:
            report_path = Path(report_path)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, 'w') as f:
                f.write(markdown)
            print(f"✅ Report saved to: {report_path}")
        
        return markdown
    
    def _build_markdown(self, analyses: List[Dict]) -> str:
        """Build markdown report from analyses"""
        lines = []
        
        # Header
        lines.append("# Picture Analysis Report")
        lines.append(f"\n**Total Images Analyzed:** {len(analyses)}")
        lines.append("")
        
        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append("| # | Image | Objects | Persons | Weather | Mood |")
        lines.append("|---|-------|---------|---------|---------|------|")
        
        for idx, item in enumerate(analyses, 1):
            metadata = item['analysis'].get('metadata', {})
            
            # Extract and format fields
            objects = metadata.get('objects', metadata.get('objects_subjects', 'N/A'))
            if isinstance(objects, list):
                objects = ', '.join(str(o) for o in objects[:3]) if objects else 'N/A'
            objects = str(objects)
            if len(objects) > 50:
                objects = objects[:47] + "..."
            
            persons = metadata.get('persons', metadata.get('persons_count', 'N/A'))
            persons = str(persons)
            if len(persons) > 40:
                persons = persons[:37] + "..."
            
            weather = metadata.get('weather', metadata.get('weather_conditions', 'N/A'))
            weather = str(weather)
            if len(weather) > 40:
                weather = weather[:37] + "..."
            
            mood = metadata.get('mood_atmosphere', 'N/A')
            mood = str(mood)
            if len(mood) > 50:
                mood = mood[:47] + "..."
            
            lines.append(f"| {idx} | {item['name']} | {objects} | {persons} | {weather} | {mood} |")
        
        lines.append("")
        
        # Detailed analysis for each image
        for idx, item in enumerate(analyses, 1):
            lines.append("")
            lines.append(f"## {idx}. {item['name']}")
            lines.append("")
            
            # Description if available
            if item['description']:
                lines.append("### Description")
                lines.append("")
                lines.append(f"> {item['description']}")
                lines.append("")
            
            # Image thumbnails
            lines.append("")
            lines.append("### Images")
            lines.append("")
            
            # Analyzed image
            if item['analyzed_img'] and item['analyzed_img'].exists():
                # Use just filename since images are in same directory as report
                img_path = item['analyzed_img'].name
                lines.append(f"**Original with EXIF:**  \n![Analyzed]({img_path})")
                lines.append("")
            
            # Enhanced image
            if item['enhanced_img'] and item['enhanced_img'].exists():
                # Use just filename since images are in same directory as report
                img_path = item['enhanced_img'].name
                lines.append(f"**Enhanced:**  \n![Enhanced]({img_path})")
                lines.append("")
            
            # Restored images
            if item['restored_imgs']:
                lines.append("**Restored versions:**")
                lines.append("")
                for restored in item['restored_imgs']:
                    profile = restored.stem.split('_restored_')[-1] if '_restored_' in restored.stem else 'restored'
                    img_path = restored.name
                    lines.append(f"- **{profile.title()}:** ![{profile}]({img_path})")
                lines.append("")
            
            # Full metadata table
            lines.append("")
            lines.append("### Full Analysis")
            lines.append("")
            
            metadata = item['analysis'].get('metadata', {})
            lines.append("| Aspect | Details |")
            lines.append("|--------|---------|")
            
            # Map metadata to readable format (handle both old and new field names)
            metadata_display = [
                ("Objects", metadata.get('objects', metadata.get('objects_subjects', 'N/A'))),
                ("Persons", metadata.get('persons', metadata.get('persons_count', 'N/A'))),
                ("Weather", metadata.get('weather', metadata.get('weather_conditions', 'N/A'))),
                ("Mood & Atmosphere", metadata.get('mood_atmosphere', 'N/A')),
                ("Time of Day", metadata.get('time_of_day', 'N/A')),
                ("Season & Date", metadata.get('season_date', 'N/A')),
                ("Scene Type", metadata.get('scene_type', 'N/A')),
                ("Location & Setting", metadata.get('location_setting', 'N/A')),
                ("Activity", metadata.get('activity', 'N/A')),
                ("Photography Style", metadata.get('photography_style', 'N/A')),
                ("Composition Quality", metadata.get('composition_quality', 'N/A')),
            ]
            
            for aspect, detail in metadata_display:
                # Format detail - handle lists/dicts
                if isinstance(detail, list):
                    if detail and isinstance(detail[0], dict):
                        # List of dicts - extract first description/value
                        detail_str = detail[0].get('description', str(detail[0])) if detail else 'N/A'
                    else:
                        # Simple list
                        detail_str = ', '.join(str(d) for d in detail[:3]) if detail else 'N/A'
                elif isinstance(detail, dict):
                    detail_str = str(detail)
                else:
                    detail_str = str(detail)
                
                # Escape pipe characters and truncate if too long
                detail_str = detail_str.replace('|', '\\|')
                if len(detail_str) > 200:
                    detail_str = detail_str[:197] + "..."
                
                lines.append(f"| {aspect} | {detail_str} |")
            
            lines.append("")
            
            # Enhancement recommendations
            enhancement = item['analysis'].get('enhancement', {})
            if enhancement:
                lines.append("")
                lines.append("### Enhancement Recommendations")
                lines.append("")
                lines.append("| Parameter | Recommendation |")
                lines.append("|-----------|-----------------|")
                
                for param, value in enhancement.items():
                    if param != 'summary' and param.lower() != 'raw_response':
                        # Format value - avoid raw JSON
                        if isinstance(value, (dict, list)):
                            value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                        else:
                            value_str = str(value).replace('|', '\\|')
                        lines.append(f"| {param.title()} | {value_str} |")
                
                if 'summary' in enhancement:
                    lines.append("")
                    lines.append(f"**Summary:** {enhancement['summary']}")
                    lines.append("")
                
                lines.append("")
            
            # Slide restoration profiles (if available)
            profiles = item['analysis'].get('slide_profiles', [])
            if profiles:
                lines.append("")
                lines.append("### Recommended Restoration Profiles")
                lines.append("")
                lines.append("| Profile | Confidence | Reason |")
                lines.append("|---------|------------|--------|")
                
                for profile in profiles:
                    name = profile.get('profile', 'Unknown')
                    confidence = profile.get('confidence', 0)
                    # Handle both decimal (0.6) and percentage (60) formats
                    if confidence > 1:
                        conf = f"{confidence:.0f}%"
                    else:
                        conf = f"{confidence:.0%}"
                    reason = profile.get('reason', 'N/A')
                    lines.append(f"| {name.title()} | {conf} | {reason} |")
                
                lines.append("")
            
            # Add page break
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def _image_to_base64(self, image_path: Path, max_size: int = 300) -> str:
        """
        Convert image to base64 embedded in markdown
        
        Args:
            image_path: Path to image file
            max_size: Maximum dimension for thumbnail
            
        Returns:
            Base64 encoded image string
        """
        try:
            img = Image.open(image_path)
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            
            # Save to bytes
            import io
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            img_data = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/jpeg;base64,{img_data}"
        except Exception as e:
            print(f"Warning: Could not process image {image_path}: {e}")
            return ""
