import os
import json

def initialize_character_sprite_matrix(character_name: str, base_dir: str = "./assets/sprites"):
    """
    Automates the creation of children character sprite directories 
    and generates structural metadata maps to prevent engine runtime breaks.
    """
    char_root = os.path.join(base_dir, character_name)
    cycles = ["idle", "walk", "talk"]
    
    print(f"📁 Asset Engine: Creating isolated directory matrix for character: [{character_name}]")
    
    # 1. Procedurally generate sub-state directories
    for cycle in cycles:
        cycle_path = os.path.join(char_root, cycle)
        os.makedirs(cycle_path, exist_ok=True)
        # Drop a dummy placeholder text file to preserve empty directories in git repos
        with open(os.path.join(cycle_path, ".placeholder"), "w") as f:
            f.write("Drop your 2D vector PNG frames here.")
            
    # 2. Compile structural animation metadata map
    metadata = {
        "character_name": character_name,
        "frame_dimensions": [512, 512],
        "cycles": {
            "idle": {"loop": True, "fps": 12, "total_frames": 1},
            "walk": {"loop": True, "fps": 12, "total_frames": 4},
            "talk": {
                "loop": False,
                "mapping_type": "phoneme_rhubarb",
                "shapes": ["A", "B", "C", "D", "E", "F", "X"]
            }
        }
    }
    
    metadata_path = os.path.join(char_root, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
        
    print(f"🏆 Initialization Success: System manifest written to [{metadata_path}]")
    return char_root

if __name__ == "__main__":
    # Test pass setup execution for Nandu and Kalu the Bird
    # Ensure correct base path relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    base_sprites_dir = os.path.join(project_root, "assets", "sprites")
    initialize_character_sprite_matrix("nandu", base_dir=base_sprites_dir)
    initialize_character_sprite_matrix("kalu", base_dir=base_sprites_dir)
