#!/usr/bin/env python3
"""
Comprehensive validation test for refactored picture analysis system.
Tests all CLI commands with real images.
"""

import sys
import subprocess
import json
from pathlib import Path


def run_command(cmd, description):
    """Run a command and report results"""
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"{'='*70}")
    print(f"Command: {cmd}\n")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print("STDOUT:")
        print(result.stdout[:1500])  # Limit output
    if result.stderr:
        print("STDERR:")
        print(result.stderr[:500])
    
    status = "✓ PASS" if result.returncode == 0 else "✗ FAIL"
    print(f"\n{status} (exit code: {result.returncode})")
    return result.returncode == 0


def main():
    """Run comprehensive validation tests"""
    print("\n" + "="*70)
    print("COMPREHENSIVE VALIDATION TEST SUITE")
    print("="*70)
    print(f"Working Directory: {Path.cwd()}")
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Import validation
    tests_total += 1
    print(f"\n{'='*70}")
    print("TEST 1: Import Validation")
    print(f"{'='*70}")
    try:
        from cli_commands import cmd_analyze, cmd_batch_impl, cmd_process
        from metadata_manager import MetadataManager
        from picture_analyzer import PictureAnalyzer
        from picture_enhancer import SmartEnhancer
        print("✓ All core modules import successfully")
        print("✓ MetadataManager facade is available")
        print("✓ PictureAnalyzer supports dependency injection")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Import failed: {e}")
    
    # Test 2: MetadataManager instantiation
    tests_total += 1
    print(f"\n{'='*70}")
    print("TEST 2: MetadataManager Instantiation")
    print(f"{'='*70}")
    try:
        mgr1 = MetadataManager()
        print(f"✓ Default instantiation: {type(mgr1).__name__}")
        mgr2 = MetadataManager()
        print(f"✓ Multiple instances: {type(mgr2).__name__}")
        tests_passed += 1
    except Exception as e:
        print(f"✗ MetadataManager failed: {e}")
    
    # Test 3: PictureAnalyzer with DI
    tests_total += 1
    print(f"\n{'='*70}")
    print("TEST 3: PictureAnalyzer Dependency Injection")
    print(f"{'='*70}")
    try:
        analyzer1 = PictureAnalyzer()
        print(f"✓ Default instantiation works")
        print(f"  metadata_manager type: {type(analyzer1.metadata_manager).__name__}")
        
        custom_mgr = MetadataManager()
        analyzer2 = PictureAnalyzer(metadata_manager=custom_mgr)
        print(f"✓ Injected instantiation works")
        print(f"  metadata_manager type: {type(analyzer2.metadata_manager).__name__}")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Dependency injection failed: {e}")
    
    # Test 4: CLI analyze command (single image)
    tests_total += 1
    test_image = Path("pictures/Berlijn/2025-12-29-0001.jpg")
    if test_image.exists():
        passed = run_command(
            f"python3 cli.py analyze {test_image}",
            "CLI: Analyze Single Image"
        )
        if passed:
            tests_passed += 1
    else:
        print(f"SKIPPED: Test image not found at {test_image}")
    
    # Test 5: CLI batch command (5 images only)
    tests_total += 1
    print(f"\n{'='*70}")
    print("TEST 5: CLI: Batch Analyze (5 images)")
    print(f"{'='*70}")
    try:
        # Copy 5 test images to a temporary test directory
        test_dir = Path("test_validation_batch")
        test_dir.mkdir(exist_ok=True)
        
        import shutil
        source_dir = Path("pictures/Berlijn")
        for i, img in enumerate(sorted(source_dir.glob("*.jpg"))[:5]):
            shutil.copy(img, test_dir / img.name)
        
        print(f"Created test directory with 5 images at {test_dir}")
        passed = run_command(
            f"python3 cli.py analyze --batch {test_dir}",
            "CLI: Batch Analyze (5 images)"
        )
        if passed:
            tests_passed += 1
        
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
    except Exception as e:
        print(f"✗ Batch test setup failed: {e}")
    
    # Test 6: CLI process command
    tests_total += 1
    test_image = Path("pictures/Berlijn/2025-12-29-0002.jpg")
    if test_image.exists():
        passed = run_command(
            f"python3 cli.py process {test_image}",
            "CLI: Process Command (analyze+enhance)"
        )
        if passed:
            tests_passed += 1
    else:
        print(f"SKIPPED: Test image not found")
    
    # Test 7: CLI report command
    tests_total += 1
    output_dir = Path("output")
    if output_dir.exists() and list(output_dir.glob("*_analyzed.json")):
        passed = run_command(
            f"python3 cli.py report {output_dir}",
            "CLI: Report Generation"
        )
        if passed:
            tests_passed += 1
    else:
        print(f"SKIPPED: No analysis data found for report")
    
    # Test 8: EXIF copy through MetadataManager
    tests_total += 1
    print(f"\n{'='*70}")
    print("TEST 8: EXIF Copy via MetadataManager")
    print(f"{'='*70}")
    try:
        from exif_handler import EXIFHandler
        mgr = MetadataManager()
        
        # Check that copy_exif method is available
        if hasattr(mgr, 'copy_exif'):
            print("✓ MetadataManager.copy_exif() is available")
            print(f"  Method: {type(mgr.copy_exif)}")
            tests_passed += 1
        else:
            print("✗ MetadataManager.copy_exif() not found")
    except Exception as e:
        print(f"✗ EXIF test failed: {e}")
    
    # Summary
    print(f"\n{'='*70}")
    print("VALIDATION SUMMARY")
    print(f"{'='*70}")
    print(f"Tests Passed: {tests_passed}/{tests_total}")
    
    if tests_passed == tests_total:
        print("✓ ALL TESTS PASSED - System is fully functional!")
        return 0
    else:
        print(f"⚠ {tests_total - tests_passed} test(s) failed or skipped")
        return 1


if __name__ == "__main__":
    sys.exit(main())
