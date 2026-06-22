#!/usr/bin/env python3
"""
Demonstration script showing the image quality improvements in action.
This script shows how different quality settings affect image generation.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from content_pipeline.config import Settings
from content_pipeline.bots.image import VARIANTS


def demonstrate_quality_settings():
    """Demonstrate different quality settings and their effects."""
    print("=" * 70)
    print("Image Quality Improvements Demonstration")
    print("=" * 70)
    print()
    
    print("1. Default Settings (High Quality)")
    print("-" * 70)
    default_settings = Settings.from_environment()
    print(f"   Image Quality: {default_settings.image_quality}")
    print(f"   Image Seed: {default_settings.image_seed}")
    print(f"   Image Guidance Scale: {default_settings.image_guidance_scale}")
    print(f"   Image Num Inference Steps: {default_settings.image_num_inference_steps}")
    print(f"   Image Denoise Strength: {default_settings.image_denoise_strength}")
    print()
    
    print("2. Quality Level Comparison")
    print("-" * 70)
    
    quality_levels = ["low", "medium", "high"]
    
    for quality in quality_levels:
        print(f"\n   Quality Level: {quality.upper()}")
        print("   " + "-" * (70 - len(f"   Quality Level: {quality.upper()}")))
        
        # Create settings for this quality level
        settings = Settings(
            output_dir=Path("output"),
            image_quality=quality,
            image_seed=42,
            image_guidance_scale=7.5,
            image_num_inference_steps=20,
            image_denoise_strength=0.7,
        )
        
        # Show quality-specific effects
        if quality == "high":
            print(f"   - Uses higher inference steps for detail")
            print(f"   - Applies sharpening and contrast enhancement")
            print(f"   - Better for final output and presentations")
        elif quality == "medium":
            print(f"   - Uses balanced inference steps")
            print(f"   - Applies mild sharpening")
            print(f"   - Good for most use cases")
        else:  # low
            print(f"   - Uses lower inference steps for speed")
            print(f"   - Minimal enhancement")
            print(f"   - Best for rapid prototyping")
    
    print()
    print("3. Image Variant Support")
    print("-" * 70)
    
    for variant in VARIANTS:
        print(f"   {variant.aspect_ratio} ({variant.width}x{variant.height})")
        print(f"   - Filename: {variant.filename}")
        print(f"   - Compatible with all quality levels")
    
    print()
    print("4. Environment Variable Configuration")
    print("-" * 70)
    print("   To configure image quality, set these environment variables:")
    print()
    print("   IMAGE_QUALITY=high|medium|low")
    print("   IMAGE_SEED=0|42|123")
    print("   IMAGE_GUIDANCE_SCALE=7.5")
    print("   IMAGE_NUM_INFERENCE_STEPS=20")
    print("   IMAGE_DENOISE_STRENGTH=0.7")
    print()
    print("   Example .env configuration:")
    print("   IMAGE_QUALITY=high")
    print("   IMAGE_SEED=42")
    print("   IMAGE_GUIDANCE_SCALE=8.0")
    print("   IMAGE_NUM_INFERENCE_STEPS=30")
    print("   IMAGE_DENOISE_STRENGTH=0.8")
    
    print()
    print("=" * 70)
    print("Demonstration Complete")
    print("=" * 70)


if __name__ == "__main__":
    demonstrate_quality_settings()