"""
Example usage of the Picture Analyzer
"""
import json
from picture_analyzer import PictureAnalyzer
from picture_enhancer import PictureEnhancer


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


def example_with_enhancement():
    """Example: Analyze image and then enhance it"""
    analyzer = PictureAnalyzer()
    enhancer = PictureEnhancer()
    
    # First, analyze the image
    analysis = analyzer.analyze_and_save('pictures/example.jpg')
    
    # Then enhance it (e.g., increase brightness and contrast)
    enhancer.adjust_brightness('output/example_analyzed.jpg', 1.1, 'output/example_bright.jpg')
    enhancer.adjust_contrast('output/example_bright.jpg', 1.2, 'output/example_enhanced.jpg')
    
    print("Enhancement complete!")


if __name__ == '__main__':
    print("Picture Analyzer Examples")
    print("=" * 50)
    print("")
    print("Note: Uncomment the example you want to run below:")
    print("")
    
    # Uncomment one of these to run:
    # example_single_analysis()
    # example_batch_analysis()
    # example_with_enhancement()
