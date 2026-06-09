import re

def sanitize_script_for_tts(script_text: str) -> str:
    """
    Cleans structural bracket annotations, role designations, and timing tokens
    (e.g., [Verse], [pause], [Narrator], [Character: Name]) from the script
    to produce clean, readable text for high-fidelity speech synthesis.
    """
    if not script_text:
        return ""
        
    # 1. Remove bracketed blocks completely, e.g., [Verse], [Chorus], [pause]
    cleaned = re.sub(r'\[.*?\]', '', script_text)
    
    # 2. Clean up any remaining formatting lines like "Narrator:" or "Speaker 1:" at the start of lines
    cleaned = re.sub(r'^[a-zA-Z0-9\s_]+:\s*', '', cleaned, flags=re.MULTILINE)
    
    # 3. Clean up multiple spaces and newline structures
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # 4. Clean up punctuation spacing and trim ends
    cleaned = cleaned.replace(" .", ".").replace(" ,", ",").strip()
    
    return cleaned

def preprocess_storytelling_pacing(script_text: str) -> str:
    """
    Pre-processes storytelling scripts by adding structural punctuation hints ('...!')
    to guide the neural speech engine to insert dramatic pacing pauses.
    """
    if not script_text:
        return ""
        
    # Standardize Devanagari danda punctuation spacing
    script_text = re.sub(r'।\s*', '...! ', script_text)
    
    # Standardize English periods followed by space/end to add pacing
    script_text = re.sub(r'\.(?=\s|$)', '...! ', script_text)
    
    return script_text
