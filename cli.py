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
        description='Analyze pictures using OpenAI Vision API, generate EXIF metadata, enhance images, restore slides, and create reports'
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
    batch_parser.add_argument(
        '--enhance',
        action='store_true',
        help='Also enhance images based on analysis recommendations'
    )
    batch_parser.add_argument(
        '--restore-slide',
        type=str,
        nargs='?',
        const='auto',
        help='Also restore slides using profile (auto, faded, color_cast, red_cast, yellow_cast, aged, well_preserved)'
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
    
    # Generate report command
    report_parser = subparsers.add_parser('report', help='Generate markdown report from analysis results')
    report_parser.add_argument(
        'directory',
        type=str,
        help='Path to output directory containing analyzed images'
    )
    report_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output path for markdown report',
        default=None
    )
    
    # Generate gallery report command
    gallery_parser = subparsers.add_parser('gallery', help='Generate image gallery report showing all images in a table')
    gallery_parser.add_argument(
        'directory',
        type=str,
        help='Path to output directory containing analyzed images'
    )
    gallery_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output path for markdown gallery report',
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
        
        elif args.command == 'restore-slide':
            return cmd_restore_slide(args)
        
        elif args.command == 'report':
            return cmd_report(args)
        
        elif args.command == 'gallery':
            return cmd_gallery(args)
    
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
    """Batch analyze images in a directory, optionally enhance and restore"""
    if not Path(args.directory).is_dir():
        print(f"Error: Directory not found: {args.directory}")
        return 1
    
    analyzer = PictureAnalyzer()
    enhancer = SmartEnhancer() if args.enhance else None
    
    # Determine output directory
    output_dir = args.output or "output"
    Path(output_dir).mkdir(exist_ok=True)
    
    # Get all supported image files
    from config import SUPPORTED_FORMATS
    image_files = []
    for fmt in SUPPORTED_FORMATS:
        image_files.extend(Path(args.directory).glob(f"*{fmt}"))
        image_files.extend(Path(args.directory).glob(f"*{fmt.upper()}"))
    
    if not image_files:
        print(f"No supported images found in: {args.directory}")
        print(f"Supported formats: {', '.join(SUPPORTED_FORMATS)}")
        return 1
    
    image_files = sorted(set(image_files))  # Remove duplicates and sort
    total = len(image_files)
    
    print(f"Found {total} image(s) to process")
    if args.enhance:
        print("  + Enhancement enabled")
    if args.restore_slide:
        print(f"  + Slide restoration enabled ({args.restore_slide} profile)")
    print()
    
    success_count = 0
    for idx, image_path in enumerate(image_files, 1):
        image_stem = image_path.stem
        
        # When using restore-slide, put files directly in output dir
        # Otherwise, organize by subdirectories
        if args.restore_slide:
            analyzed_path = Path(output_dir) / f"{image_stem}_analyzed.jpg"
            enhanced_path = Path(output_dir) / f"{image_stem}_enhanced.jpg" if args.enhance else None
            restored_path = Path(output_dir) / f"{image_stem}_restored.jpg"
            analysis_json = Path(output_dir) / f"{image_stem}_analyzed.json"
        else:
            analysis_dir = Path(output_dir) / image_stem
            analysis_dir.mkdir(exist_ok=True)
            analyzed_path = analysis_dir / f"{image_stem}_analyzed.jpg"
            enhanced_path = analysis_dir / f"{image_stem}_enhanced.jpg" if args.enhance else None
            restored_path = None
            analysis_json = analysis_dir / f"{image_stem}_analyzed.json"
        
        print(f"[{idx}/{total}] Processing: {image_path.name}")
        
        try:
            # Step 1: Analyze
            analysis = analyzer.analyze_and_save(str(image_path), str(analyzed_path), save_json=True)
            
            # Step 2: Enhance (optional)
            enhanced_exists = False
            if args.enhance and 'enhancement' in analysis:
                result = enhancer.enhance_from_analysis(str(analyzed_path), analysis['enhancement'], str(enhanced_path))
                if result:
                    EXIFHandler.copy_exif(str(analyzed_path), str(enhanced_path), str(enhanced_path))
                    enhanced_exists = True
            
            # Step 3: Restore slide (optional)
            if args.restore_slide:
                restore_input = str(enhanced_path) if (args.enhance and enhanced_exists) else str(analyzed_path)
                
                # Determine which profile(s) to use
                profiles_to_process = []
                
                if args.restore_slide == 'auto':
                    # Check if analysis has slide profile recommendations
                    slide_profiles = analysis.get('slide_profiles', [])
                    if slide_profiles:
                        # Use all recommended profiles with confidence >= 50%
                        try:
                            profiles_to_process = [p['profile'] for p in slide_profiles if isinstance(p, dict) and 'profile' in p and p.get('confidence', 0) >= 50]
                        except (KeyError, TypeError) as e:
                            print(f"  Warning: Could not parse slide profiles: {e}")
                            profiles_to_process = []
                        if profiles_to_process:
                            print(f"  → Suggested profiles: {', '.join(profiles_to_process)}")
                    
                    # If no recommendations or all below 50%, fall back to auto-detect
                    if not profiles_to_process:
                        profiles_to_process = ['auto']
                else:
                    # User specified a profile
                    profiles_to_process = [args.restore_slide]
                
                # Process each profile
                for profile in profiles_to_process:
                    if len(profiles_to_process) > 1:
                        # Multiple profiles: add profile name to output
                        profile_restored_path = str(restored_path).replace('.jpg', f'_{profile}.jpg')
                    else:
                        profile_restored_path = str(restored_path)
                    
                    if profile == 'auto':
                        SlideRestoration.auto_restore_slide(
                            restore_input,
                            analysis,
                            profile_restored_path
                        )
                    else:
                        SlideRestoration.restore_slide(
                            restore_input,
                            profile=profile,
                            output_path=profile_restored_path
                        )
                    
                    if Path(profile_restored_path).exists():
                        EXIFHandler.copy_exif(str(analyzed_path), profile_restored_path, profile_restored_path)
            
            success_count += 1
            print(f"  ✓ Complete")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print(f"\n{'='*50}")
    print(f"Batch processing complete: {success_count}/{total} successful")
    print(f"Output directory: {output_dir}")
    
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
        
        # Determine which profile(s) to use
        profiles_to_process = []
        
        if args.restore_slide == 'auto':
            # Check if analysis has slide profile recommendations
            slide_profiles = analysis.get('slide_profiles', [])
            if slide_profiles:
                # Use all recommended profiles with confidence >= 50%
                try:
                    profiles_to_process = [p['profile'] for p in slide_profiles if isinstance(p, dict) and 'profile' in p and p.get('confidence', 0) >= 50]
                except (KeyError, TypeError) as e:
                    print(f"  Warning: Could not parse slide profiles: {e}")
                    profiles_to_process = []
                if profiles_to_process:
                    print(f"  → Suggested profiles: {', '.join(profiles_to_process)}")
            
            # If no recommendations or all below 50%, fall back to auto-detect
            if not profiles_to_process:
                profiles_to_process = ['auto']
        else:
            # User specified a profile
            profiles_to_process = [args.restore_slide]
        
        # Process each profile
        for profile in profiles_to_process:
            if len(profiles_to_process) > 1:
                # Multiple profiles: add profile name to output
                profile_restored_path = restored_path.replace('.jpg', f'_{profile}.jpg')
            else:
                profile_restored_path = restored_path
            
            if profile == 'auto':
                result = SlideRestoration.auto_restore_slide(
                    analyzed_path,  # Restore from analyzed image, not enhanced
                    analysis,
                    profile_restored_path
                )
            else:
                result = SlideRestoration.restore_slide(
                    analyzed_path,  # Restore from analyzed image, not enhanced
                    profile=profile,
                    output_path=profile_restored_path
                )
            
            if result:
                print(f"✓ Slide restoration complete ({profile}): {result}")
                # Copy EXIF to restored image
                EXIFHandler.copy_exif(analyzed_path, profile_restored_path, profile_restored_path)
            else:
                print(f"⚠ Slide restoration failed ({profile})")
    
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


