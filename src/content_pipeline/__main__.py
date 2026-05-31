from pathlib import Path

from .cli import main
from .config import Settings
from .bots.blocker_agent import log_exception


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        try:
            settings = Settings.from_environment(Path.cwd())
            log_exception(settings.output_dir, command="content-pipeline", exc=exc, component="cli")
        except Exception:
            pass
        raise
