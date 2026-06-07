from pathlib import Path
import sys

# Self-healing package installer to guarantee pydub is installed at runtime on Streamlit Sharing
try:
    import pydub
except ImportError:
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pydub"])
    except Exception as e:
        print(f"WARNING: Failed to dynamically install pydub: {e}")

# If Python >= 3.13, we also check and install audioop-lts if needed
if sys.version_info >= (3, 13):
    try:
        import audioop
    except ImportError:
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "audioop-lts"])
        except Exception as e:
            print(f"WARNING: Failed to dynamically install audioop-lts: {e}")

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from app import main


if __name__ == "__main__":
    main()
