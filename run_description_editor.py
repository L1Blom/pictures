#!/usr/bin/env python3
"""Launch the description editor web app."""

import sys
import os
from pathlib import Path

from description_editor_app import create_app

if __name__ == '__main__':
    # Change to project root if needed
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Get photos directory from command line or use default
    if len(sys.argv) > 1:
        photos_dir = sys.argv[1]
    else:
        photos_dir = 'photos'
    
    # Validate directory exists
    photos_path = Path(photos_dir)
    if not photos_path.exists():
        print(f"\n❌ Error: Directory not found: {photos_dir}")
        print(f"   Usage: python3 run_description_editor.py [photos_directory]")
        sys.exit(1)
    
    print("\n" + "="*70)
    print("📷 Photo Description Editor")
    print("="*70)
    print(f"\n📂 Using directory: {photos_dir}")
    print("\n🌐 Starting web server...\n")
    print("   Open your browser and go to: http://localhost:7000")
    print("\n" + "="*70 + "\n")
    
    app = create_app(photos_dir=photos_dir)
    app.run(debug=True, port=7000, use_reloader=True)
