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
        # Sort analyses by name
        analyses = sorted(analyses, key=lambda x: x['name'])
        markdown = self._build_markdown(analyses)
        
        # Save if path provided
        if report_path:
            report_path = Path(report_path)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, 'w') as f:
                f.write(markdown)
            print(f"✅ Report saved to: {report_path}")
        
        return markdown
    
    def generate_gallery_report(self, output_dir: Path, report_path: Optional[Path] = None) -> str:
        """
        Generate a gallery report showing all images for each input in a table format
        
        Args:
            output_dir: Directory containing analyzed images and analyzed.json files
            report_path: Optional path to save report. If None, returns as string
            
        Returns:
            Markdown gallery report content
        """
        output_dir = Path(output_dir)
        
        # Collect all image analysis results (same logic as generate_report)
        analyses = []
        
        # First, try to find JSON files directly in output_dir
        for json_file in output_dir.glob("*_analyzed.json"):
            with open(json_file, 'r') as f:
                analysis = json.load(f)
            
            base_name = json_file.stem.replace('_analyzed', '')
            
            analyzed_img = None
            for ext in ['*.jpg', '*.png', '*.gif', '*.bmp', '*.tiff', '*.webp', '*.heic']:
                for file in output_dir.glob(f"{base_name}*_analyzed.{ext.split('.')[-1]}"):
                    analyzed_img = file
                    break
                if analyzed_img:
                    break
            
            enhanced_img = None
            for file in output_dir.glob(f"{base_name}*_enhanced.*"):
                enhanced_img = file
                break
            
            restored_imgs = []
            for file in output_dir.glob(f"{base_name}*_restored*.jpg"):
                restored_imgs.append(file)
            
            analyses.append({
                'name': base_name,
                'analyzed_img': analyzed_img,
                'enhanced_img': enhanced_img,
                'restored_imgs': sorted(restored_imgs),
                'dir': output_dir
            })
        
        # Then, look for nested structure
        image_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        for img_dir in sorted(image_dirs):
            analysis_file = img_dir / "analyzed.json"
            if analysis_file.exists():
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
                    'analyzed_img': analyzed_img,
                    'enhanced_img': enhanced_img,
                    'restored_imgs': sorted(restored_imgs),
                    'dir': img_dir
                })
        
        # Sort by name
        analyses = sorted(analyses, key=lambda x: x['name'])
        
        # Generate gallery report
        markdown = self._build_gallery_markdown(analyses)
        
        # Save if path provided
        if report_path:
            report_path = Path(report_path)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, 'w') as f:
                f.write(markdown)
            print(f"✅ Gallery report saved to: {report_path}")
        
        return markdown
    
    def _build_gallery_markdown(self, analyses: List[Dict]) -> str:
        """Build markdown gallery report showing all images in table format with up to 2 restored profiles"""
        lines = []
        
        # Header
        lines.append("# Picture Gallery Report")
        lines.append(f"\n**Total Images:** {len(analyses)}")
        lines.append("")
        
        # Gallery table with images - 6 columns: #, Name, Original, Enhanced, Restored 1, Restored 2
        lines.append("## Image Gallery")
        lines.append("")
        lines.append("| # | Image Name | Original | Enhanced | Restored 1 | Restored 2 |")
        lines.append("|---|------------|----------|----------|-----------|-----------|")
        
        for idx, item in enumerate(analyses, 1):
            original = ""
            enhanced = ""
            restored_1 = ""
            restored_2 = ""
            
            # Original image - create thumbnail for consistent sizing
            if item['analyzed_img'] and item['analyzed_img'].exists():
                thumb_path = self._create_thumbnail(item['analyzed_img'], item['dir'])
                if thumb_path:
                    thumb_name = f"{item['analyzed_img'].stem}_thumb.jpg"
                    original = f"![]({thumb_name})"
            
            # Enhanced image - same size
            if item['enhanced_img'] and item['enhanced_img'].exists():
                thumb_path = self._create_thumbnail(item['enhanced_img'], item['dir'])
                if thumb_path:
                    thumb_name = f"{item['enhanced_img'].stem}_thumb.jpg"
                    enhanced = f"![]({thumb_name})"
            
            # Restored images - show up to first 2 in separate columns
            if item['restored_imgs']:
                for i, restored in enumerate(item['restored_imgs'][:2]):
                    thumb_path = self._create_thumbnail(restored, item['dir'])
                    if thumb_path:
                        profile = restored.stem.split('_restored_')[-1] if '_restored_' in restored.stem else 'restored'
                        thumb_name = f"{restored.stem}_thumb.jpg"
                        img_html = f"![]({thumb_name})"
                        
                        if i == 0:
                            restored_1 = f"{img_html} **{profile.title()}**"
                        elif i == 1:
                            restored_2 = f"{img_html} **{profile.title()}**"
            
            lines.append(f"| {idx} | {item['name']} | {original} | {enhanced} | {restored_1} | {restored_2} |")
        
        lines.append("")
        
        return "\n".join(lines)

    def _create_thumbnail(self, image_path: Path, output_dir: Path, thumb_size: int = 150) -> Optional[Path]:
        """
        Create a thumbnail of the image for consistent gallery display
        
        Args:
            image_path: Path to original image
            output_dir: Directory to save thumbnail
            thumb_size: Size of thumbnail (width in pixels)
            
        Returns:
            Path to thumbnail file or None if creation failed
        """
        try:
            # Check if thumbnail already exists
            thumb_name = f"{image_path.stem}_thumb.jpg"
            thumb_path = output_dir / thumb_name
            
            if thumb_path.exists():
                return thumb_path
            
            # Create thumbnail
            img = Image.open(image_path)
            
            # Calculate height to maintain aspect ratio
            aspect_ratio = img.height / img.width
            thumb_height = int(thumb_size * aspect_ratio)
            
            # Resize
            img.thumbnail((thumb_size, thumb_height), Image.Resampling.LANCZOS)
            
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            
            # Save thumbnail
            img.save(thumb_path, quality=85)
            return thumb_path
            
        except Exception as e:
            print(f"Warning: Could not create thumbnail for {image_path}: {e}")
            return None

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
            
            # Extract and format fields - NO TRUNCATION
            objects = metadata.get('objects', metadata.get('objects_subjects', 'N/A'))
            if isinstance(objects, list):
                objects = ', '.join(str(o) for o in objects) if objects else 'N/A'
            objects = str(objects).replace('|', '\\|')
            
            # Format persons - handle list of dicts
            persons = metadata.get('persons', metadata.get('persons_count', 'N/A'))
            if isinstance(persons, list):
                # Extract descriptions from list of dicts
                descriptions = []
                for person in persons:
                    if isinstance(person, dict):
                        # Try common keys for descriptions
                        for key in ['description', 'Description', 'brief_description', 'person_1', 'person_2', 'person_3', 'person_4', 'details']:
                            if key in person:
                                descriptions.append(person[key])
                                break
                    else:
                        descriptions.append(str(person))
                persons = '; '.join(descriptions) if descriptions else 'N/A'
            persons = str(persons).replace('|', '\\|')
            
            weather = metadata.get('weather', metadata.get('weather_conditions', 'N/A'))
            weather = str(weather).replace('|', '\\|')
            
            # Check for mood/atmosphere with various field names
            mood = metadata.get('mood_atmosphere') or metadata.get('mood/atmosphere') or metadata.get('mood') or metadata.get('Mood/Atmosphere', 'N/A')
            # Handle mood if it's a dict/list structure
            if isinstance(mood, dict):
                mood = mood.get('description', mood.get('mood', str(mood)))
            elif isinstance(mood, list):
                if mood and isinstance(mood[0], dict):
                    mood = mood[0].get('description', mood[0].get('mood', str(mood[0])))
                else:
                    mood = mood[0] if mood else 'N/A'
            mood = str(mood).replace('|', '\\|')
            
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
            
            # Image thumbnails in side-by-side layout
            lines.append("")
            lines.append("### Images")
            lines.append("")
            
            # Original and Enhanced side by side
            has_analyzed = item['analyzed_img'] and item['analyzed_img'].exists()
            has_enhanced = item['enhanced_img'] and item['enhanced_img'].exists()
            
            if has_analyzed or has_enhanced:
                lines.append("| Original | Enhanced |")
                lines.append("|----------|----------|")
                
                analyzed_cell = ""
                enhanced_cell = ""
                
                if has_analyzed:
                    img_path = item['analyzed_img'].name
                    analyzed_cell = f"![Original]({img_path})"
                
                if has_enhanced:
                    img_path = item['enhanced_img'].name
                    enhanced_cell = f"![Enhanced]({img_path})"
                
                lines.append(f"| {analyzed_cell} | {enhanced_cell} |")
                lines.append("")
            
            # Restored images in table format
            if item['restored_imgs']:
                lines.append("")
                lines.append("### Restored Versions")
                lines.append("")
                
                # Create table with 2 columns of restored images
                restored_list = []
                for restored in item['restored_imgs']:
                    profile = restored.stem.split('_restored_')[-1] if '_restored_' in restored.stem else 'restored'
                    img_path = restored.name
                    restored_list.append((profile.title(), f"![{profile}]({img_path})"))
                
                lines.append("| Profile | Image |")
                lines.append("|---------|-------|")
                for profile_name, img_markdown in restored_list:
                    lines.append(f"| {profile_name} | {img_markdown} |")
                lines.append("")
            
            # Full metadata table
            lines.append("")
            lines.append("### Full Analysis")
            lines.append("")
            
            metadata = item['analysis'].get('metadata', {})
            lines.append("| Aspect | Details |")
            lines.append("|--------|---------|")
            
            # Map metadata to readable format - dynamically build based on what's available
            metadata_display = []
            
            # Add fields that are present in the data
            field_mapping = [
                ('objects', 'Objects'),
                ('objects_subjects', 'Objects & Subjects'),
                ('persons', 'Persons'),
                ('persons_count', 'Persons Count'),
                ('persons_position', 'Persons Position'),
                ('weather', 'Weather'),
                ('weather_conditions', 'Weather Conditions'),
                ('mood_atmosphere', 'Mood & Atmosphere'),
                ('mood/atmosphere', 'Mood & Atmosphere'),
                ('mood', 'Mood & Atmosphere'),
                ('Mood/Atmosphere', 'Mood & Atmosphere'),
                ('time_of_day', 'Time of Day'),
                ('season_date', 'Season & Date'),
                ('scene_type', 'Scene Type'),
                ('location_setting', 'Location & Setting'),
                ('activity', 'Activity'),
                ('photography_style', 'Photography Style'),
                ('composition_quality', 'Composition Quality'),
            ]
            
            # Build list with available fields
            seen_fields = set()
            for field_key, display_name in field_mapping:
                if field_key in metadata and display_name not in seen_fields:
                    metadata_display.append((display_name, metadata[field_key]))
                    seen_fields.add(display_name)
            
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
            
            # Enhancement recommendations with nice formatting
            enhancement = item['analysis'].get('enhancement', {})
            if enhancement:
                lines.append("")
                lines.append("### Enhancement Recommendations")
                lines.append("")
                
                for param, value in enhancement.items():
                    if param != 'summary' and param.lower() != 'raw_response':
                        lines.append(f"**{param.title().replace('_', ' ')}:**")
                        lines.append("")
                        
                        # Format value nicely based on type
                        if isinstance(value, dict):
                            # Format dict as key-value pairs
                            for key, val in value.items():
                                key_display = key.replace('_', ' ').title()
                                lines.append(f"- **{key_display}:** {val}")
                        elif isinstance(value, list):
                            # Format list as bullet points
                            for item_val in value:
                                if isinstance(item_val, dict):
                                    item_str = ', '.join(f"{k}: {v}" for k, v in item_val.items())
                                    lines.append(f"- {item_str}")
                                else:
                                    lines.append(f"- {item_val}")
                        else:
                            lines.append(str(value))
                        
                        lines.append("")
                
                if 'summary' in enhancement:
                    lines.append("")
                    lines.append(f"**Summary:** {enhancement['summary']}")
                    lines.append("")
            
            # Slide restoration profiles (if available)
            profiles = item['analysis'].get('slide_profiles', [])
            if profiles:
                lines.append("")
                lines.append("### Recommended Restoration Profiles")
                lines.append("")
                lines.append("| Profile | Confidence | Description |")
                lines.append("|---------|------------|-------------|")
                
                profile_descriptions = {
                    'faded': 'Very faded with lost color and contrast',
                    'color_cast': 'Generic color casts from aging',
                    'red_cast': 'Red/magenta color casts from aging',
                    'yellow_cast': 'Yellow/warm color casts from aging',
                    'aged': 'Moderately aged with some fading',
                    'well_preserved': 'Minimal aging',
                }
                
                for profile in profiles:
                    name = profile.get('profile', 'Unknown')
                    confidence = profile.get('confidence', 0)
                    # Handle both decimal (0.6) and percentage (60) formats
                    if confidence > 1:
                        conf = f"{confidence:.0f}%"
                    else:
                        conf = f"{confidence:.0%}"
                    # Use profile description if available, otherwise use generic description
                    description = profile_descriptions.get(name, 'Slide restoration profile')
                    lines.append(f"| {name.title()} | {conf} | {description} |")
                
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
