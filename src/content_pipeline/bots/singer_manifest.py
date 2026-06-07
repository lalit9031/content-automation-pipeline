import os
import urllib.request
import zipfile
import ssl
import shutil
from pathlib import Path

SINGER_MANIFEST = {
    "arijit_singh": {
        "display_name": "Arijit Singh",
        "gender": "male",
        "url": "https://huggingface.co/QuickWick/Music-AI-Voices/resolve/main/Arijit%20Singh%20(RVC)%20(Crepe%20v2)%20450%20Epoch.zip",
        "file_prefix": "Arijit_Singh"
    },
    "shreya_ghoshal": {
        "display_name": "Shreya Ghoshal",
        "gender": "female",
        "url": "https://huggingface.co/sanjay7178/indian-artists-rvc/resolve/main/shreya.zip",
        "file_prefix": "shreya"
    },
    "jubin_nautiyal": {
        "display_name": "Jubin Nautiyal",
        "gender": "male",
        "url": "https://huggingface.co/ivaan2003/ai-rvc/resolve/main/Jubin%20Nautiyal%20-%20Weights.gg%20Model.zip",
        "file_prefix": "Jubin_Nautiyal"
    },
    "badshah": {
        "display_name": "Badshah",
        "gender": "male",
        "url": "https://huggingface.co/ivaan2003/ai-rvc/resolve/main/Badshah%20-%20Weights.gg%20Model.zip",
        "file_prefix": "Badshah"
    },
    "kishore_kumar": {
        "display_name": "Kishore Kumar",
        "gender": "male",
        "url": "https://huggingface.co/ivaan2003/ai-rvc/resolve/main/KK2Ai.zip",
        "file_prefix": "Kishore_Kumar"
    }
}

# Alias mapping for typo compatibility
SINGER_ALIASES = {
    "arijit_singn": "arijit_singh"
}

def verify_and_cache_singer_model(singer_key: str) -> str:
    """
    Verifies if the specified singer's checkpoint exists locally. 
    If missing, automatically fetches the pre-trained weights array 
    from Hugging Face and extracts them to the workspace.
    """
    # Normalize the singer key (handle aliases/typos)
    singer_key = SINGER_ALIASES.get(singer_key, singer_key)
    
    if singer_key not in SINGER_MANIFEST:
        print(f"⚠️ Unknown artist key '{singer_key}'. Defaulting to Arijit Singh core weights.")
        singer_key = "arijit_singh"
        
    config = SINGER_MANIFEST[singer_key]
    model_dir = Path("models/singers")
    pth_file = model_dir / f"{config['file_prefix']}.pth"
    
    # Check for existing localized singer weights footprint
    if pth_file.exists():
        print(f"✅ Local weights found for: {config['display_name']}")
        return config['file_prefix']
        
    print(f"📥 Local weights missing for {config['display_name']}. Initializing remote pipeline fetch...")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    temp_zip_path = model_dir / f"temp_{singer_key}.zip"
    
    try:
        # Stream model bytes over verified/unverified SSL context directly to temporary local ZIP asset
        context = ssl._create_unverified_context()
        req = urllib.request.Request(
            config['url'],
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        
        print(f"📥 Downloading ZIP model from {config['url']}...")
        with urllib.request.urlopen(req, context=context) as response, open(temp_zip_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
            
        # Unpack checkpoint weights and indexing feature layers into destination node folder
        print("📦 Extracting RVC model weights...")
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            pth_extracted = False
            for file_info in zip_ref.infolist():
                filename = Path(file_info.filename).name
                if filename.startswith(".") or file_info.filename.startswith("__MACOSX"):
                    continue
                # Extract .pth file
                if file_info.filename.endswith(".pth"):
                    with zip_ref.open(file_info) as source_file:
                        with open(pth_file, "wb") as target_file:
                            target_file.write(source_file.read())
                    pth_extracted = True
                    print(f"✨ Extracted and saved model weights to: {pth_file}")
                # Extract .index file
                if file_info.filename.endswith(".index"):
                    dest_index = model_dir / f"{config['file_prefix']}.index"
                    with zip_ref.open(file_info) as source_file:
                        with open(dest_index, "wb") as target_file:
                            target_file.write(source_file.read())
                    print(f"✨ Extracted and saved retrieval index to: {dest_index}")
            
            if not pth_extracted:
                raise FileNotFoundError("Could not find a valid .pth file inside the zip archive.")
                
        print(f"🎉 Fully synchronized and cached acoustic fingerprint for: {config['display_name']}")
        
        if temp_zip_path.exists():
            os.remove(temp_zip_path) # Purge the zip download frame to protect storage footprint
            
        return config['file_prefix']
        
    except Exception as e:
        print(f"❌ Failed to sync artist download asset map: {str(e)}")
        if temp_zip_path.exists():
            try:
                os.remove(temp_zip_path)
            except Exception:
                pass
        return "Arijit_Singh" # Seamless fallback to default active singer on network fault
