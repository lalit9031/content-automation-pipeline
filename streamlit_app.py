from pathlib import Path
import sys

# Self-healing package installer to guarantee pydub is installed at runtime on Streamlit Sharing
try:
    import pydub
except ImportError:
    import os
    from pathlib import Path
    flag_file = Path(__file__).resolve().parent / "output" / ".runtime" / "pydub_install_attempted.flag"
    if not flag_file.exists():
        import subprocess
        try:
            flag_file.parent.mkdir(parents=True, exist_ok=True)
            flag_file.touch()
            print("📦 Dynamic installation: installing pydub...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pydub"])
            print("📦 Dynamic installation of pydub finished.")
        except Exception as e:
            print(f"WARNING: Failed to dynamically install pydub: {e}")

# If Python >= 3.13, we also check and install audioop-lts if needed
if sys.version_info >= (3, 13):
    try:
        import audioop
    except ImportError:
        from pathlib import Path
        flag_file_audioop = Path(__file__).resolve().parent / "output" / ".runtime" / "audioop_install_attempted.flag"
        if not flag_file_audioop.exists():
            import subprocess
            try:
                flag_file_audioop.parent.mkdir(parents=True, exist_ok=True)
                flag_file_audioop.touch()
                print("📦 Dynamic installation: installing audioop-lts...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "audioop-lts"])
                print("📦 Dynamic installation of audioop-lts finished.")
            except Exception as e:
                print(f"WARNING: Failed to dynamically install audioop-lts: {e}")

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from app import main


if __name__ == "__main__":
    main()
