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
from slide_restoration import SlideRestoration
from exif_handler import EXIFHandler


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
        # Slide restoration command
    slide_parser = subparsers.add_parser('restore-slide', help='Restore a scanned old slide/dia positive')
    slide_parser.add_argument(
        'image',
        type=str,
        help='Path to the scanned slide image'
    )
    slide_parser.add_argument(
        '-p', '--profile',
        type=str,
        choices=['faded', 'color_cast', 'red_cast', 'yellow_cast', 'aged', 'well_preserved', 'auto'],
        default='auto',
        help='Restoration profile (auto=auto-detect from analysis)'
    )
    slide_parser.add_argument(
        '-a', '--analysis',
        type=str,
        help='Path to JSON analysis file (required for auto profile)',
        default=None
    )
    slide_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output path for restored slide',
        default=None
    )
    slide_parser.add_argument(
        '--no-denoise',
        action='store_true',
        help='Skip noise reduction'
    )
    slide_parser.add_argument(
        '--no-despeckle',
        action='store_true',
        help='Skip dust/speckle removal'
    )
    
    # Analyze and enhance command (combined)
    analyze_enhance_parser = subparsers.add_parser(
        'process',
        help='Analyze and enhance an image in one step (optionally restore slide)'
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
    analyze_enhance_parser.add_argument(
        '--restore-slide',
        type=str,
        nargs='?',
        const='auto',
        help='Also restore slide using profile (auto, faded, color_cast, red_cast, yellow_cast, aged, well_preserved). Use --restore-slide alone for auto-detection'
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
        
        elif args.command == 'restore-slide':
            return cmd_restore_slide(args)
    
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
    """Analyze and enhance image in one step, optionally restore slide"""
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
    restored_path = f"{output_dir}/{image_stem}_restored.jpg" if args.restore_slide else None
    
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
            # Copy EXIF to enhanced image
            EXIFHandler.copy_exif(analyzed_path, enhanced_path, enhanced_path)
        else:
            print("⚠ Enhancement failed, but analysis was saved")
    else:
        print("⚠ No enhancement data found in analysis")
    
    # Step 3: Optionally restore slide
    if args.restore_slide:
        step_num = 3
        print(f"\n[{step_num}/3] Restoring slide")
        
        if args.restore_slide == 'auto':
            # Auto-detect profile from analysis
            result = SlideRestoration.auto_restore_slide(
                analyzed_path,  # Restore from analyzed image, not enhanced
                analysis,
                restored_path
            )
        else:
            # Use specified profile
            result = SlideRestoration.restore_slide(
                analyzed_path,  # Restore from analyzed image, not enhanced
                profile=args.restore_slide,
                output_path=restored_path
            )
        
        if result:
            print(f"✓ Slide restoration complete: {result}")
            # Copy EXIF to restored image
            EXIFHandler.copy_exif(analyzed_path, restored_path, restored_path)
        else:
            print("⚠ Slide restoration failed")
    
    print(f"\nResults:")
    print(f"  Analyzed image: {analyzed_path}")
    print(f"  Enhanced image: {enhanced_path}")
    if restored_path:
        print(f"  Restored image: {restored_path}")
    print(f"  Analysis JSON: {analysis_json}")
    
    return 0


def cmd_restore_slide(args):
    """Restore a scanned old slide using specialized profiles"""
    if not Path(args.image).exists():
        print(f"Error: Image file not found: {args.image}")
        return 1
    
    # Determine output path
    if args.output is None:
        output_path = str(Path(args.image).parent / f"{Path(args.image).stem}_restored.jpg")
    else:
        output_path = args.output if args.output.endswith(('.jpg', '.jpeg')) else f"{args.output}_restored.jpg"
    
    # Handle auto profile
    if args.profile == 'auto':
        # Need to analyze first
        if not args.analysis:
            # Try to find analysis file
            image_stem = Path(args.image).stem
            analysis_path = str(Path(args.image).parent / f"{image_stem}_analyzed.json")
            if not Path(analysis_path).exists():
                print("Error: Auto profile requires analysis. Please either:")
                print("  1. Provide -a/--analysis path, or")
                print("  2. Run 'analyze' command first, or")
                print("  3. Specify a profile (--profile faded/color_cast/aged/well_preserved)")
                return 1
        else:
            analysis_path = args.analysis
        
        if not Path(analysis_path).exists():
            print(f"Error: Analysis file not found: {analysis_path}")
            return 1
        
        # Load analysis and auto-detect profile
        with open(analysis_path, 'r') as f:
            analysis = json.load(f)
        
        result = SlideRestoration.auto_restore_slide(
            args.image,
            analysis,
            output_path
        )
    else:
        # Use specified profile
        print(f"Restoring slide with '{args.profile}' profile: {args.image}")
        result = SlideRestoration.restore_slide(
            args.image,
            profile=args.profile,
            output_path=output_path,
            denoise=not args.no_denoise,
            despeckle=not args.no_despeckle
        )
    
    if result:
        print(f"\n✓ Slide restoration complete: {result}")
        return 0
    else:
        print("✗ Slide restoration failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
