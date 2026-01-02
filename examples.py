"""
Example usage of the Picture Analyzer and Enhancer
"""
import json
from picture_analyzer import PictureAnalyzer
from picture_enhancer import PictureEnhancer, SmartEnhancer


def example_single_analysis():
    """Example: Analyze a single image"""
    analyzer = PictureAnalyzer()
    
    # Analyze and save with EXIF metadata
    results = analyzer.analyze_and_save(
        'pictures/example.jpg',
        output_path='output/example_analyzed.jpg'
    )
    
    print("Analysis Results:")
    print(json.dumps(results, indent=2))


def example_batch_analysis():
    """Example: Analyze all images in a directory"""
    analyzer = PictureAnalyzer()
    
    # Batch process all images in a directory
    results = analyzer.batch_analyze(
        directory='pictures/',
        output_directory='output/'
    )
    
    print(f"Processed {len(results)} images")


def example_smart_enhancement():
    """Example: Enhance image based on AI recommendations"""
    enhancer = SmartEnhancer()
    
    # Enhance using the analysis JSON file
    result = enhancer.enhance_from_json(
        'output/example_analyzed.jpg',
        'output/example_analyzed.json',
        'output/example_enhanced.jpg'
    )
    
    print(f"Enhanced image saved: {result}")


def example_full_workflow():
    """Example: Complete workflow - analyze and enhance in one go"""
    analyzer = PictureAnalyzer()
    enhancer = SmartEnhancer()
    
    # Step 1: Analyze the image
    print("Step 1: Analyzing image...")
    analysis = analyzer.analyze_and_save(
        'pictures/example.jpg',
        'output/example_analyzed.jpg'
    )
    
    # Step 2: Enhance based on recommendations
    print("\nStep 2: Enhancing image...")
    if 'enhancement' in analysis:
        enhanced_path = enhancer.enhance_from_analysis(
            'output/example_analyzed.jpg',
            analysis['enhancement'],
            'output/example_enhanced.jpg'
        )
        
        if enhanced_path:
            print(f"✓ Complete workflow finished!")
            print(f"  Analyzed: output/example_analyzed.jpg")
            print(f"  Enhanced: {enhanced_path}")
        else:
            print("⚠ Enhancement failed")
    else:
        print("⚠ No enhancement data available")


def example_manual_enhancement():
    """Example: Manual enhancement with specific adjustments"""
    enhancer = PictureEnhancer()
    
    # Apply specific enhancements
    image_path = 'pictures/example.jpg'
    
    # Increase brightness
    image_path = enhancer.adjust_brightness(
        image_path, 1.1, 'output/step1_brighter.jpg'
    )
    
    # Increase contrast
    image_path = enhancer.adjust_contrast(
        image_path, 1.2, 'output/step2_contrast.jpg'
    )
    
    # Increase saturation
    image_path = enhancer.adjust_saturation(
        image_path, 1.15, 'output/step3_saturated.jpg'
    )
    
    print("Manual enhancement complete!")


if __name__ == '__main__':
    print("Picture Analyzer & Enhancer Examples")
    print("=" * 50)
    print("")
    print("Available examples:")
    print("  - example_single_analysis()     : Analyze one image")
    print("  - example_batch_analysis()      : Analyze multiple images")
    print("  - example_smart_enhancement()   : Enhance with AI recommendations")
    print("  - example_full_workflow()       : Analyze and enhance in one step")
    print("  - example_manual_enhancement()  : Manual step-by-step enhancement")
    print("")
    print("Or use the CLI commands:")
    print("  python cli.py analyze <image>")
    print("  python cli.py batch <directory>")
    print("  python cli.py enhance <image> -a <analysis.json>")
    print("  python cli.py process <image>")
    print("")
    
    # Uncomment one of these to run:
    # example_single_analysis()
    # example_batch_analysis()
    # example_smart_enhancement()
    # example_full_workflow()
    # example_manual_enhancement()
