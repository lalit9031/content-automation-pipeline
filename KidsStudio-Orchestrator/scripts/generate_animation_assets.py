import os
from pathlib import Path
from PIL import Image, ImageDraw

def create_mock_animation_assets():
    """
    Generates mock cartoon character assets and background using Pillow.
    """
    project_root = Path(__file__).resolve().parents[1]
    assets_dir = project_root / "assets" / "character"
    mouth_dir = assets_dir / "mouths"
    
    assets_dir.mkdir(parents=True, exist_ok=True)
    mouth_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🎨 Generating mock animation assets in: {assets_dir}...")
    
    # 1. Create Kalu the Bird (300x300 transparent canvas)
    kalu = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw_k = ImageDraw.Draw(kalu)
    # Blue body
    draw_k.ellipse([50, 80, 250, 260], fill=(30, 144, 255, 255), outline=(10, 80, 200, 255), width=4)
    # Wing
    draw_k.ellipse([50, 140, 130, 220], fill=(0, 191, 255, 255), outline=(10, 80, 200, 255), width=3)
    # Cute eye
    draw_k.ellipse([180, 110, 220, 150], fill=(255, 255, 255, 255), outline=(20, 20, 20, 255), width=3)
    draw_k.ellipse([195, 120, 215, 140], fill=(20, 20, 20, 255))
    draw_k.ellipse([200, 122, 208, 130], fill=(255, 255, 255, 255))
    # Beak base area (mouth will overlay here)
    draw_k.polygon([(220, 150), (220, 175), (200, 162)], fill=(255, 165, 0, 255))
    
    kalu_path = assets_dir / "kalu_body.png"
    kalu.save(kalu_path, "PNG")
    print(f"   Saved Kalu the Bird asset: {kalu_path}")
    
    # 2. Create Nandu the Boy (300x300 transparent canvas)
    nandu = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw_n = ImageDraw.Draw(nandu)
    # Shirt/Body
    draw_n.ellipse([70, 200, 230, 320], fill=(210, 105, 30, 255), outline=(139, 69, 19, 255), width=4)
    # Face
    draw_n.ellipse([90, 50, 210, 190], fill=(255, 218, 185, 255), outline=(205, 133, 63, 255), width=4)
    # Hair
    draw_n.chord([88, 45, 212, 120], 180, 360, fill=(30, 30, 30, 255))
    # Eyes
    draw_n.ellipse([115, 100, 135, 120], fill=(20, 20, 20, 255))
    draw_n.ellipse([165, 100, 185, 120], fill=(20, 20, 20, 255))
    draw_n.ellipse([120, 102, 126, 108], fill=(255, 255, 255, 255))
    draw_n.ellipse([170, 102, 176, 108], fill=(255, 255, 255, 255))
    # Nose
    draw_n.line([150, 120, 150, 135], fill=(205, 133, 63, 255), width=3)
    
    nandu_path = assets_dir / "nandu_body.png"
    nandu.save(nandu_path, "PNG")
    print(f"   Saved Nandu the Boy asset: {nandu_path}")
    
    # 3. Create Fallback Village Background (1280x720 canvas)
    bg = Image.new("RGBA", (1280, 720), (135, 206, 235, 255)) # Sky blue
    draw_bg = ImageDraw.Draw(bg)
    # Blazing hot sun
    draw_bg.ellipse([1000, 50, 1150, 200], fill=(255, 223, 0, 255), outline=(255, 140, 0, 255), width=8)
    # Ground/Sand path (hot yellow/brown)
    draw_bg.rectangle([0, 450, 1280, 720], fill=(210, 180, 140, 255))
    # Simple clay huts
    # Hut 1
    draw_bg.rectangle([100, 300, 350, 480], fill=(188, 143, 143, 255), outline=(139, 69, 19, 255), width=4)
    draw_bg.polygon([(70, 300), (380, 300), (225, 200)], fill=(139, 69, 19, 255)) # Roof
    draw_bg.rectangle([190, 380, 260, 480], fill=(100, 50, 20, 255)) # Door
    # Hut 2
    draw_bg.rectangle([800, 320, 1000, 480], fill=(205, 133, 63, 255), outline=(139, 69, 19, 255), width=4)
    draw_bg.polygon([(780, 320), (1020, 320), (900, 230)], fill=(160, 82, 45, 255)) # Roof
    draw_bg.rectangle([870, 390, 930, 480], fill=(100, 50, 20, 255)) # Door
    
    # Simple tree trunk & green foliage
    draw_bg.rectangle([550, 250, 600, 480], fill=(101, 67, 33, 255))
    draw_bg.ellipse([480, 150, 670, 300], fill=(34, 139, 34, 255))
    
    bg_path = assets_dir / "mock_village_background.png"
    bg.save(bg_path, "PNG")
    print(f"   Saved mock village background: {bg_path}")
    
    # 4. Create standard mouth shapes (if they do not exist)
    mouth_shapes = {
        "X": "rest",   # Simple closed line
        "A": "aa/ah",  # Big vertical ellipse
        "B": "m/p/b",  # Flat thick line
        "C": "eh",     # Open flat ellipse
        "D": "ooh",    # Small round circle
        "E": "ee",     # Wide flat teeth showing
        "F": "f/v",    # Lower lip touching upper teeth
        "G": "s/t",    # Closed teeth showing
        "H": "l/n"     # Open mouth showing tongue
    }
    
    for key, desc in mouth_shapes.items():
        mouth_path = mouth_dir / f"{key}.png"
        if not mouth_path.exists():
            mouth_img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
            m_draw = ImageDraw.Draw(mouth_img)
            if key == "X":
                m_draw.line([60, 100, 140, 100], fill=(50, 50, 50, 255), width=10)
            elif key == "A":
                m_draw.ellipse([60, 60, 140, 140], fill=(120, 20, 20, 255), outline=(50, 50, 50, 255), width=6)
            elif key == "B":
                m_draw.line([50, 100, 150, 100], fill=(50, 50, 50, 255), width=14)
                m_draw.line([60, 100, 140, 100], fill=(255, 120, 120, 255), width=6)
            elif key == "C":
                m_draw.ellipse([55, 75, 145, 125], fill=(120, 20, 20, 255), outline=(50, 50, 50, 255), width=6)
            elif key == "D":
                m_draw.ellipse([80, 80, 120, 120], fill=(120, 20, 20, 255), outline=(50, 50, 50, 255), width=6)
            elif key == "E":
                m_draw.ellipse([50, 80, 150, 120], fill=(120, 20, 20, 255), outline=(50, 50, 50, 255), width=6)
                m_draw.rectangle([65, 88, 135, 96], fill=(255, 255, 255, 255))
            elif key == "F":
                m_draw.ellipse([50, 80, 150, 122], fill=(120, 20, 20, 255), outline=(50, 50, 50, 255), width=6)
                m_draw.rectangle([65, 88, 135, 96], fill=(255, 255, 255, 255))
                m_draw.line([60, 104, 140, 104], fill=(255, 120, 120, 255), width=4)
            elif key == "G":
                m_draw.ellipse([50, 85, 150, 115], fill=(120, 20, 20, 255), outline=(50, 50, 50, 255), width=6)
                m_draw.rectangle([65, 92, 135, 108], fill=(255, 255, 255, 255))
                m_draw.line([65, 100, 135, 100], fill=(150, 150, 150, 255), width=2)
            elif key == "H":
                m_draw.ellipse([55, 70, 145, 130], fill=(120, 20, 20, 255), outline=(50, 50, 50, 255), width=6)
                m_draw.ellipse([70, 105, 130, 128], fill=(255, 100, 130, 255))
            mouth_img.save(mouth_path, "PNG")
            
    print("✅ Animation assets generation complete.")

if __name__ == "__main__":
    create_mock_animation_assets()
