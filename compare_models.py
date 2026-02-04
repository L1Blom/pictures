"""
Comparison script for gpt-4o vs gpt-4o-mini models
Tests both models on sample images and compares results, speed, and insights
"""
import json
import time
import base64
import os
from pathlib import Path
from typing import Dict, Any, List
from openai import OpenAI
from config import OPENAI_API_KEY, SUPPORTED_FORMATS, OUTPUT_DIR, METADATA_LANGUAGE
from prompts import ANALYSIS_PROMPT

class ModelComparator:
    """Compare different OpenAI vision models"""
    
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.models = ['gpt-4o', 'gpt-4o-mini']
        self.results = []
        
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def _analyze_with_model(self, image_path: str, model: str) -> Dict[str, Any]:
        """Analyze a single image with a specific model"""
        print(f"  Testing {model}...", end=" ", flush=True)
        start_time = time.time()
        
        image_data = self._encode_image(image_path)
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                max_tokens=2000,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an image analysis assistant. Respond with detailed analysis in JSON format."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": ANALYSIS_PROMPT
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}",
                                },
                            }
                        ],
                    }
                ],
            )
            
            elapsed = time.time() - start_time
            
            result = {
                'model': model,
                'status': 'success',
                'time': elapsed,
                'tokens': response.usage.total_tokens,
                'input_tokens': response.usage.prompt_tokens,
                'output_tokens': response.usage.completion_tokens,
                'response': response.choices[0].message.content
            }
            
            print(f"✓ ({elapsed:.2f}s, {response.usage.total_tokens} tokens)")
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"✗ Error: {str(e)}")
            return {
                'model': model,
                'status': 'error',
                'time': elapsed,
                'error': str(e)
            }
    
    def find_test_images(self, max_images: int = 3) -> List[str]:
        """Find test images in the pictures directory"""
        test_dirs = ['pictures', 'test_enhance', 'test_gps', 'test_gps_fresh']
        images = []
        
        for test_dir in test_dirs:
            if os.path.exists(test_dir):
                for file in Path(test_dir).glob('*'):
                    if file.suffix.lower() in SUPPORTED_FORMATS:
                        images.append(str(file))
                        if len(images) >= max_images:
                            return images
        
        return images[:max_images]
    
    def compare(self, image_paths: List[str] = None) -> None:
        """Run comparison on provided or found images"""
        if image_paths is None:
            image_paths = self.find_test_images(max_images=3)
        
        if not image_paths:
            print("No test images found. Please provide image paths or ensure test directories exist.")
            return
        
        print(f"\n{'='*70}")
        print(f"MODEL COMPARISON: gpt-4o vs gpt-4o-mini")
        print(f"{'='*70}\n")
        
        for idx, image_path in enumerate(image_paths, 1):
            if not os.path.exists(image_path):
                print(f"⚠ Skipping {image_path} (not found)")
                continue
            
            print(f"Image {idx}: {Path(image_path).name}")
            print("-" * 70)
            
            image_results = {}
            for model in self.models:
                result = self._analyze_with_model(image_path, model)
                image_results[model] = result
                self.results.append({
                    'image': image_path,
                    **result
                })
            
            # Compare results
            self._print_comparison(image_results)
            print()
    
    def _print_comparison(self, image_results: Dict[str, Dict]) -> None:
        """Print comparison summary for an image"""
        if not all(r.get('status') == 'success' for r in image_results.values()):
            return
        
        gpt4o = image_results['gpt-4o']
        mini = image_results['gpt-4o-mini']
        
        print("\n📊 COMPARISON:")
        print(f"  Speed:")
        print(f"    gpt-4o:      {gpt4o['time']:.2f}s")
        print(f"    gpt-4o-mini: {mini['time']:.2f}s")
        speed_diff = ((gpt4o['time'] - mini['time']) / gpt4o['time'] * 100)
        print(f"    → gpt-4o-mini is {abs(speed_diff):.1f}% {'faster' if speed_diff > 0 else 'slower'}")
        
        print(f"\n  Tokens Used:")
        print(f"    gpt-4o:      {gpt4o['tokens']} total ({gpt4o['input_tokens']} input, {gpt4o['output_tokens']} output)")
        print(f"    gpt-4o-mini: {mini['tokens']} total ({mini['input_tokens']} input, {mini['output_tokens']} output)")
        token_diff = ((gpt4o['tokens'] - mini['tokens']) / gpt4o['tokens'] * 100)
        print(f"    → gpt-4o-mini uses {abs(token_diff):.1f}% fewer tokens")
        
        print(f"\n  Response Quality:")
        gpt4o_len = len(gpt4o['response'])
        mini_len = len(mini['response'])
        print(f"    gpt-4o:      {gpt4o_len} characters")
        print(f"    gpt-4o-mini: {mini_len} characters")
        
        # Try to parse JSON responses if they contain JSON
        try:
            gpt4o_json = json.loads(gpt4o['response'])
            mini_json = json.loads(mini['response'])
            
            gpt4o_keys = set(gpt4o_json.keys())
            mini_keys = set(mini_json.keys())
            
            print(f"\n  Data Extraction (assuming JSON response):")
            print(f"    gpt-4o keys:      {sorted(gpt4o_keys)}")
            print(f"    gpt-4o-mini keys: {sorted(mini_keys)}")
            
            if gpt4o_keys == mini_keys:
                print(f"    → Both extract the same fields ✓")
            else:
                missing = mini_keys - gpt4o_keys
                extra = gpt4o_keys - mini_keys
                if missing:
                    print(f"    → gpt-4o-mini missing: {missing}")
                if extra:
                    print(f"    → gpt-4o has extra: {extra}")
        except:
            pass
    
    def print_summary(self) -> None:
        """Print overall summary"""
        if not self.results:
            return
        
        successful = [r for r in self.results if r['status'] == 'success']
        if not successful:
            return
        
        print(f"\n{'='*70}")
        print("OVERALL SUMMARY")
        print(f"{'='*70}\n")
        
        gpt4o_results = [r for r in successful if r['model'] == 'gpt-4o']
        mini_results = [r for r in successful if r['model'] == 'gpt-4o-mini']
        
        if gpt4o_results and mini_results:
            avg_time_4o = sum(r['time'] for r in gpt4o_results) / len(gpt4o_results)
            avg_time_mini = sum(r['time'] for r in mini_results) / len(mini_results)
            avg_tokens_4o = sum(r['tokens'] for r in gpt4o_results) / len(gpt4o_results)
            avg_tokens_mini = sum(r['tokens'] for r in mini_results) / len(mini_results)
            
            print("Performance Metrics (Average):")
            print(f"  gpt-4o:      {avg_time_4o:.2f}s per image, {avg_tokens_4o:.0f} tokens")
            print(f"  gpt-4o-mini: {avg_time_mini:.2f}s per image, {avg_tokens_mini:.0f} tokens")
            
            speed_gain = ((avg_time_4o - avg_time_mini) / avg_time_4o * 100)
            token_savings = ((avg_tokens_4o - avg_tokens_mini) / avg_tokens_4o * 100)
            
            print(f"\nCost Savings with gpt-4o-mini:")
            print(f"  Speed: {speed_gain:.1f}% faster" if speed_gain > 0 else f"  Speed: {abs(speed_gain):.1f}% slower")
            print(f"  Tokens: {token_savings:.1f}% fewer tokens")
            print(f"  Estimated cost: ~70% cheaper (official OpenAI rates)")
            
            print(f"\n✅ Recommendation:")
            if speed_gain > -20 and token_savings > 30:
                print(f"   Use gpt-4o-mini for this task - comparable quality with significant savings")
            elif speed_gain > 10:
                print(f"   Use gpt-4o if you need maximum quality/speed trade-off")
            else:
                print(f"   Either model works well - choose based on budget")

if __name__ == "__main__":
    comparator = ModelComparator()
    
    # Run comparison on found images
    comparator.compare()
    
    # Print summary
    comparator.print_summary()
    
    # Save detailed results
    results_file = os.path.join(OUTPUT_DIR, 'model_comparison_results.json')
    with open(results_file, 'w') as f:
        json.dump(comparator.results, f, indent=2)
    print(f"\n📁 Detailed results saved to: {results_file}")
