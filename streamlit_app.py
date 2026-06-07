from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
TARGET_SITE_PACKAGES = PROJECT_ROOT / "output" / ".runtime" / "site-packages"
TARGET_SITE_PACKAGES.mkdir(parents=True, exist_ok=True)

# Add our custom site-packages to sys.path so any packages installed there are importable
if str(TARGET_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(TARGET_SITE_PACKAGES))

# 1. If Python >= 3.13, check and install audioop-lts first
if sys.version_info >= (3, 13):
    try:
        import audioop
    except ImportError:
        flag_file_audioop = PROJECT_ROOT / "output" / ".runtime" / "audioop_install_attempted.flag"
        if not flag_file_audioop.exists():
            import subprocess
            try:
                flag_file_audioop.parent.mkdir(parents=True, exist_ok=True)
                flag_file_audioop.touch()
                print("📦 Dynamic installation: installing audioop-lts to target dir...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "--target", str(TARGET_SITE_PACKAGES), "audioop-lts"
                ])
                print("📦 Dynamic installation of audioop-lts finished.")
            except Exception as e:
                print(f"WARNING: Failed to dynamically install audioop-lts: {e}")

# 2. Check and install pydub next
try:
    import pydub
except ImportError:
    flag_file = PROJECT_ROOT / "output" / ".runtime" / "pydub_install_attempted.flag"
    if not flag_file.exists():
        import subprocess
        try:
            flag_file.parent.mkdir(parents=True, exist_ok=True)
            flag_file.touch()
            print("📦 Dynamic installation: installing pydub to target dir...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "--target", str(TARGET_SITE_PACKAGES), "pydub"
            ])
            print("📦 Dynamic installation of pydub finished.")
        except Exception as e:
            print(f"WARNING: Failed to dynamically install pydub: {e}")


SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():

    sys.path.insert(0, str(SRC_DIR))

from app import main


if __name__ == "__main__":
    main()
