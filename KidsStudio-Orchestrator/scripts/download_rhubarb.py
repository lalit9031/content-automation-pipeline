import os
import sys
import urllib.request
import zipfile
import shutil
from pathlib import Path

def download_and_setup_rhubarb():
    """
    Automates fetching, extracting, and preparing the Rhubarb Lip Sync binary
    for macOS architectures without manual download steps.
    """
    project_root = Path(__file__).resolve().parents[1]
    bin_dir = project_root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    
    # Target release binary URL for macOS
    url = "https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.14.0/Rhubarb-Lip-Sync-1.14.0-macOS.zip"
    zip_path = bin_dir / "rhubarb_download.zip"
    extract_dir = bin_dir / "rhubarb_extracted"
    target_binary = bin_dir / "rhubarb"
    
    # 1. Download ZIP file
    print(f"📥 Downloading native macOS Rhubarb release from:\n   {url}...")
    try:
        # User-Agent string to bypass simple request blocks
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        print("✅ ZIP Download complete.")
    except Exception as e:
        print(f"❌ Failed to download binary: {e}")
        sys.exit(1)
        
    # 2. Extract contents
    print("📦 Extracting package archive contents...")
    try:
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        print("✅ Extraction complete.")
    except Exception as e:
        print(f"❌ Failed to extract zip package: {e}")
        # Clean up zip
        if zip_path.exists():
            os.remove(zip_path)
        sys.exit(1)
        
    # 3. Locate and move binary file
    # Inside the unzipped directory, there should be a folder named 'Rhubarb-Lip-Sync-1.14.0-macOS'
    # containing 'rhubarb' and 'res' folder.
    source_binary = None
    for root, dirs, files in os.walk(extract_dir):
        if "rhubarb" in files:
            source_binary = Path(root) / "rhubarb"
            break
            
    if not source_binary:
        print("❌ Could not locate 'rhubarb' binary within the extracted directory.")
        # Clean up
        shutil.rmtree(extract_dir)
        os.remove(zip_path)
        sys.exit(1)
        
    # Copy 'rhubarb' to bin/rhubarb
    print(f"🚚 Moving binary to target workspace path: {target_binary}")
    shutil.copy(source_binary, target_binary)
    
    # Copy the required resources folder 'res' (rhubarb relies on dictionary models in res/)
    source_res_dir = source_binary.parent / "res"
    target_res_dir = bin_dir / "res"
    if source_res_dir.exists():
        print(f"🚚 Copying supporting resource dictionaries to: {target_res_dir}")
        if target_res_dir.exists():
            shutil.rmtree(target_res_dir)
        shutil.copytree(source_res_dir, target_res_dir)
        
    # 4. Set execution permissions (chmod +x)
    print("🔑 Securing executable file permissions (chmod +x)...")
    try:
        os.chmod(target_binary, 0o755)
        print("✅ Executable permissions set.")
    except Exception as e:
        print(f"⚠️ Warning: Failed to apply chmod permissions: {e}")
        
    # 5. Clean up temporary files
    print("🧹 Cleaning up installer temporary directories...")
    shutil.rmtree(extract_dir)
    os.remove(zip_path)
    
    print("\n🎉 Setup Successful! Rhubarb speech alignment engine is ready to compile timings.")

if __name__ == "__main__":
    download_and_setup_rhubarb()
