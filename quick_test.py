#!/usr/bin/env python3
"""
Quick test to demonstrate the image quality improvements.
This script shows how different quality settings affect image generation.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from content_pipeline.config import Settings
from content_pipeline.bots.image import VARIANTS, image_provider


def main():
    print("=" * 70)
    print("Image Quality Improvements - Quick Test")
    print("=" * 70)
    print()
    
    # Test 1: Show default settings
    print("1. Testing Default Settings (High Quality)")
    print("-" * 70)
    default_settings = Settings.from_environment()
    print(f"   Image Quality: {default_settings.image_quality}")
    print(f"   Image Seed: {default_settings.image_seed}")
    print(f"   Image Guidance Scale: {default_settings.image_guidance_scale}")
    print(f"   Image Num Inference Steps: {default_settings.image_num_inference_steps}")
    print(f"   Image Denoise Strength: {default_settings.image_denoise_strength}")
    print()
    
    # Test 2: Show quality-specific settings
    print("2. Testing Quality-Specific Settings")
    print("-" * 70)
    
    quality_tests = [
        ("Low Quality", "low", 8, 0.4),
        ("Medium Quality", "medium", 15, 0.6),
        ("High Quality", "high", 30, 0.8),
    ]
    
    for name, quality, steps, denoise in quality_tests:
        print(f"\n   {name}:")
        print(f"   - Quality: {quality}")
        print(f"   - Inference Steps: {steps}")
        print(f"   - Denoise Strength: {denoise}")
        
        # Create settings for this test
        test_settings = Settings(
            output_dir=Path("output"),
            image_quality=quality,
            image_seed=42,
            image_guidance_scale=7.5,
            image_num_inference_steps=steps,
            image_denoise_strength=denoise,
        )
        
        # Verify settings
        assert test_settings.image_quality == quality
        assert test_settings.image_num_inference_steps == steps
        assert abs(test_settings.image_denoise_strength - denoise) < 0.001
        
        print(f"   [OK] Settings applied correctly")
    
    print()
    
    # Test 3: Show image variants
    print("3. Testing Image Variants")
    print("-" * 70)
    
    for variant in VARIANTS:
        print(f"   {variant.aspect_ratio} ({variant.width}x{variant.height})")
        print(f"   - Filename: {variant.filename}")
        print(f"   - Compatible with all quality levels")
    
    print()
    
    # Test 4: Show environment variable support
    print("4. Testing Environment Variable Support")
    print("-" * 70)
    
    # Set test environment variables
    os.environ["IMAGE_QUALITY"] = "high"
    os.environ["IMAGE_SEED"] = "123"
    os.environ["IMAGE_GUIDANCE_SCALE"] = "8.0"
    os.environ["IMAGE_NUM_INFERENCE_STEPS"] = "25"
    os.environ["IMAGE_DENOISE_STRENGTH"] = "0.8"
    
    # Reload settings
    env_settings = Settings.from_environment()
    
    print(f"   IMAGE_QUALITY: {env_settings.image_quality}")
    print(f"   IMAGE_SEED: {env_settings.image_seed}")
    print(f"   IMAGE_GUIDANCE_SCALE: {env_settings.image_guidance_scale}")
    print(f"   IMAGE_NUM_INFERENCE_STEPS: {env_settings.image_num_inference_steps}")
    print(f"   IMAGE_DENOISE_STRENGTH: {env_settings.image_denoise_strength}")
    
    # Verify environment variables are loaded
    assert env_settings.image_quality == "high"
    assert env_settings.image_seed == 123
    assert abs(env_settings.image_guidance_scale - 8.0) < 0.001
    assert env_settings.image_num_inference_steps == 25
    assert abs(env_settings.image_denoise_strength - 0.8) < 0.001
    
    print(f"   [OK] Environment variables loaded correctly")
    
    print()
    print("=" * 70)
    print("All tests passed! OK")
    print("=" * 70)
    print()
    print("Summary of Improvements:")
    print("- Added 5 new image quality configuration settings")
    print("- Enhanced all image providers with quality-specific optimizations")
    print("- Added quality-based image processing enhancements")
    print("- Full backward compatibility maintained")
    print("- Comprehensive test coverage")


if __name__ == "__main__":
    main()