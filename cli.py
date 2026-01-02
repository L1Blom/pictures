#!/usr/bin/env python3
"""
CLI tool for analyzing and enhancing pictures
"""
import argparse
import json
import sys
import os
from pathlib import Path
from picture_analyzer import PictureAnalyzer
from picture_enhancer import SmartEnhancer


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
    
    # Enhance command (from analysis recommendations)
    enhance_parser = subparsers.add_parser('enhance', help='Enhance an image using AI recommendations')
    enhance_parser.add_argument(
        'image',
        type=str,
        help='Path to the image file'
    )
    enhance_parser.add_argument(
        '-a', '--analysis',
        type=str,
        help='Path to JSON analysis file (required if analysis not already done)',
        default=None
    )
    enhance_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output path for the enhanced image',
        default=None
    )
    
    # Analyze and enhance command (combined)
    analyze_enhance_parser = subparsers.add_parser(
        'process',
        help='Analyze and enhance an image in one step'
    )
    analyze_enhance_parser.add_argument(
        'image',
        type=str,
        help='Path to the image file'
    )
    analyze_enhance_parser.add_argument(
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
        if args.command == 'analyze':
            return cmd_analyze(args)
        
        elif args.command == 'batch':
            return cmd_batch(args)
        
        elif args.command == 'enhance':
            return cmd_enhance(args)
        
        elif args.command == 'process':
            return cmd_process(args)
    
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_analyze(args):
    """Analyze a single image"""
    if not Path(args.image).exists():
        print(f"Error: Image file not found: {args.image}")
        return 1
    
    analyzer = PictureAnalyzer()
    print(f"Analyzing: {args.image}")
    
    # Handle output path - if it's a directory, generate filename
    output_path = args.output
    if output_path and Path(output_path).is_dir():
        image_stem = Path(args.image).stem
        output_path = os.path.join(output_path, f"{image_stem}_analyzed.jpg")
    
    results = analyzer.analyze_and_save(
        args.image,
        output_path=output_path,
        save_json=not args.no_json
    )
    
    print("\nAnalysis Results:")
    print(json.dumps(results, indent=2))
    return 0


def cmd_batch(args):
    """Batch analyze images in a directory"""
    if not Path(args.directory).is_dir():
        print(f"Error: Directory not found: {args.directory}")
        return 1
    
    analyzer = PictureAnalyzer()
    print(f"Analyzing images in: {args.directory}")
    results = analyzer.batch_analyze(args.directory, args.output)
    
    return 0


def cmd_enhance(args):
    """Enhance an image using AI recommendations"""
    if not Path(args.image).exists():
        print(f"Error: Image file not found: {args.image}")
        return 1
    
    enhancer = SmartEnhancer()
    
    # Determine analysis path
    if args.analysis:
        analysis_path = args.analysis
    else:
        # Try to find analysis file next to image
        image_stem = Path(args.image).stem
        output_dir = Path(args.output).parent if args.output else Path(args.image).parent
        analysis_path = output_dir / f"{image_stem}_analyzed.json"
        
        if not Path(analysis_path).exists():
            print(f"Error: Analysis file not found. Please provide with -a or run 'analyze' first")
            print(f"Looked for: {analysis_path}")
            return 1
    
    if not Path(analysis_path).exists():
        print(f"Error: Analysis file not found: {analysis_path}")
        return 1
    
    # Determine output path
    if args.output is None:
        output_path = str(Path(args.image).parent / f"{Path(args.image).stem}_enhanced.jpg")
    else:
        output_path = args.output
    
    print(f"Enhancing: {args.image}")
    print(f"Using analysis: {analysis_path}")
    print(f"Output: {output_path}\n")
    
    result = enhancer.enhance_from_json(args.image, analysis_path, output_path)
    
    if result:
        print(f"✓ Image enhanced successfully: {result}")
        return 0
    else:
        print("✗ Enhancement failed")
        return 1


def cmd_process(args):
    """Analyze and enhance image in one step"""
    if not Path(args.image).exists():
        print(f"Error: Image file not found: {args.image}")
        return 1
    
    analyzer = PictureAnalyzer()
    enhancer = SmartEnhancer()
    
    # Determine output directory
    output_dir = args.output or "output"
    Path(output_dir).mkdir(exist_ok=True)
    
    image_stem = Path(args.image).stem
    analyzed_path = f"{output_dir}/{image_stem}_analyzed.jpg"
    enhanced_path = f"{output_dir}/{image_stem}_enhanced.jpg"
    analysis_json = f"{output_dir}/{image_stem}_analyzed.json"
    
    # Step 1: Analyze
    print(f"[1/2] Analyzing: {args.image}")
    analysis = analyzer.analyze_and_save(args.image, analyzed_path, save_json=True)
    print(f"✓ Analysis complete")
    
    # Step 2: Enhance
    print(f"\n[2/2] Enhancing based on recommendations")
    if 'enhancement' in analysis:
        result = enhancer.enhance_from_analysis(analyzed_path, analysis['enhancement'], enhanced_path)
        if result:
            print(f"✓ Enhancement complete: {result}")
        else:
            print("⚠ Enhancement failed, but analysis was saved")
    else:
        print("⚠ No enhancement data found in analysis")
    
    print(f"\nResults:")
    print(f"  Analyzed image: {analyzed_path}")
    print(f"  Enhanced image: {enhanced_path}")
    print(f"  Analysis JSON: {analysis_json}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
