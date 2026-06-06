import re
import logging
from google import genai

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a master phonetic transcriptionist for AI singing models (such as LeVo-2/Tencent SongGeneration) "
    "which are trained on English/Chinese datasets and struggle with South Asian phonetics.\n"
    "Translate/transcribe the following Hindi lyrics (which may be in Devanagari or Hinglish) into phonetic English spelling "
    "that will guide the model to sing with a perfect native Indian accent and tone (vibe).\n"
    "Rules:\n"
    "1. Map dental soft 't' to 'th' (e.g. 'titli' -> 'thith-lee', 'tum' -> 'thum').\n"
    "2. Map retroflex hard 't' to 't' (e.g. 'tamatar' -> 'ta-ma-tar').\n"
    "3. Map dental soft 'd' to 'dh' (e.g. 'dil' -> 'dhil', 'dheela' -> 'dhee-la').\n"
    "4. Map retroflex hard 'd' to 'd' (e.g. 'dawat' -> 'da-wat', 'chadhi' -> 'chud-hee').\n"
    "5. Use double letters for long vowels to force correct vowel length (e.g., 'aaye' -> 'aa-yay', 'joota' -> 'joo-tha', 'rone' -> 'roh-nay').\n"
    "6. Break words with hyphens if it helps correct syllable pacing (e.g., 'rasgulla' -> 'rus-gul-la').\n"
    "7. Preserve brackets around section tags (like [verse], [chorus], [bridge]) EXACTLY as they are. Do not transcribe or modify them.\n"
    "Output ONLY the phonetic transliterated lyrics. Do not add any conversational text, explanations, or markdown formatting."
)

def has_devanagari(text: str) -> bool:
    return bool(re.search(r'[\u0900-\u097F]', text))

def rule_based_phonetic_fallback(lyrics: str) -> str:
    """Fallback rule-based phonetic mapper when Gemini is unavailable."""
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
            itrans = transliterate(line_strip, sanscript.DEVANAGARI, sanscript.ITRANS)
        else:
            itrans = line_strip

        words = itrans.split()
        converted_words = []
        
        for word in words:
            leading_punc = ""
            trailing_punc = ""
            while word and not word[0].isalnum() and word[0] not in ['[', ']']:
                leading_punc += word[0]
                word = word[1:]
            while word and not word[-1].isalnum() and word[-1] not in ['[', ']']:
                trailing_punc = word[-1] + trailing_punc
                word = word[:-1]
                
            if not word:
                converted_words.append(leading_punc + trailing_punc)
                continue
                
            w = word
            # 1. Map conjuncts
            w = w.replace("j~n", "gy")
            w = w.replace("kShetra", "kshetra")
            w = w.replace("x", "ksh")
            w = w.replace(".Dh", "dh")
            w = w.replace(".d", "d")
            w = w.replace(".D", "d")
            
            # 2. Map nasalizations (anusvara)
            w = w.replace("oM", "ohn")
            w = w.replace("eM", "mayn")
            w = w.replace("aiM", "ayn")
            w = w.replace("iM", "in")
            w = w.replace("uM", "oon")
            w = w.replace("aM", "an")
            w = w.replace("M", "n")
            
            # 3. Map vowels
            w = w.replace("RRi", "ri")
            w = w.replace("RR", "ri")
            w = w.replace("R", "ri")
            
            # 4. Map 'e' and 'o' to sound-alike English phonics
            w = w.replace("e", "ay")
            w = w.replace("o", "oh")
            
            # Map case-sensitive ITRANS long vowels
            w = w.replace("A", "aa")
            w = w.replace("I", "ee")
            w = w.replace("U", "oo")
            
            # 5. Map short 'a' (schwa) to 'u' or 'uh'
            if w.endswith("a") and not w.endswith("aa") and len(w) > 2:
                w = w[:-1]
                
            w = re.sub(r'(?<![aeiouy])a(?![aeiouy])', 'u', w)
            
            # 6. Simplify double consonants
            w = w.replace("chch", "ch")
            w = w.lower()
            
            converted_words.append(leading_punc + w + trailing_punc)
            
        converted_lines.append(" ".join(converted_words))
        
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
