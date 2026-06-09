def calculate_frame_transform(frame_index: int, fps: int, motion_config: dict) -> tuple:
    """
    Computes the exact X, Y coordinates and scaling factor for a character 
    at any given frame to handle automated smooth walking paths.
    """
    if not motion_config.get("enabled", False):
        # Default static baseline fallback if motion path is off
        return tuple(motion_config.get("start_position")), motion_config.get("start_scale", 1.0)
        
    current_time = frame_index / fps
    start_t = motion_config["start_time"]
    end_t = motion_config["end_time"]
    
    # 1. Hold at start position if the walking animation hasn't triggered yet
    if current_time <= start_t:
        return tuple(motion_config["start_position"]), motion_config["start_scale"]
        
    # 2. Hold at final position if the walk sequence has concluded
    if current_time >= end_t:
        return tuple(motion_config["end_position"]), motion_config["end_scale"]
        
    # 3. Calculate interpolation factor (Progress delta between 0.0 and 1.0)
    progress = (current_time - start_t) / (end_t - start_t)
    
    # Compute smooth coordinate increments
    start_x, start_y = motion_config["start_position"]
    end_x, end_y = motion_config["end_position"]
    
    current_x = start_x + (end_x - start_x) * progress
    current_y = start_y + (end_y - start_y) * progress
    
    # Compute subtle scale shift to simulate walking back into the background perspective
    start_scale = motion_config["start_scale"]
    end_scale = motion_config["end_scale"]
    current_scale = start_scale + (end_scale - start_scale) * progress
    
    return (round(current_x, 2), round(current_y, 2)), round(current_scale, 3)
