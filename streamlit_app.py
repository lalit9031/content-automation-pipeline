import sys
from pathlib import Path
import site

PROJECT_ROOT = Path(__file__).resolve().parent
TARGET_SITE_PACKAGES = PROJECT_ROOT / "output" / ".runtime" / "site-packages"
TARGET_SITE_PACKAGES.mkdir(parents=True, exist_ok=True)

# Add our custom site-packages using site.addsitedir to process .pth files and set up paths correctly
if str(TARGET_SITE_PACKAGES) not in sys.path:
    old_len = len(sys.path)
    site.addsitedir(str(TARGET_SITE_PACKAGES))
    new_paths = sys.path[old_len:]
    sys.path = new_paths + sys.path[:old_len]
    import importlib
    importlib.invalidate_caches()
    sys.path_importer_cache.clear()

# Run dynamic installer once per Python process lifetime to keep page reruns instant
if not hasattr(sys, "_antigravity_installer_run"):
    sys._antigravity_installer_run = True
    
    # 1. If Python >= 3.13, check and install audioop-lts first
    if sys.version_info >= (3, 13):
        try:
            import audioop
        except ImportError:
            import subprocess
            try:
                print("📦 Dynamic installation: installing audioop-lts to target dir...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "--target", str(TARGET_SITE_PACKAGES), "audioop-lts"
                ])
                print("📦 Dynamic installation of audioop-lts finished.")
                import importlib
                importlib.invalidate_caches()
                sys.path_importer_cache.clear()
            except Exception as e:
                print(f"WARNING: Failed to dynamically install audioop-lts: {e}")

    # 2. Check and install pydub next
    try:
        import pydub
    except ImportError:
        import subprocess
        try:
            print("📦 Dynamic installation: installing pydub to target dir...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "--target", str(TARGET_SITE_PACKAGES), "pydub"
            ])
            print("📦 Dynamic installation of pydub finished.")
            import importlib
            importlib.invalidate_caches()
            sys.path_importer_cache.clear()
        except Exception as e:
            print(f"WARNING: Failed to dynamically install pydub: {e}")


SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():

    sys.path.insert(0, str(SRC_DIR))

from app import main


if __name__ == "__main__":
    main()
