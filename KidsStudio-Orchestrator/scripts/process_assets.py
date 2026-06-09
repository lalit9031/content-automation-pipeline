import os
import math
from pathlib import Path
from PIL import Image

def remove_background(image_path: Path, output_path: Path, threshold: float = 80):
    img = Image.open(image_path).convert("RGBA")
    width, height = img.size
    
    # Get the background color from the top-left pixel
    bg_color = img.getpixel((0, 0))
    print(f"Detected background color: {bg_color} for {image_path.name}")
    
    # Remove background pixels based on color distance
    datas = img.getdata()
    newData = []
    
    bg_r, bg_g, bg_b = bg_color[0], bg_color[1], bg_color[2]
    
    for item in datas:
        r, g, b, a = item
        # Euclidean distance in RGB
        dist = math.sqrt((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2)
        
        # Also handle general chroma-key fallback (high green, low red/blue)
        is_green = g > 1.35 * r and g > 1.35 * b and g > 60
        
        if dist < threshold or is_green:
            newData.append((0, 0, 0, 0))
        else:
            newData.append(item)
            
    img.putdata(newData)
    
    # Crop to content (bounding box of non-transparent pixels)
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
    brain_dir = Path("/Users/lalitprasadsingh/.gemini/antigravity/brain/de8cee56-ef36-4fbe-bd0e-a324495c02a6")
    assets_dir = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/KidsStudio-Orchestrator/assets/character")
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # Paths to generated green screen files
    kalu_src = brain_dir / "kalu_bird_green_1780949732688.png"
    nandu_src = brain_dir / "nandu_boy_green_1780949749403.png"
    
    kalu_out = assets_dir / "kalu_body.png"
    nandu_out = assets_dir / "nandu_body.png"
    
    print("Processing Kalu Bird...")
    remove_background(kalu_src, kalu_out, threshold=95)
    
    print("\nProcessing Nandu Boy...")
    remove_background(nandu_src, nandu_out, threshold=95)
    
    print("\nFinished background removal!")

if __name__ == "__main__":
    main()
