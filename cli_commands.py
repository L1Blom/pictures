"""
CLI command handlers for picture analysis and enhancement

Provides individual command implementations:
- cmd_analyze: Analyze single/batch images (uses new pipeline)
- cmd_process: Analyze, enhance, and optionally restore
- cmd_report: Generate analysis report
- cmd_gallery: Generate image gallery
- cmd_restore_slide: Restore old slides (legacy support)
- cmd_enhance: Enhance image from analysis (legacy support)
"""

import json
import sys
from pathlib import Path
from picture_enhancer import SmartEnhancer
from slide_restoration import SlideRestoration
from metadata_manager import MetadataManager
from report_generator import ReportGenerator
from config import SUPPORTED_FORMATS

# Import new pipeline-based analyzer
sys.path.insert(0, str(Path(__file__).parent / "src"))
from picture_analyzer.cli.app import (
    _single_analyze as _src_single_analyze,
    _batch_analyze as _src_batch_analyze,
)


def cmd_analyze(args):
    """Analyze a single or batch of images using the new pipeline"""
    # Determine if single or batch based on args
    if hasattr(args, 'batch') and args.batch:
        # Batch mode
        return cmd_batch_impl(args)
    else:
        # Single image mode
        return cmd_analyze_single(args)


def cmd_analyze_single(args):
    """Analyze a single image using the new pipeline"""
    if not Path(args.image).exists():
        print(f"Error: Image file not found: {args.image}")
        return 1
    
    print(f"Analyzing: {args.image}")
    
    try:
        _src_single_analyze(
            image_path=Path(args.image),
            output=args.output if hasattr(args, 'output') else None,
            do_enhance=getattr(args, 'enhance', False),
            restore_slide=getattr(args, 'restore_slide', None),
            no_json=getattr(args, 'no_json', False),
            provider=None,
            pipeline_mode=None,
        )
        return 0
    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        return 1


def cmd_batch_impl(args):
    """Batch analyze images in a directory using new pipeline, optionally enhance and restore"""
    directory = args.image if hasattr(args, 'image') else args.directory
    
    if not Path(directory).is_dir():
        print(f"Error: Directory not found: {directory}")
        return 1
    
    print(f"\nBatch Processing: {directory}")
    if getattr(args, 'enhance', False):
        print("  + Enhancement enabled")
    if getattr(args, 'restore_slide', None):
        print(f"  + Slide restoration enabled ({args.restore_slide} profile)")
    print()
    
    try:
        _src_batch_analyze(
            directory=Path(directory),
            output=args.output if hasattr(args, 'output') else None,
            do_enhance=getattr(args, 'enhance', False),
            restore_slide=getattr(args, 'restore_slide', None),
            provider=None,
            pipeline_mode=None,
            skip_existing=False,
        )
        return 0
    except Exception as e:
        print(f"Error during batch processing: {e}", file=sys.stderr)
        return 1


def cmd_process(args):
    """Analyze, enhance and optionally restore slide in one step using new pipeline"""
    if not Path(args.image).exists():
        print(f"Error: Image file not found: {args.image}")
        return 1
    
    print(f"Processing: {args.image}")
    if getattr(args, 'enhance', False):
        print("  + Enhancement enabled")
    if getattr(args, 'restore_slide', None):
        print(f"  + Slide restoration enabled")
    
    try:
        _src_single_analyze(
            image_path=Path(args.image),
            output=args.output if hasattr(args, 'output') else None,
            do_enhance=True,  # Always enhance in process command
            restore_slide=getattr(args, 'restore_slide', None),
            no_json=False,
            provider=None,
            pipeline_mode=None,
        )
        return 0
    except Exception as e:
        print(f"Error during processing: {e}", file=sys.stderr)
        return 1


def cmd_enhance(args):
    """Enhance an image using AI recommendations (legacy command)"""
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


def cmd_restore_slide(args):
    """Restore a scanned old slide using specialized profiles (legacy command)"""
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
