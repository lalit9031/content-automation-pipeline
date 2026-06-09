import math
from PIL import Image

def render_dynamic_character_frame(
    frame_index: int, 
    fps: int, 
    character_assets: dict, 
    active_mouth_shape: str
) -> Image.Image:
    """
    Dynamically builds a single character frame by blending layers:
    1. Swaying feathers/wing layer (using a sine-wave rotation).
    2. Static character body layer.
    3. Mouth shape layer corresponding to the current phoneme.
    """
    # 1. Load component layers
    body = character_assets["body"].copy()
    feathers = character_assets["feathers"].copy()
    
    # Resolve mouth shape (phoneme)
    mouths = character_assets.get("mouths", {})
    mouth_sprite = mouths.get(active_mouth_shape)
    if not mouth_sprite:
        mouth_sprite = mouths.get("X")
        
    # 2. Calculate smooth continuous sway for secondary motion
    current_time = frame_index / fps
    # Cycle back and forth by 3 degrees every 2 seconds (0.5 Hz frequency)
    sway_angle = 3.0 * math.sin(2.0 * math.pi * current_time / 2.0)
    
    # Rotate around custom pivot if specified, else bottom-center
    pivot = character_assets.get("feather_pivot")
    if pivot is None:
        pivot = (feathers.width // 2, feathers.height)
        
    rotated_feathers = feathers.rotate(
        sway_angle, 
        resample=Image.Resampling.BICUBIC, 
        center=pivot
    )
    
    # 3. Compositing
    frame_canvas = Image.new("RGBA", body.size, (0, 0, 0, 0))
    
    # Layer 1: Swaying feathers/wings
    feather_pos = character_assets.get("feather_pos", (0, 0))
    frame_canvas.alpha_composite(rotated_feathers, feather_pos)
    
    # Layer 2: Main character body
    frame_canvas.alpha_composite(body, (0, 0))
    
    # Layer 3: Dynamic mouth sprite
    if mouth_sprite:
        mouth_pos = character_assets.get("mouth_anchor_coordinates", (0, 0))
        # Use PIL paste with mask to support pasting smaller mouth images at target coordinates
        frame_canvas.paste(mouth_sprite, box=mouth_pos, mask=mouth_sprite)
        
    return frame_canvas
