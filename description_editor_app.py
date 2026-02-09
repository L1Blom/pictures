"""Web app for editing directory-level description.txt files.

Provides a UI to:
- List all photo directories
- View thumbnails of images in each directory
- Edit and save description.txt for each directory
"""

from flask import Flask, jsonify, request, send_file, send_from_directory
from pathlib import Path
from PIL import Image
import io
import logging
from typing import List, Dict, Any
import json

logger = logging.getLogger(__name__)


class DescriptionEditor:
    """Backend for description.txt management."""
    
    TEMPLATE = """Albumnaam: 
Locatie: 
Datum: 
Personen: 
Activiteit: 
Weer: 
Opmerkingen: 
Stemming: """
    
    def __init__(self, photos_dir: str = "photos"):
        """Initialize editor with photos directory."""
        self.photos_dir = Path(photos_dir)
        if not self.photos_dir.exists():
            raise ValueError(f"Photos directory not found: {photos_dir}")
    
    def get_directories(self) -> List[Dict[str, Any]]:
        """Get all photo directories with metadata.
        
        Returns:
            List of directory info dicts
        """
        dirs = []
        for dir_path in sorted(self.photos_dir.iterdir()):
            if not dir_path.is_dir():
                continue
            
            # Count images
            images = list(dir_path.glob("*.JPG")) + list(dir_path.glob("*.jpg"))
            
            # Check if description.txt exists
            desc_file = dir_path / "description.txt"
            has_description = desc_file.exists()
            description = ""
            if has_description:
                description = desc_file.read_text().strip()
            
            dirs.append({
                'name': dir_path.name,
                'path': str(dir_path.relative_to(self.photos_dir)),
                'image_count': len(images),
                'has_description': has_description,
                'description_preview': description[:100] + "..." if len(description) > 100 else description,
            })
        
        return dirs
    
    def get_directory_details(self, dir_path: str) -> Dict[str, Any]:
        """Get details for a specific directory.
        
        Args:
            dir_path: Relative path to directory from photos_dir
        
        Returns:
            Directory details with images and description
        """
        full_path = self.photos_dir / dir_path
        if not full_path.exists() or not full_path.is_dir():
            raise ValueError(f"Directory not found: {dir_path}")
        
        # Get images
        images = sorted(
            list(full_path.glob("*.JPG")) + list(full_path.glob("*.jpg"))
        )
        
        # Get description
        desc_file = full_path / "description.txt"
        description = ""
        if desc_file.exists():
            description = desc_file.read_text().strip()
        else:
            description = self.TEMPLATE
        
        return {
            'directory': dir_path,
            'full_path': str(full_path),
            'description': description,
            'images': [
                {
                    'name': img.name,
                    'path': str(img.relative_to(self.photos_dir)),
                }
                for img in images  # Show all images
            ],
            'total_images': len(images),
        }
    
    def save_description(self, dir_path: str, description: str) -> bool:
        """Save description.txt for a directory.
        
        Args:
            dir_path: Relative path to directory
            description: Description text to save
        
        Returns:
            True if successful
        """
        full_path = self.photos_dir / dir_path
        desc_file = full_path / "description.txt"
        
        try:
            desc_file.write_text(description.strip())
            logger.info(f"Saved description to {desc_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save description: {e}")
            return False
    
    def get_thumbnail(self, image_path: str, size: int = 200) -> bytes:
        """Generate thumbnail for an image.
        
        Args:
            image_path: Relative path to image
            size: Thumbnail size in pixels
        
        Returns:
            PNG thumbnail bytes
        """
        full_path = self.photos_dir / image_path
        if not full_path.exists():
            raise ValueError(f"Image not found: {image_path}")
        
        try:
            img = Image.open(full_path)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            
            # Convert to PNG in memory
            img_io = io.BytesIO()
            img.save(img_io, 'PNG')
            img_io.seek(0)
            return img_io.getvalue()
        except Exception as e:
            logger.error(f"Failed to create thumbnail: {e}")
            raise


def create_app(photos_dir: str = "photos") -> Flask:
    """Create and configure Flask app.
    
    Args:
        photos_dir: Path to photos directory
    
    Returns:
        Configured Flask app
    """
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    static_dir = script_dir / 'static'
    
    app = Flask(__name__, static_folder=str(static_dir), static_url_path='/static')
    editor = DescriptionEditor(photos_dir)
    
    @app.route('/api/directories', methods=['GET'])
    def list_directories():
        """List all photo directories."""
        try:
            dirs = editor.get_directories()
            return jsonify({'success': True, 'directories': dirs})
        except Exception as e:
            logger.error(f"Error listing directories: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/directory/<path:dir_path>', methods=['GET'])
    def get_directory(dir_path):
        """Get details for a directory."""
        try:
            details = editor.get_directory_details(dir_path)
            return jsonify({'success': True, 'directory': details})
        except Exception as e:
            logger.error(f"Error getting directory details: {e}")
            return jsonify({'success': False, 'error': str(e)}), 404
    
    @app.route('/api/directory/<path:dir_path>', methods=['POST'])
    def save_directory(dir_path):
        """Save description for a directory."""
        try:
            data = request.get_json()
            description = data.get('description', '')
            
            success = editor.save_description(dir_path, description)
            return jsonify({'success': success})
        except Exception as e:
            logger.error(f"Error saving description: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/thumbnail/<path:image_path>', methods=['GET'])
    def get_thumbnail(image_path):
        """Get thumbnail for an image."""
        try:
            size = request.args.get('size', 200, type=int)
            thumbnail = editor.get_thumbnail(image_path, size)
            return send_file(
                io.BytesIO(thumbnail),
                mimetype='image/png',
                as_attachment=False,
            )
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            return jsonify({'success': False, 'error': str(e)}), 404
    
    @app.route('/')
    def index():
        """Serve main page."""
        return send_from_directory(app.static_folder, 'index.html')
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=7000)
