import os
import time
import shutil
from pathlib import Path

def run_global_housekeeping_if_due(scratch_dir_path: str = "/Users/lalitprasadsingh/.gemini/antigravity/scratch"):
    """
    Checks if 3 days have passed since the last global cleanup.
    If so, deletes loose media files (*.mp3, *.wav, *.mp4, *.png, *.svg) directly under the scratch folder.
    """
    scratch_dir = Path(scratch_dir_path)
    if not scratch_dir.exists():
        return
        
    timestamp_file = scratch_dir / ".last_global_cleanup"
    current_time = time.time()
    three_days_seconds = 3 * 24 * 3600  # 259,200 seconds
    
    should_clean = False
    
    if not timestamp_file.exists():
        # First-time initialization
        should_clean = True
    else:
        try:
            with open(timestamp_file, "r") as f:
                last_time = float(f.read().strip())
            if current_time - last_time >= three_days_seconds:
                should_clean = True
        except Exception:
            # Fallback if file is corrupted
            should_clean = True
            
    if should_clean:
        print(f"\n🧹 Janitor Core: 3 days have passed. Running automated global storage scrub under {scratch_dir_path}...")
        extensions_to_clean = {".mp3", ".wav", ".mp4", ".png", ".svg"}
        
        try:
            for item in scratch_dir.iterdir():
                if item.is_file() and item.suffix.lower() in extensions_to_clean:
                    try:
                        item.unlink()
                        print(f"  🗑️ Cleared: {item.name}")
                    except Exception as e:
                        print(f"  ⚠️ Could not delete file {item.name}: {e}")
                        
            # Update the timestamp
            with open(timestamp_file, "w") as f:
                f.write(str(current_time))
            print("✅ Global housekeeping complete. Timestamp updated.")
        except Exception as e:
            print(f"⚠️ Janitor Warning: Error during global scratch cleanup: {e}")

def archive_and_purge_project(project_folder_name: str, base_projects_dir: str = "./projects"):
    """
    Implements our retention policy. Preserves the tiny manifest blueprint, output videos,
    and voice tracks, but completely purges the heavy image frame caches to save local SSD space.
    """
    target_project_path = Path(base_projects_dir) / project_folder_name
    frame_cache_path = target_project_path / "render_output"
    
    print(f"\n🧹 Janitor Core: Running automated data retention cleanup for [{project_folder_name}]...")
    
    # 1. Safely remove the heavy intermediate PNG image frames folder
    if frame_cache_path.exists():
        try:
            shutil.rmtree(frame_cache_path)
            print(f"✅ Storage Saved: Purged heavy intermediate layers from {frame_cache_path}")
        except Exception as e:
            print(f"⚠️ Janitor Warning: Could not clear frame cache directory: {e}")
    else:
        print(f"ℹ️ Janitor Note: No frame cache directory found at {frame_cache_path}")
            
    # 2. Confirm core metadata blueprints are safe
    manifest_check = target_project_path / "scene_manifest.json"
    if manifest_check.exists():
        print(f"🔒 Blueprint Secure: Retaining dynamic JSON recipe file at: {manifest_check}")
    else:
        print(f"⚠️ Janitor Alert: Blueprint manifest not found at: {manifest_check}")

    # 3. Confirm vocals are safe
    vocals_check = target_project_path / "vocals"
    if vocals_check.exists():
        vocal_files = list(vocals_check.glob("*"))
        print(f"🔒 Vocals Secure: Preserving {len(vocal_files)} vocal/BGM assets at: {vocals_check}")
        
    print(f"✨ Lifecycle execution complete. Machine storage footprint minimized.")

if __name__ == "__main__":
    # Get the project root directory
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    # Run global housekeeping check
    run_global_housekeeping_if_due(scratch_dir_path=str(PROJECT_ROOT.parent))
    # Test pass run manually via terminal execution
    archive_and_purge_project("ghamandi_mor", base_projects_dir=str(PROJECT_ROOT / "projects"))
