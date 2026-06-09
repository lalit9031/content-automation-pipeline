import os
import json
from PIL import Image

def load_dynamic_character_bundle(character_folder_name: str, base_sprites_dir: str = "./assets/sprites") -> dict:
    """
    Dynamically parses a character's local directory at runtime.
    Extracts custom facial anchors and loads image matrices on the fly.
    """
    # Resolve relative paths relative to PROJECT_ROOT if needed
    project_root = Path(__file__).resolve().parents[2]
    abs_sprites_dir = project_root / base_sprites_dir.lstrip("./")
    target_path = abs_sprites_dir / character_folder_name
    
    meta_file = target_path / "metadata.json"
    
    if not meta_file.exists():
        raise FileNotFoundError(f"❌ Automation Error: Config file missing for asset bundle: [{character_folder_name}] at {meta_file}")
        
    # 1. Parse the localized metadata JSON configuration sheet
    with open(meta_file, "r", encoding="utf-8") as f:
        meta_data = json.load(f)
        
    print(f"🔒 Asset Core: Parsing dynamic runtime configuration for [{meta_data['character_key']}]")
    
    # 2. Build the asset memory bundle container dynamically
    bundle = {
        "character_key": meta_data["character_key"],
        "mouth_anchor_xy": tuple(meta_data["anchors"]["mouth_anchor_xy"]),
        "feather_pivot_xy": tuple(meta_data["anchors"]["feather_pivot_xy"]),
        "body_dimensions": tuple(meta_data["dimensions"]),
        "body": Image.open(target_path / "body.png").convert("RGBA"),
        "feathers": Image.open(target_path / "feathers.png").convert("RGBA"),
        "mouths": {}
    }
    
    # 3. Dynamically loop through and load whatever mouth shapes are present in the talk folder
    mouth_dir = target_path / "talk"
    if mouth_dir.exists():
        for file in os.listdir(mouth_dir):
            if file.endswith(".png"):
                shape_key = os.path.splitext(file)[0].upper() # e.g., 'A', 'B', 'X'
                bundle["mouths"][shape_key] = Image.open(mouth_dir / file).convert("RGBA")
                
    return bundle

# Ensure Path is imported
from pathlib import Path
