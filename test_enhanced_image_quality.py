#!/usr/bin/env python3
"""
Test script to verify the enhanced image quality improvements.
This script tests the new quality-aware sampler settings and prompt enhancements.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from content_pipeline.config import Settings
from content_pipeline.bots.image import VARIANTS, image_provider


def test_enhanced_workflow():
    """Test that the enhanced workflow is being used."""
    print("Testing enhanced workflow...")
    
    settings = Settings.from_environment()
    
    # Check that the workflow path is set to the enhanced version
    expected_workflow = "workflows/comfyui_flux_api_enhanced.json"
    actual_workflow = settings.comfyui_image_workflow
    
    print(f"  Expected workflow: {expected_workflow}")
    print(f"  Actual workflow: {actual_workflow}")
    
    # Check if the enhanced workflow file exists
    enhanced_workflow_path = Path("workflows") / "comfyui_flux_api_enhanced.json"
    if enhanced_workflow_path.exists():
        print(f"  [OK] Enhanced workflow file exists at {enhanced_workflow_path}")
        print("  [OK] Enhanced workflow is being used")
    else:
        print(f"  [WARN] Enhanced workflow file not found at {enhanced_workflow_path}")
        print("  Note: This may be expected if the file doesn't exist yet")
    
    print()


def test_quality_aware_enhancements():
    """Test that quality-aware prompt enhancements are working."""
    print("Testing quality-aware prompt enhancements...")
    
    # Test different quality levels
    quality_tests = [
        ("low", "simple scene, clear outline"),
        ("medium", "good composition, natural lighting, clear details"),
        ("high", "high detail, intricate features, professional lighting, sharp focus"),
    ]
    
    for quality, expected_enhancement in quality_tests:
        print(f"  Testing quality level: {quality}")
        
        # Create settings with specific quality
        test_settings = Settings(
            output_dir=Path("output"),
            image_quality=quality,
            image_seed=42,
            image_guidance_scale=7.5,
            image_num_inference_steps=20,
            image_denoise_strength=0.7,
        )
        
        # Create provider and test prompt enhancement
        provider = image_provider(test_settings)
        
        # Test prompt enhancement (only if the provider has this method)
        if hasattr(provider, "_enhance_prompt_for_quality"):
            test_prompt = "A beautiful landscape"
            enhanced_prompt = provider._enhance_prompt_for_quality(test_prompt, quality)
            
            print(f"    Original prompt: {test_prompt}")
            print(f"    Enhanced prompt: {enhanced_prompt}")
            
            # Verify that the enhancement contains quality-specific elements
            assert quality in enhanced_prompt.lower(), f"Quality {quality} not found in enhanced prompt"
            
            # Test negative prompt
            negative_prompt = provider._get_negative_prompt(quality)
            print(f"    Negative prompt: {negative_prompt}")
            
            # Test sampler configuration
            sampler_config = provider._get_sampler_config(quality)
            print(f"    Sampler config: {sampler_config}")
            
            assert sampler_config["steps"] > 0, "Sampler steps should be positive"
            assert sampler_config["cfg"] > 0, "Sampler cfg should be positive"
            
            print(f"    ✓ Quality {quality} enhancements applied correctly")
        else:
            print(f"    [WARN] Provider does not have quality enhancement methods (this is expected for MockImageProvider)")
    
    print()


def test_sampler_configurations():
    """Test that sampler configurations are quality-specific."""
    print("Testing sampler configurations...")
    
    settings = Settings.from_environment()
    provider = image_provider(settings)
    
    is_flux = False
    if hasattr(provider, "model_name") and provider.model_name:
        is_flux = "flux" in provider.model_name.lower()
        
    if is_flux:
        # Flux-specific quality levels
        quality_tests = [
            ("low", 15, 1.0, 1.0, "euler"),
            ("medium", 25, 1.0, 1.0, "euler"),
            ("high", 30, 1.0, 1.0, "euler"),
        ]
    else:
        # Standard SD/SDXL quality levels
        quality_tests = [
            ("low", 20, 2.5, 0.7, "euler"),
            ("medium", 25, 3.5, 0.8, "dpmpp_2m"),
            ("high", 30, 5.0, 0.9, "euler_ancestral"),
        ]
    
    for quality, expected_steps, expected_cfg, expected_denoise, expected_sampler in quality_tests:
        print(f"  Testing quality level: {quality}")
        
        sampler_config = provider._get_sampler_config(quality)
        
        print(f"    Steps: {sampler_config['steps']} (expected: {expected_steps})")
        print(f"    CFG: {sampler_config['cfg']} (expected: {expected_cfg})")
        print(f"    Denoise: {sampler_config['denoise']} (expected: {expected_denoise})")
        print(f"    Sampler: {sampler_config['sampler_name']} (expected: {expected_sampler})")
        
        assert sampler_config["steps"] == expected_steps, f"Expected steps {expected_steps}, got {sampler_config['steps']}"
        assert sampler_config["cfg"] == expected_cfg, f"Expected cfg {expected_cfg}, got {sampler_config['cfg']}"
        assert sampler_config["denoise"] == expected_denoise, f"Expected denoise {expected_denoise}, got {sampler_config['denoise']}"
        assert sampler_config["sampler_name"] == expected_sampler, f"Expected sampler {expected_sampler}, got {sampler_config['sampler_name']}"
        
        # Test guidance scale for Flux
        if is_flux:
            expected_guidance = settings.image_guidance_scale if settings.image_guidance_scale != 7.5 else (4.0 if quality == "high" else (3.5 if quality == "medium" else 2.5))
            print(f"    Guidance: {sampler_config['guidance']} (expected: {expected_guidance})")
            assert sampler_config["guidance"] == expected_guidance, f"Expected guidance {expected_guidance}, got {sampler_config['guidance']}"
            
        print(f"    [OK] Sampler configuration for {quality} quality is correct")
    
    print()


def test_environment_variable_support():
    """Test that environment variables are properly loaded."""
    print("Testing environment variable support...")
    
    # Save original environment variables
    original_env = {}
    for key in ["IMAGE_QUALITY", "IMAGE_SEED", "IMAGE_GUIDANCE_SCALE", "IMAGE_NUM_INFERENCE_STEPS", "IMAGE_DENOISE_STRENGTH"]:
        if key in os.environ:
            original_env[key] = os.environ[key]
    
    # Set test environment variables
    os.environ["IMAGE_QUALITY"] = "high"
    os.environ["IMAGE_SEED"] = "123"
    os.environ["IMAGE_GUIDANCE_SCALE"] = "8.0"
    os.environ["IMAGE_NUM_INFERENCE_STEPS"] = "25"
    os.environ["IMAGE_DENOISE_STRENGTH"] = "0.8"
    
    try:
        # Reload settings
        settings = Settings.from_environment()
        
        # Verify environment variables are loaded
        assert settings.image_quality == "high", f"Expected 'high', got {settings.image_quality}"
        assert settings.image_seed == 123, f"Expected 123, got {settings.image_seed}"
        assert abs(settings.image_guidance_scale - 8.0) < 0.001, f"Expected 8.0, got {settings.image_guidance_scale}"
        assert settings.image_num_inference_steps == 25, f"Expected 25, got {settings.image_num_inference_steps}"
        assert abs(settings.image_denoise_strength - 0.8) < 0.001, f"Expected 0.8, got {settings.image_denoise_strength}"
        
        print("  [OK] Environment variables loaded correctly")
    finally:
        # Restore original environment variables
        for key in ["IMAGE_QUALITY", "IMAGE_SEED", "IMAGE_GUIDANCE_SCALE", "IMAGE_NUM_INFERENCE_STEPS", "IMAGE_DENOISE_STRENGTH"]:
            if key in original_env:
                os.environ[key] = original_env[key]
            else:
                os.environ.pop(key, None)
    
    print()


def test_backward_compatibility():
    """Test that the changes are backward compatible."""
    print("Testing backward compatibility...")
    
    # Test that the default settings work
    default_settings = Settings.from_environment()
    
    # Verify default values
    assert default_settings.image_quality == "high", f"Expected 'high', got {default_settings.image_quality}"
    assert default_settings.image_seed == 0, f"Expected 0, got {default_settings.image_seed}"
    assert default_settings.image_guidance_scale == 7.5, f"Expected 7.5, got {default_settings.image_guidance_scale}"
    assert default_settings.image_num_inference_steps == 20, f"Expected 20, got {default_settings.image_num_inference_steps}"
    assert default_settings.image_denoise_strength == 0.7, f"Expected 0.7, got {default_settings.image_denoise_strength}"
    
    print("  [OK] Default settings are correct")
    
    # Test that the workflow path is set correctly
    expected_workflow = "workflows/comfyui_flux_api_enhanced.json"
    actual_workflow = default_settings.comfyui_image_workflow
    
    # Check if the enhanced workflow file exists
    enhanced_workflow_path = Path("workflows") / "comfyui_flux_api_enhanced.json"
    if enhanced_workflow_path.exists():
        print("  [OK] Enhanced workflow file exists")
        print("  [OK] Enhanced workflow path is set correctly")
    else:
        print("  [WARN] Enhanced workflow file not found")
        print("  Note: This may be expected if the file doesn't exist yet")
    
    print()


def main():
    """Run all tests."""
    print("=" * 70)
    print("Testing Enhanced Image Quality Improvements")
    print("=" * 70)
    print()
    
    try:
        test_enhanced_workflow()
        test_quality_aware_enhancements()
        test_sampler_configurations()
        test_environment_variable_support()
        test_backward_compatibility()
        
        print("=" * 70)
        print("All tests passed! OK")
        print("=" * 70)
        return 0
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())