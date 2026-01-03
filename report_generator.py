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
            output_dir: Directory containing analyzed images and analysis.json files
            report_path: Optional path to save report. If None, returns as string
            
        Returns:
            Markdown report content
        """
        output_dir = Path(output_dir)
        
        # Collect all image analysis results
        image_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        analyses = []
        
        for img_dir in sorted(image_dirs):
            analysis_file = img_dir / "analysis.json"
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
        lines.append("| # | Image | Objects | Persons | Location | Mood |")
        lines.append("|---|-------|---------|---------|----------|------|")
        
        for idx, item in enumerate(analyses, 1):
            metadata = item['analysis'].get('metadata', {})
            objects = metadata.get('objects_subjects', 'N/A')[:20]
            persons = metadata.get('persons_count', 'N/A')
            location = metadata.get('location_setting', 'N/A')[:20]
            mood = metadata.get('mood_atmosphere', 'N/A')[:15]
            
            # Truncate for table
            objects = (objects[:17] + "...") if len(str(objects)) > 20 else objects
            location = (location[:17] + "...") if len(str(location)) > 20 else location
            mood = (mood[:12] + "...") if len(str(mood)) > 15 else mood
            
            lines.append(f"| {idx} | {item['name']} | {objects} | {persons} | {location} | {mood} |")
        
        lines.append("")
        
        # Detailed analysis for each image
        for idx, item in enumerate(analyses, 1):
            lines.append(f"## {idx}. {item['name']}")
            lines.append("")
            
            # Description if available
            if item['description']:
                lines.append("### Description")
                lines.append("")
                lines.append(f"> {item['description']}")
                lines.append("")
            
            # Image thumbnails
            lines.append("### Images")
            lines.append("")
            
            # Analyzed image
            if item['analyzed_img'] and item['analyzed_img'].exists():
                img_rel_path = item['analyzed_img'].relative_to(item['analyzed_img'].parent.parent)
                lines.append(f"**Original with EXIF:**  \n![Analyzed]({img_rel_path})")
                lines.append("")
            
            # Enhanced image
            if item['enhanced_img'] and item['enhanced_img'].exists():
                img_rel_path = item['enhanced_img'].relative_to(item['enhanced_img'].parent.parent)
                lines.append(f"**Enhanced:**  \n![Enhanced]({img_rel_path})")
                lines.append("")
            
            # Restored images
            if item['restored_imgs']:
                lines.append("**Restored versions:**")
                lines.append("")
                for restored in item['restored_imgs']:
                    profile = restored.stem.split('_restored_')[-1] if '_restored_' in restored.stem else 'restored'
                    img_rel_path = restored.relative_to(restored.parent.parent)
                    lines.append(f"- **{profile.title()}:** ![{profile}]({img_rel_path})")
                lines.append("")
            
            # Full metadata table
            lines.append("### Full Analysis")
            lines.append("")
            
            metadata = item['analysis'].get('metadata', {})
            lines.append("| Aspect | Details |")
            lines.append("|--------|---------|")
            
            # Map metadata to readable format
            metadata_display = [
                ("Objects & Subjects", metadata.get('objects_subjects', 'N/A')),
                ("Persons Count", metadata.get('persons_count', 'N/A')),
                ("Persons Position", metadata.get('persons_position', 'N/A')),
                ("Weather", metadata.get('weather_conditions', 'N/A')),
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
                # Escape pipe characters in detail
                detail_str = str(detail).replace('|', '\\|')
                lines.append(f"| {aspect} | {detail_str} |")
            
            lines.append("")
            
            # Enhancement recommendations
            enhancement = item['analysis'].get('enhancement', {})
            if enhancement:
                lines.append("### Enhancement Recommendations")
                lines.append("")
                lines.append("| Parameter | Recommendation |")
                lines.append("|-----------|-----------------|")
                
                for param, value in enhancement.items():
                    if param != 'summary':
                        lines.append(f"| {param.title()} | {value} |")
                
                if 'summary' in enhancement:
                    lines.append("")
                    lines.append(f"**Summary:** {enhancement['summary']}")
                    lines.append("")
            
            # Slide restoration profiles (if available)
            profiles = item['analysis'].get('slide_profiles', [])
            if profiles:
                lines.append("### Recommended Restoration Profiles")
                lines.append("")
                lines.append("| Profile | Confidence | Reason |")
                lines.append("|---------|------------|--------|")
                
                for profile in profiles:
                    name = profile.get('profile', 'Unknown')
                    conf = f"{profile.get('confidence', 0):.0%}"
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
