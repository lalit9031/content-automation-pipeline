from pathlib import Path
import sys

# Ensure audioop is available on Python 3.13+ via audioop-lts if installed
if sys.version_info >= (3, 13):
    try:
        import audioop
    except ImportError:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():

    sys.path.insert(0, str(SRC_DIR))

from app import main


if __name__ == "__main__":
    main()
