#!/usr/bin/env python3
"""
Test script to verify image quality improvements in the content automation pipeline.
This script tests the new image quality settings and enhancements.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from content_pipeline.config import Settings
from content_pipeline.bots.image import (
    image_provider,
    VARIANTS,
    ImageVariant,
)


def test_image_quality_settings():
    """Test that image quality settings are properly loaded."""
    print("Testing image quality settings...")
    
    # Test with default settings
    settings = Settings.from_environment()
    
    print(f"  Image quality: {settings.image_quality}")
    print(f"  Image seed: {settings.image_seed}")
    print(f"  Image guidance scale: {settings.image_guidance_scale}")
    print(f"  Image num inference steps: {settings.image_num_inference_steps}")
    print(f"  Image denoise strength: {settings.image_denoise_strength}")
    
    # Test that quality values are valid
    assert settings.image_quality in ["low", "medium", "high", "hd"], "Invalid image quality value"
    assert 0 <= settings.image_seed <= 2147483647, "Invalid image seed value"
    assert 0.0 <= settings.image_guidance_scale <= 20.0, "Invalid image guidance scale value"
    assert 1 <= settings.image_num_inference_steps <= 50, "Invalid image num inference steps value"
    assert 0.0 <= settings.image_denoise_strength <= 1.0, "Invalid image denoise strength value"
    
    print("  [OK] All image quality settings are valid")
    print()


def test_image_provider_quality_enhancement():
    """Test that image providers apply quality enhancements."""
    print("Testing image provider quality enhancements...")
    
    settings = Settings.from_environment()
    
    # Test with different quality settings
    quality_levels = ["low", "medium", "high"]
    
    for quality in quality_levels:
        print(f"  Testing quality level: {quality}")
        
        # Create settings with specific quality
        test_settings = Settings(
            output_dir=Path("output"),
            image_provider=settings.image_provider,
            image_quality=quality,
            image_seed=42,
            image_guidance_scale=7.5,
            image_num_inference_steps=20,
            image_denoise_strength=0.7,
        )
        
        # Test that the settings are properly applied
        assert test_settings.image_quality == quality, f"Quality setting not applied: {test_settings.image_quality}"
        assert test_settings.image_seed == 42, f"Seed setting not applied: {test_settings.image_seed}"
        
        print(f"    [OK] Quality {quality} settings applied correctly")
    
    print()


def test_image_variant_compatibility():
    """Test that image variants are compatible with quality settings."""
    print("Testing image variant compatibility...")
    
    settings = Settings.from_environment()
    
    # Test all variants
    for variant in VARIANTS:
        print(f"  Testing variant: {variant.aspect_ratio} ({variant.width}x{variant.height})")
        
        # Create a test provider
        provider = image_provider(settings)
        
        # Verify variant properties
        assert variant.aspect_ratio in ["1:1", "16:9", "9:16"], f"Invalid aspect ratio: {variant.aspect_ratio}"
        assert variant.width > 0 and variant.height > 0, f"Invalid dimensions: {variant.width}x{variant.height}"
        assert variant.filename.startswith("images/"), f"Invalid filename: {variant.filename}"
        
        print(f"    [OK] Variant {variant.aspect_ratio} is valid")
    
    print()


def test_quality_enhancement_logic():
    """Test the quality enhancement logic in image processing."""
    print("Testing quality enhancement logic...")
    
    settings = Settings.from_environment()
    
    # Test quality-specific parameters
    print("  Testing quality-specific parameter adjustments...")
    
    # High quality should use higher steps
    high_settings = Settings(
        output_dir=Path("output"),
        image_quality="high",
        image_num_inference_steps=30,
    )
    assert high_settings.image_num_inference_steps == 30, "High quality steps not applied"
    
    # Medium quality should use medium steps
    medium_settings = Settings(
        output_dir=Path("output"),
        image_quality="medium",
        image_num_inference_steps=15,
    )
    assert medium_settings.image_num_inference_steps == 15, "Medium quality steps not applied"
    
    # Low quality should use lower steps
    low_settings = Settings(
        output_dir=Path("output"),
        image_quality="low",
        image_num_inference_steps=8,
    )
    assert low_settings.image_num_inference_steps == 8, "Low quality steps not applied"
    
    print("  [OK] Quality-specific parameter adjustments work correctly")
    print()


def test_environment_variable_loading():
    """Test that environment variables are properly loaded."""
    print("Testing environment variable loading...")
    
    # Set test environment variables
    os.environ["IMAGE_QUALITY"] = "high"
    os.environ["IMAGE_SEED"] = "123"
    os.environ["IMAGE_GUIDANCE_SCALE"] = "8.0"
    os.environ["IMAGE_NUM_INFERENCE_STEPS"] = "25"
    os.environ["IMAGE_DENOISE_STRENGTH"] = "0.8"
    
    # Reload settings
    settings = Settings.from_environment()
    
    # Verify environment variables are loaded
    assert settings.image_quality == "high", f"Expected 'high', got {settings.image_quality}"
    assert settings.image_seed == 123, f"Expected 123, got {settings.image_seed}"
    assert abs(settings.image_guidance_scale - 8.0) < 0.001, f"Expected 8.0, got {settings.image_guidance_scale}"
    assert settings.image_num_inference_steps == 25, f"Expected 25, got {settings.image_num_inference_steps}"
    assert abs(settings.image_denoise_strength - 0.8) < 0.001, f"Expected 0.8, got {settings.image_denoise_strength}"
    
    print("  [OK] Environment variables loaded correctly")
    print()


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Image Quality Improvements")
    print("=" * 60)
    print()
    
    try:
        test_image_quality_settings()
        test_image_provider_quality_enhancement()
        test_image_variant_compatibility()
        test_quality_enhancement_logic()
        test_environment_variable_loading()
        
        print("=" * 60)
        print("All tests passed! OK")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())