import re
import logging
from google import genai

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a master transliterator. Transliterate the following Hindi lyrics (which may be in Devanagari or Hinglish) into clean, standard Roman Hinglish.\n"
    "Rules:\n"
    "1. Use standard, commonly-accepted Hinglish spellings (e.g., use 'titli' instead of 'thithlee', 'tum' instead of 'thum', 'rone' instead of 'rohnay', 'chal' instead of 'chul', 'gayi' instead of 'gayee').\n"
    "2. Do NOT distort spellings or apply phonetic guides (e.g., do not use double vowels like 'aajaa' or 'mayray' - use standard 'aja' or 'mere').\n"
    "3. Keep all words as clean, standard Hinglish. Strip complex punctuation (like semicolons, extra hyphens, commas at the end of lines) but keep basic sentence flow.\n"
    "4. Preserve brackets around section tags (like [verse], [chorus], [bridge]) EXACTLY as they are. Do not translate or modify them.\n"
    "5. CRITICAL: Preserve all original line breaks and newlines EXACTLY. Do not combine lines or output the lyrics as a single line.\n"
    "Output ONLY the transliterated Hinglish lyrics. Do not add any conversational text, explanations, or markdown formatting."
)

def has_devanagari(text: str) -> bool:
    return bool(re.search(r'[\u0900-\u097F]', text))

def rule_based_phonetic_fallback(lyrics: str) -> str:
    """Fallback rule-based transliterator when Gemini is unavailable."""
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
    except ImportError:
        logger.warning("indic-transliteration not installed. Returning original text.")
        return lyrics

    lines = lyrics.splitlines()
    converted_lines = []

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            converted_lines.append("")
            continue
            
        if line_strip.startswith("[") and line_strip.endswith("]"):
            converted_lines.append(line_strip)
            continue
            
        # Transliterate only if it contains Devanagari
        if has_devanagari(line_strip):
            hk = transliterate(line_strip, sanscript.DEVANAGARI, sanscript.HK)
            hk = hk.lower()
            hk = hk.replace("aa", "a")
            hk = hk.replace("ii", "i")
            hk = hk.replace("uu", "u")
            hk = hk.replace("R^i", "ri")
            hk = hk.replace("sh", "sh")
            hk = hk.replace("s", "s")
            hk = hk.replace("t", "t")
            hk = hk.replace("d", "d")
            hk = hk.replace("n", "n")
            line_out = hk
        else:
            line_out = line_strip

        # Clean punctuation slightly
        line_out = re.sub(r'[;:,.]', '', line_out)
        converted_lines.append(line_out)
        
    return "\n".join(converted_lines)

def hindi_to_phonetic_hinglish(lyrics: str, gemini_api_key: str | None = None) -> str:
    """Converts Hindi/Hinglish lyrics into phonetic Hinglish for high-quality singing."""
    if not lyrics or not lyrics.strip():
        return lyrics

    if gemini_api_key:
        try:
            logger.info("Attempting Gemini-based phonetic transliteration...")
            client = genai.Client(api_key=gemini_api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[SYSTEM_PROMPT, lyrics]
            )
            res_text = response.text.strip()
            if res_text:
                logger.info("Gemini-based phonetic transliteration succeeded.")
                # Verify it has structure tags preserved
                if "[verse]" in lyrics.lower() and "[verse]" not in res_text.lower():
                    # Fallback to check tags
                    pass
                else:
                    return res_text
        except Exception as e:
            logger.warning(f"Gemini phonetic translation failed, falling back to rules: {e}")

    logger.info("Running rule-based phonetic mapping fallback...")
    return rule_based_phonetic_fallback(lyrics)
