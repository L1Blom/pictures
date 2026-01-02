#!/usr/bin/env python3
"""
CLI tool for analyzing and enhancing pictures
"""
import argparse
import json
import sys
from pathlib import Path
from picture_analyzer import PictureAnalyzer


def main():
    """Main entry point for the CLI"""
    parser = argparse.ArgumentParser(
        description='Analyze pictures using OpenAI Vision API and generate EXIF metadata'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Analyze single image command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze a single image')
    analyze_parser.add_argument(
        'image',
        type=str,
        help='Path to the image file'
    )
    analyze_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output path for the processed image',
        default=None
    )
    analyze_parser.add_argument(
        '--no-json',
        action='store_true',
        help='Do not save JSON analysis file'
    )
    
    # Batch analyze command
    batch_parser = subparsers.add_parser('batch', help='Analyze multiple images in a directory')
    batch_parser.add_argument(
        'directory',
        type=str,
        help='Path to directory containing images'
    )
    batch_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output directory for processed images',
        default=None
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        analyzer = PictureAnalyzer()
        
        if args.command == 'analyze':
            if not Path(args.image).exists():
                print(f"Error: Image file not found: {args.image}")
                return 1
            
            print(f"Analyzing: {args.image}")
            results = analyzer.analyze_and_save(
                args.image,
                output_path=args.output,
                save_json=not args.no_json
            )
            
            print("\nAnalysis Results:")
            print(json.dumps(results, indent=2))
            return 0
        
        elif args.command == 'batch':
            if not Path(args.directory).is_dir():
                print(f"Error: Directory not found: {args.directory}")
                return 1
            
            print(f"Analyzing images in: {args.directory}")
            results = analyzer.batch_analyze(args.directory, args.output)
            
            return 0
    
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
