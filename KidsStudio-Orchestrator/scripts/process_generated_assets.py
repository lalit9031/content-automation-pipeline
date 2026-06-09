import os
import math
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/KidsStudio-Orchestrator")
assets_dir = PROJECT_ROOT / "assets" / "character"
assets_dir.mkdir(parents=True, exist_ok=True)

def remove_background(image_path: Path, output_path: Path, threshold: float = 90):
    img = Image.open(image_path).convert("RGBA")
    width, height = img.size
    
    # Check top-left pixel
    bg_color = img.getpixel((0, 0))
    bg_r, bg_g, bg_b = bg_color[0], bg_color[1], bg_color[2]
    
    datas = img.getdata()
    newData = []
    
    for item in datas:
        r, g, b, a = item
        # Euclidean distance
        dist = math.sqrt((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2)
        
        # Chroma key detection (high green, low red/blue)
        is_green = g > 1.35 * r and g > 1.35 * b and g > 60
        
        # Catch white/very light background
        is_white = r > 240 and g > 240 and b > 240
        
        if dist < threshold or is_green or is_white:
            newData.append((0, 0, 0, 0))
        else:
            newData.append(item)
            
    img.putdata(newData)
    
    bbox = img.getbbox()
    if bbox:
        img_cropped = img.crop(bbox)
        print(f"Cropped {image_path.name} from {width}x{height} to {img_cropped.size}")
        img_cropped.save(output_path, "PNG")
        return img_cropped
    else:
        img.save(output_path, "PNG")
        return img

def main():
    # Source paths (from the generated output paths)
    peacock_src = Path("/Users/lalitprasadsingh/.gemini/antigravity/brain/de8cee56-ef36-4fbe-bd0e-a324495c02a6/peacock_green_1780951658888.png")
    crow_src = Path("/Users/lalitprasadsingh/.gemini/antigravity/brain/de8cee56-ef36-4fbe-bd0e-a324495c02a6/crow_green_1780951673001.png")
    jungle_src = Path("/Users/lalitprasadsingh/.gemini/antigravity/brain/de8cee56-ef36-4fbe-bd0e-a324495c02a6/jungle_bg_1780951689093.png")
    hunter_src = Path("/Users/lalitprasadsingh/.gemini/antigravity/brain/de8cee56-ef36-4fbe-bd0e-a324495c02a6/hunter_bg_1780951705789.png")
    
    # Destination paths
    peacock_out = assets_dir / "peacock_body.png"
    kalu_out = assets_dir / "kalu_body.png" # Kalu is the Crow bird
    jungle_out = assets_dir / "jungle_bg.png"
    hunter_out = assets_dir / "hunter_bg.png"
    
    print("✂️ Processing Peacock...")
    remove_background(peacock_src, peacock_out, threshold=95)
    
    print("✂️ Processing Crow (Kalu)...")
    remove_background(crow_src, kalu_out, threshold=95)
    
    print("💾 Copying & Resizing Jungle Background...")
    img_jg = Image.open(jungle_src)
    img_jg = img_jg.resize((1280, 720), Image.Resampling.LANCZOS)
    img_jg.save(jungle_out, "PNG")
    
    print("💾 Copying & Resizing Hunter Background...")
    img_ht = Image.open(hunter_src)
    img_ht = img_ht.resize((1280, 720), Image.Resampling.LANCZOS)
    img_ht.save(hunter_out, "PNG")
    
    print("✅ Assets processed successfully!")

if __name__ == "__main__":
    main()