def cmd_report(args):
    """Generate markdown report from analysis results"""
    from report_generator import ReportGenerator
    
    directory = Path(args.directory)
    
    if not directory.exists():
        print(f"✗ Directory not found: {directory}")
        return 1
    
    # Determine output path
    if args.output:
        report_path = Path(args.output)
    else:
        report_path = directory / "analysis_report.md"
    
    print(f"Generating report from: {directory}")
    print(f"Report will be saved to: {report_path}")
    print("")
    
    generator = ReportGenerator()
    generator.generate_report(directory, report_path)
    
    print(f"\n✓ Report generation complete: {report_path}")
    return 0


def cmd_gallery(args):
    """Generate gallery report showing all images in table format"""
    from report_generator import ReportGenerator
    
    directory = Path(args.directory)
    
    if not directory.exists():
        print(f"✗ Directory not found: {directory}")
        return 1
    
    # Determine output path
    if args.output:
        report_path = Path(args.output)
    else:
        report_path = directory / "gallery.md"
    
    print(f"Generating gallery report from: {directory}")
    print(f"Gallery report will be saved to: {report_path}")
    print("")
    
    generator = ReportGenerator()
    generator.generate_gallery_report(directory, report_path)
    
    print(f"\n✓ Gallery report generation complete: {report_path}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
