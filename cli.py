#!/usr/bin/env python3
"""
CLI tool for analyzing and enhancing pictures

Commands:
  - analyze: Analyze single image (or batch with --batch flag)
  - process: Analyze, enhance, and optionally restore in one step
  - report: Generate markdown report from analysis results
  - gallery: Generate image gallery report
  
  (Legacy commands for backward compatibility: batch, enhance, restore-slide)
"""
import argparse
import sys
from cli_commands import (
    cmd_analyze, cmd_process, cmd_report, cmd_gallery,
    cmd_enhance, cmd_restore_slide, cmd_batch_impl
)


def main():
    """Main entry point for the CLI"""
    parser = argparse.ArgumentParser(
        description='Analyze pictures using OpenAI Vision API, generate EXIF metadata, enhance images, restore slides, and create reports'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # ========================================================================
    # CORE COMMANDS
    # ========================================================================
    
    # Analyze command (single or batch with --batch flag)
    analyze_parser = subparsers.add_parser('analyze', help='Analyze single image or batch directory')
    analyze_group = analyze_parser.add_mutually_exclusive_group(required=True)
    analyze_group.add_argument(
        'image',
        type=str,
        nargs='?',
        help='Path to the image file or directory (for batch)'
    )
    analyze_group.add_argument(
        '-d', '--directory',
        type=str,
        help='Batch mode: path to directory containing images'
    )
    analyze_parser.add_argument(
        '-b', '--batch',
        action='store_true',
        help='Enable batch mode (if using image argument for directory)'
    )
    analyze_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output directory for processed images',
        default=None
    )
    analyze_parser.add_argument(
        '--enhance',
        action='store_true',
        help='Also enhance images based on analysis recommendations'
    )
    analyze_parser.add_argument(
        '--restore-slide',
        type=str,
        nargs='?',
        const='auto',
        help='Also restore slides using profile (auto, faded, color_cast, red_cast, yellow_cast, aged, well_preserved)'
    )
    analyze_parser.add_argument(
        '--no-json',
        action='store_true',
        help='Do not save JSON analysis file'
    )
    
    # Process command (analyze + enhance + optional restore, all in one)
    process_parser = subparsers.add_parser(
        'process',
        help='Analyze, enhance, and optionally restore in one step'
    )
    process_parser.add_argument(
        'image',
        type=str,
        help='Path to the image file'
    )
    process_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output directory for processed images',
        default=None
    )
    process_parser.add_argument(
        '--restore-slide',
        type=str,
        nargs='?',
        const='auto',
        help='Also restore slide using profile (auto, faded, color_cast, red_cast, yellow_cast, aged, well_preserved)'
    )
    
    # Report command
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
    
    # Gallery command
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
    
    # ========================================================================
    # LEGACY COMMANDS (for backward compatibility)
    # ========================================================================
    
    # Batch command (legacy - use analyze --batch instead)
    batch_parser = subparsers.add_parser('batch', help='[LEGACY] Analyze multiple images in a directory')
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
    
    # Enhance command (legacy - use process instead)
    enhance_parser = subparsers.add_parser('enhance', help='[LEGACY] Enhance an image using AI recommendations')
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
    
    # Restore slide command (legacy - use process --restore-slide instead)
    slide_parser = subparsers.add_parser('restore-slide', help='[LEGACY] Restore a scanned old slide/dia positive')
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
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        if args.command == 'analyze':
            return cmd_analyze(args)
        elif args.command == 'process':
            return cmd_process(args)
        elif args.command == 'report':
            return cmd_report(args)
        elif args.command == 'gallery':
            return cmd_gallery(args)
        
        # Legacy commands
        elif args.command == 'batch':
            return cmd_batch_impl(args)
        elif args.command == 'enhance':
            return cmd_enhance(args)
        elif args.command == 'restore-slide':
            return cmd_restore_slide(args)
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1





if __name__ == '__main__':
    sys.exit(main())

