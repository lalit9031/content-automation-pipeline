import os
import json
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/KidsStudio-Orchestrator")
assets_dir = PROJECT_ROOT / "assets"
char_dir = assets_dir / "character"

def main():
    # 1. Create standard dynamic directories
    environments_dir = assets_dir / "environments"
    environments_dir.mkdir(parents=True, exist_ok=True)
    
    peacock_sprite_dir = assets_dir / "sprites" / "proud_peacock"
    peacock_sprite_dir.mkdir(parents=True, exist_ok=True)
    (peacock_sprite_dir / "talk").mkdir(parents=True, exist_ok=True)
    
    crow_sprite_dir = assets_dir / "sprites" / "kalu_crow"
    crow_sprite_dir.mkdir(parents=True, exist_ok=True)
    (crow_sprite_dir / "talk").mkdir(parents=True, exist_ok=True)
    
    project_dir = PROJECT_ROOT / "projects" / "ghamandi_mor"
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Copy/Create background environment files
    jungle_src = char_dir / "jungle_bg.png"
    hunter_src = char_dir / "hunter_bg.png"
    
    if jungle_src.exists():
        Image.open(jungle_src).save(environments_dir / "jungle_river.png", "PNG")
        print("💾 Saved environment: jungle_river.png")
    if hunter_src.exists():
        Image.open(hunter_src).save(environments_dir / "village_road.png", "PNG")
        print("💾 Saved environment: village_road.png")
        
    # 3. Process Peacock Layers & Save
    peacock_src = char_dir / "peacock_body.png"
    if peacock_src.exists():
        peacock_img = Image.open(peacock_src).convert("RGBA")
        pw, ph = peacock_img.size
        
        # Erase body from feathers layer
        peacock_feathers = peacock_img.copy()
        pf_data = list(peacock_feathers.getdata())
        pf_new = []
        for idx, pix in enumerate(pf_data):
            x = idx % pw
            if x >= 560:
                pf_new.append((0, 0, 0, 0))
            else:
                pf_new.append(pix)
        peacock_feathers.putdata(pf_new)
        peacock_feathers.save(peacock_sprite_dir / "feathers.png", "PNG")
        
        # Erase feathers from body layer
        peacock_body = peacock_img.copy()
        pb_data = list(peacock_body.getdata())
        pb_new = []
        for idx, pix in enumerate(pb_data):
            x = idx % pw
            if x < 400:
                pb_new.append((0, 0, 0, 0))
            else:
                pb_new.append(pix)
        peacock_body.putdata(pb_new)
        peacock_body.save(peacock_sprite_dir / "body.png", "PNG")
        print("✂️ Sliced proud_peacock body & feathers layers.")
        
    # 4. Process Kalu Crow Layers & Save
    kalu_src = char_dir / "kalu_body.png"
    if kalu_src.exists():
        kalu_img = Image.open(kalu_src).convert("RGBA")
        kw, kh = kalu_img.size
        
        # Keep only wing box area
        kalu_wing = kalu_img.copy()
        kw_data = list(kalu_wing.getdata())
        kw_new = []
        for idx, pix in enumerate(kw_data):
            x = idx % kw
            y = idx // kw
            if 360 <= x < 680 and 320 <= y < 550:
                kw_new.append(pix)
            else:
                kw_new.append((0, 0, 0, 0))
        kalu_wing.putdata(kw_new)
        kalu_wing.save(crow_sprite_dir / "feathers.png", "PNG")
        
        # Body is original
        kalu_img.save(crow_sprite_dir / "body.png", "PNG")
        print("✂️ Sliced kalu_crow body & wing layers.")
        
    # 5. Copy mouth files to sprites folders
    mouths_dir = char_dir / "mouths"
    if mouths_dir.exists():
        for f in mouths_dir.glob("*.png"):
            # Copy mouth files to both character sheets
            shutil_copy = Image.open(f)
            shutil_copy.save(peacock_sprite_dir / "talk" / f.name, "PNG")
            shutil_copy.save(crow_sprite_dir / "talk" / f.name, "PNG")
        print("👄 Preloaded mouth phonemes into proud_peacock/talk/ and kalu_crow/talk/ directories.")
        
    # 6. Generate localized metadata.json configurations
    peacock_meta = {
        "character_key": "PROUD_PEACOCK",
        "dimensions": [811, 876],
        "anchors": {
            "mouth_anchor_xy": [730, 230],
            "feather_pivot_xy": [300, 776]
        },
        "cycles": {
            "idle": {"total_frames": 1, "fps": 12},
            "walk": {"total_frames": 4, "fps": 12},
            "talk": {"mapping_type": "phoneme_rhubarb"}
        }
    }
    with open(peacock_sprite_dir / "metadata.json", "w") as f:
        json.dump(peacock_meta, f, indent=4)
        
    crow_meta = {
        "character_key": "KALU_CROW",
        "dimensions": [746, 694],
        "anchors": {
            "mouth_anchor_xy": [180, 200],
            "feather_pivot_xy": [450, 360]
        },
        "cycles": {
            "idle": {"total_frames": 1, "fps": 12},
            "walk": {"total_frames": 4, "fps": 12},
            "talk": {"mapping_type": "phoneme_rhubarb"}
        }
    }
    with open(crow_sprite_dir / "metadata.json", "w") as f:
        json.dump(crow_meta, f, indent=4)
        
    print("🔒 Created character localized configuration files.")

if __name__ == "__main__":
    main()
